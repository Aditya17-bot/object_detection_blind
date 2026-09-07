"""Replay a recorded walk through EVERY capability and report weaknesses.

Why this exists
---------------
Unit tests cover each pure function; the field walks cover walk mode. Nothing
covered the rest of the surface — find for each class, describe, count, check,
clear path, recall, colour, light — against real frames at the handset's real
frame rate. This runs the actual server pipeline (yolov8s + custom model +
cross-model merge + embedding naming head) over a clip, drives a real
GuidanceEngine at the phone's measured cadence, and exercises every capability
at every sampled frame.

It reports ANOMALIES, not just output: statements the system made that the
frame does not support, and questions it refused that the frame does support.
Those are the things that cost a demo.

    venv-gpu\\Scripts\\python.exe tools/replay_all_features.py ^
        test_output/field_walk_20260907.mp4 --fps 2.2

Always venv-gpu: `venv` is the CPU torch build (~750 ms/frame).
"""
import argparse
import collections
import json
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour_naming
import decision
from decision import GuidanceEngine
from detect_merge import merge_detections
from name_index import TRUSTED_KEY, Namer
from object_memory import ObjectMemory
from position import (OBSTACLE_CLASSES, TARGET_CLASSES, analyze_box,
                      clock_phrase, distance_meters)

COCO_CONF = 0.6
CUSTOM_CONF = 0.4
_CUSTOM_FLOOR = {"door": 0.4, "dustbin": 0.6}
DIRECTIONS = ("left", "ahead", "right")


# ----------------------------------------------------------------------
# detection — mirrors infer_server.build_app()'s /infer body exactly
# ----------------------------------------------------------------------
def load_models(name_index="name_index.npz"):
    from ultralytics import YOLO
    coco = YOLO("yolov8s.pt")
    try:
        custom = YOLO("door_dustbin_stairs.pt")
    except Exception as exc:  # noqa: BLE001
        print(f"custom model unavailable ({exc})")
        custom = None
    namer = None
    if name_index and os.path.exists(name_index):
        namer = Namer.maybe_load(name_index, coco, "yolov8s.pt",
                                 vocabulary=TARGET_CLASSES)
    return coco, custom, namer


def _collect(result, names, conf_floor, keep_all, trusted=False):
    out = []
    for b in result.boxes:
        name = names[int(b.cls)]
        conf = float(b.conf)
        if not keep_all and name not in TARGET_CLASSES:
            continue
        if conf < _CUSTOM_FLOOR.get(name, conf_floor):
            continue
        x1, y1, x2, y2 = (float(t) for t in b.xyxyn[0])
        det = {"name": name, "conf": conf, "x1": x1, "y1": y1,
               "x2": x2, "y2": y2}
        if trusted:
            det[TRUSTED_KEY] = True
        out.append(det)
    return out


def detect(frame, coco, custom, namer, imgsz=640):
    keep_all = namer is not None
    dets = _collect(coco.predict(frame, conf=COCO_CONF, imgsz=imgsz,
                                 verbose=False)[0],
                    coco.names, COCO_CONF, keep_all)
    if custom is not None:
        dets += _collect(custom.predict(frame, conf=CUSTOM_CONF, imgsz=imgsz,
                                        verbose=False)[0],
                         custom.names, CUSTOM_CONF, keep_all, trusted=True)
    if namer is not None:
        namer.apply(frame, dets)
        dets = [d for d in dets if d["name"] in TARGET_CLASSES]
    return merge_detections(dets, floors=dict(_CUSTOM_FLOOR),
                            default_floor=COCO_CONF)


def infos_from(dets, w, h):
    out = []
    for d in dets:
        out.append(analyze_box(
            d["name"], d["conf"], d["x1"] * w, d["y1"] * h,
            d["x2"] * w, d["y2"] * h, w, h,
            trusted_name=bool(d.get(TRUSTED_KEY) or d.get("trusted_name"))))
    return out


