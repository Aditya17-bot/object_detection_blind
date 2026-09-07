"""Replay a walk as the user actually experiences it: guidance AND commands,
arbitrated by the real SpeechPolicy, on one timeline.

replay_all_features.py asks "is each capability's answer correct". This asks
the different question the field walks kept failing: given that the user speaks
while the app is speaking, WHAT DOES THE USER ACTUALLY HEAR, and in what order.
That is where the last three walks went wrong — a find answer clipped by
routine guidance, a command dropped because another task held focus, a page of
OCR text cut off mid-sentence.

Speech durations are estimated from word count so overlap is visible; the
estimate is stated in the report rather than hidden, because the policy's own
holds are estimates too.

    venv-gpu\\Scripts\\python.exe tools/replay_timeline.py ^
        test_output/field_walk_20260907.mp4
"""
import argparse
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import decision
import speech_policy
from decision import GuidanceEngine
from speech_policy import (CONFIRM, RESPONSE, ROUTINE, SAFETY, SpeechPolicy)
from tools.replay_all_features import (detect, infos_from, load_models)

# Words per second for the estimate. flutter_tts at the app's default rate
# lands around here; it only has to be close enough to show a collision.
WORDS_PER_SECOND = 2.6

# What the user says, and when. Chosen to hit the cases that broke in the
# field: a question during continuous guidance, a long read, a setting change,
# and a find that must not be talked over.
SCRIPT = [
    (3.0, "find", "bottle"),
    (7.0, "check", "left"),
    (11.0, "describe", None),
    (14.0, "read", None),
    (19.0, "count", "person"),
    (23.0, "path", None),
    (26.0, "recall", "door"),
]


def _speech_seconds(msg):
    return max(0.6, len(msg.split()) / WORDS_PER_SECOND)


def run(path, fps, imgsz, name_index, out_md):
    coco, custom, namer = load_models(name_index)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(src_fps / fps)))

    engine = GuidanceEngine()
    policy = SpeechPolicy()
    spoken = []          # (t, priority, tag, msg, seconds)
    dropped = []         # (t, reason, tag, msg)
    pending = list(SCRIPT)

    def say(t, msg, priority, tag, solicited):
        if not policy.allow_speech(priority, tag, t, solicited=solicited):
            dropped.append((t, f"speech gated (focus={policy.active_tag(t)})",
                            tag, msg))
            return False
        seconds = _speech_seconds(msg)
        # An answer owns the channel for as long as it takes to say it —
        # main.dart._say extends the hold for exactly this reason.
        if priority >= RESPONSE:
            policy.extend(tag, t, seconds * 1.5)
        spoken.append((t, priority, tag, msg, seconds))
        return True

    idx = -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1
        if idx % step:
            continue
        t = idx / src_fps
        h, w = frame.shape[:2]
        infos = infos_from(detect(frame, coco, custom, namer, imgsz), w, h)

        # -- the user speaks -------------------------------------------
        while pending and pending[0][0] <= t:
            at, action, arg = pending.pop(0)
            if not policy.allow_command(action, t, solicited=True):
                dropped.append((t, "COMMAND DROPPED", action,
                                f"{action} {arg or ''}".strip()))
                continue
            policy.begin(action, t)
            if action == "find":
                engine.set_mode("find", arg)
                say(t, f"Finding {arg}", CONFIRM, action, True)
            elif action == "check":
                msg = engine.check(infos, arg, t)
                say(t, msg or "…", RESPONSE, action, True)
            elif action == "describe":
                say(t, engine.describe(infos, t), RESPONSE, action, True)
            elif action == "count":
                say(t, engine.count(infos, arg, t), RESPONSE, action, True)
            elif action == "path":
                say(t, engine.path(infos, t), RESPONSE, action, True)
            elif action == "recall":
                say(t, engine.recall(arg, t), RESPONSE, action, True)
            elif action == "read":
                # OCR pauses the stream, captures, recognises: seconds of it
                say(t, "Reading. " + "word " * 40, RESPONSE, action, True)

        # -- guidance --------------------------------------------------
        msg = engine.update(infos, t)
        if msg:
            priority = SAFETY if "very close" in msg else ROUTINE
            tag = "walk" if engine.mode == "walk" else "find"
            say(t, msg, priority, tag, False)

    cap.release()

    # -- what actually overlapped ---------------------------------------
    collisions = []
    for (t0, p0, g0, m0, d0), (t1, p1, g1, m1, d1) in zip(spoken, spoken[1:]):
        if t1 < t0 + d0:
            collisions.append((t0, m0, d0, t1, m1, p1))

    L = []
    a = L.append
    a(f"# Timeline replay — {os.path.basename(path)}\n")
    a(f"speech length estimated at {WORDS_PER_SECOND} words/s; user commands "
      f"scripted at {[s[0] for s in SCRIPT]}\n")

    a("## What the user hears\n")
    names = {SAFETY: "SAFETY", RESPONSE: "RESPONSE", CONFIRM: "CONFIRM",
             ROUTINE: "routine"}
    for t, p, tag, msg, d in spoken:
        short = msg if len(msg) < 90 else msg[:87] + "..."
        a(f"- {t:6.1f}s  [{names[p]:8} {tag:9}] ({d:.1f}s)  {short}")
    a("")

    a(f"## Dropped ({len(dropped)})\n")
    for t, reason, tag, msg in dropped:
        short = msg if len(msg) < 80 else msg[:77] + "..."
        a(f"- {t:6.1f}s  {reason:38} {tag:9} {short}")
    a("")

    a(f"## Collisions — speech starting before the previous finished "
      f"({len(collisions)})\n")
    if not collisions:
        a("- none")
    for t0, m0, d0, t1, m1, p1 in collisions:
        cut = t0 + d0 - t1
        a(f"- {t0:.1f}s {m0[:50]!r} needs {d0:.1f}s but {t1:.1f}s "
          f"{'(' + names[p1] + ') ' if p1 else ''}{m1[:50]!r} cuts "
          f"{cut:.1f}s off it")
    a("")

    md = "\n".join(L)
    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(md)
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--fps", type=float, default=2.2)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--name-index", default="name_index.npz")
    ap.add_argument("--out", default="test_output/replay_timeline.md")
    args = ap.parse_args()
    run(args.video, args.fps, args.imgsz, args.name_index, args.out)


if __name__ == "__main__":
    main()