# ----------------------------------------------------------------------
# the replay
# ----------------------------------------------------------------------
class Findings:
    """Anomalies, grouped by kind so one recurring fault is one line."""

    def __init__(self):
        self.items = collections.defaultdict(list)

    def add(self, kind, detail):
        self.items[kind].append(detail)

    def report(self):
        if not self.items:
            return "no anomalies\n"
        lines = []
        for kind, details in sorted(self.items.items(),
                                    key=lambda kv: -len(kv[1])):
            lines.append(f"* {kind}  ({len(details)}x)")
            for d in details[:6]:
                lines.append(f"    - {d}")
            if len(details) > 6:
                lines.append(f"    - ... {len(details) - 6} more")
        return "\n".join(lines) + "\n"


def replay(path, fps, imgsz, name_index, out_md, max_frames=None):
    coco, custom, namer = load_models(name_index)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, int(round(src_fps / fps)))

    engine = GuidanceEngine()            # defaults = what the app ships
    memory = ObjectMemory()
    find_engines = {}                    # class -> its own engine, run in parallel
    f = Findings()

    announcements = []                   # (t, message)
    per_capability = collections.defaultdict(list)
    class_frames = collections.Counter()
    class_conf = collections.defaultdict(list)
    renamed = collections.Counter()
    frames_with_dets = 0
    sampled = 0
    infer_ms = []
    last_infos = []

    idx = -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1
        if idx % step:
            continue
        sampled += 1
        if max_frames and sampled > max_frames:
            break
        t = idx / src_fps                # video time == the engine's clock
        h, w = frame.shape[:2]

        t0 = time.monotonic()
        dets = detect(frame, coco, custom, namer, imgsz)
        infer_ms.append((time.monotonic() - t0) * 1000)

        for d in dets:
            if "yolo_name" in d:
                renamed[f'{d["yolo_name"]} -> {d["name"]}'] += 1
        infos = infos_from(dets, w, h)
        last_infos = infos
        if infos:
            frames_with_dets += 1
        for i in infos:
            class_frames[i.name] += 1
            class_conf[i.name].append(i.confidence)

        # -- walk mode, the always-on path -----------------------------
        msg = engine.update(infos, t)
        if msg:
            announcements.append((t, msg))
            _check_walk(msg, infos, t, f)

        memory.remember(infos, t)

        # -- every on-demand capability, at every sampled frame --------
        # A separate engine per capability so on-demand calls never disturb
        # the walk engine's cooldown state (the app's speech policy keeps
        # them apart in the same way).
        probe = GuidanceEngine()
        probe._memory = dict(engine._memory)

        desc = decision.summarize_scene(infos)
        per_capability["describe"].append((t, desc))
        _check_describe(desc, infos, t, f)

        pathmsg = decision.clear_path(infos)
        per_capability["path"].append((t, pathmsg))
        _check_path(pathmsg, infos, t, f)

        for d in DIRECTIONS:
            chk = decision.check_direction(infos, d)
            per_capability[f"check {d}"].append((t, chk))
            _check_check(chk, infos, d, t, f)

        for name in sorted({i.name for i in infos}):
            cnt = decision.count_message(infos, name)
            per_capability["count"].append((t, cnt))
            _check_count(cnt, infos, name, t, f)

        # find: one persistent engine per class ever seen, so the ENGINE's
        # own persistence/absence logic is exercised across time rather than
        # re-created each frame.
        for name in sorted(set(class_frames)):
            fe = find_engines.get(name)
            if fe is None:
                fe = GuidanceEngine(mode="find", target=name)
                find_engines[name] = fe
            if fe.mode == "walk":        # found already: re-arm the search
                fe.set_mode("find", name)
            fmsg = fe.update(infos, t)
            if fmsg:
                per_capability[f"find {name}"].append((t, fmsg))
                _check_find(fmsg, infos, name, t, f)

        # colour + light read the centre patch, exactly as _sampleColour does
        cmsg, lmsg = _colour_light(frame)
        per_capability["colour"].append((t, cmsg))
        per_capability["light"].append((t, lmsg))

    cap.release()

    # -- recall, after the walk, for everything ever seen ---------------
    end = idx / src_fps
    recalls = []
    for name in sorted(class_frames):
        recalls.append((name, engine.recall(name, end),
                        memory.recall(name, end)))

    _check_memory_agreement(recalls, f)
    _check_cadence(announcements, f)
    _check_vocabulary(class_frames, f)

    md = _write_report(out_md, path, src_fps, total, fps, sampled,
                       frames_with_dets, infer_ms, class_frames, class_conf,
                       renamed, announcements, per_capability, recalls, f)
    print(md)
    return md


# ----------------------------------------------------------------------
# invariant checks — each one is a way a demo goes wrong
# ----------------------------------------------------------------------
def _check_walk(msg, infos, t, f):
    if not infos:
        f.add("walk announced with no detections", f"t={t:.1f}s {msg!r}")
        return
    if msg.lower().startswith("obstacle"):
        f.add("walk said generic 'Obstacle' instead of a name",
              f"t={t:.1f}s {msg!r} "
              f"(seen: {sorted({i.name for i in infos})})")
    named = [i.name for i in infos if i.name in OBSTACLE_CLASSES]
    if not named:
        f.add("walk warned about a non-obstacle class",
              f"t={t:.1f}s {msg!r}")


def _check_describe(msg, infos, t, f):
    if infos and msg.lower().startswith("nothing"):
        f.add("describe said 'nothing' with detections present",
              f"t={t:.1f}s {sorted({i.name for i in infos})}")
    if not infos and not msg.lower().startswith("nothing"):
        f.add("describe named something with no detections",
              f"t={t:.1f}s {msg!r}")


def _check_path(msg, infos, t, f):
    if msg is None:
        f.add("clear_path returned None", f"t={t:.1f}s")


def _check_check(msg, infos, direction, t, f):
    if msg is None:
        f.add("check returned None for a known direction",
              f"t={t:.1f}s {direction}")
        return
    third = {"left": (0.0, 1 / 3), "ahead": (1 / 3, 2 / 3),
             "right": (2 / 3, 1.0)}[direction]
    present = [i.name for i in infos if third[0] <= i.center_x < third[1]]
    empty_answer = "nothing" in msg.lower()
    if present and empty_answer:
        f.add("check said 'nothing' with objects in that third",
              f"t={t:.1f}s {direction}: {sorted(set(present))} -> {msg!r}")
    if not present and not empty_answer:
        f.add("check named something absent from that third",
              f"t={t:.1f}s {direction}: {msg!r}")


def _check_count(msg, infos, name, t, f):
    actual = sum(1 for i in infos if i.name == name)
    digits = [int(s) for s in msg.split() if s.isdigit()]
    spoken = digits[0] if digits else (1 if " no " not in f" {msg.lower()} "
                                       else 0)
    if actual != spoken:
        f.add("count disagreed with the frame",
              f"t={t:.1f}s {name}: frame has {actual}, said {msg!r}")


def _check_find(msg, infos, name, t, f):
    visible = any(i.name == name for i in infos)
    if visible and "not visible" in msg.lower():
        f.add("find said 'not visible' while the object was detected",
              f"t={t:.1f}s {name}: {msg!r}")
    if visible and "still looking" in msg.lower():
        f.add("find said 'still looking' while the object was detected",
              f"t={t:.1f}s {name}: {msg!r}")


def _check_memory_agreement(recalls, f):
    for name, engine_msg, mem_msg in recalls:
        e_bad = "not seen" in engine_msg.lower() or "haven't" in engine_msg.lower()
        m_bad = mem_msg is None or "not seen" in str(mem_msg).lower()
        if e_bad != m_bad:
            f.add("the two object memories disagree",
                  f"{name}: engine={engine_msg!r} memory={mem_msg!r}")


def _check_cadence(announcements, f):
    # An escalation (same object, now "very close") is ALLOWED to jump min_gap
    # down to escalation_min_gap — that is the safety override. Anything closer
    # than that floor is two sentences colliding.
    floor = GuidanceEngine().escalation_min_gap
    for (t0, m0), (t1, m1) in zip(announcements, announcements[1:]):
        gap = t1 - t0
        # An escalation is "the previous warning, but nearer". The NOUN can
        # legitimately change between the two — the hedge says "Obstacle" for
        # a weak first sighting and the real name once the class has earned it
        # — so this compares the proximity, not the first word.
        escalation = "very close" in m1 and "very close" not in m0
        limit = floor if escalation else 1.5
        if gap < limit - 1e-6:
            f.add("two announcements closer than the floor",
                  f"{t0:.1f}s {m0!r} then {t1:.1f}s {m1!r} "
                  f"(gap {gap:.2f}s, floor {limit}s)")
    if len(announcements) >= 2:
        span = announcements[-1][0] - announcements[0][0]
        if span > 0 and len(announcements) / span > 0.6:
            f.add("announcement rate above one per ~1.7 s",
                  f"{len(announcements)} in {span:.1f}s")


def _check_vocabulary(class_frames, f):
    for name in class_frames:
        if name not in TARGET_CLASSES:
            f.add("a class outside TARGET_CLASSES reached the engine", name)


def _colour_light(frame):
    h, w = frame.shape[:2]
    patch = frame[int(h * 0.4):int(h * 0.6), int(w * 0.4):int(w * 0.6)]
    b, g, r = (float(patch[:, :, i].mean()) for i in range(3))
    grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    luma = float(grey.mean()) / 255.0
    return colour_naming.colour_message(r, g, b), colour_naming.light_message(luma)


# ----------------------------------------------------------------------
def _write_report(out, path, src_fps, total, fps, sampled, with_dets,
                  infer_ms, class_frames, class_conf, renamed,
                  announcements, per_capability, recalls, f):
    L = []
    a = L.append
    a(f"# All-feature replay — {os.path.basename(path)}\n")
    a(f"source {total} frames @ {src_fps:.1f} fps; sampled {sampled} at "
      f"~{fps} fps (the handset's measured rate)")
    if infer_ms:
        a(f"detector {np.median(infer_ms):.0f} ms median, "
          f"{np.percentile(infer_ms, 95):.0f} ms p95 per frame")
    a(f"frames carrying a detection: {with_dets}/{sampled} "
      f"({100.0 * with_dets / max(sampled, 1):.0f}%)\n")

    a("## Classes seen\n")
    a("| class | frames | mean conf | max conf |")
    a("|---|---|---|---|")
    for name, n in class_frames.most_common():
        cs = class_conf[name]
        a(f"| {name} | {n} | {np.mean(cs):.2f} | {max(cs):.2f} |")
    a("")

    a("## Naming head\n")
    if renamed:
        for k, v in renamed.most_common():
            a(f"- {k} — {v} frames")
    else:
        a("- no renames (index has not been taught this room)")
    a("")

    a(f"## Walk announcements ({len(announcements)})\n")
    for t, m in announcements:
        a(f"- {t:6.1f}s  {m}")
    a("")

    a("## Capability outputs (distinct)\n")
    for cap in sorted(per_capability):
        seen = []
        for t, m in per_capability[cap]:
            if not seen or seen[-1][1] != m:
                seen.append((t, m))
        a(f"### {cap}  ({len(per_capability[cap])} calls, "
          f"{len(seen)} distinct)")
        for t, m in seen[:8]:
            a(f"- {t:6.1f}s  {m}")
        if len(seen) > 8:
            a(f"- ... {len(seen) - 8} more distinct")
        a("")

    a("## Recall at end of walk\n")
    for name, engine_msg, mem_msg in recalls:
        a(f"- **{name}** — engine: {engine_msg}")
        a(f"  - persistent memory: {mem_msg}")
    a("")

    a("## Anomalies\n")
    a(f.report())

    md = "\n".join(L)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(md)
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--fps", type=float, default=2.2,
                    help="sampling rate; 2.2 is the handset's measured rate")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--name-index", default="name_index.npz")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-frames", type=int, default=None)
    args = ap.parse_args()
    out = args.out or os.path.join(
        "test_output",
        f"replay_all_{os.path.splitext(os.path.basename(args.video))[0]}.md")
    replay(args.video, args.fps, args.imgsz, args.name_index, out,
           args.max_frames)


if __name__ == "__main__":
    main()
