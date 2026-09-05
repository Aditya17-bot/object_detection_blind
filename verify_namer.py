"""BlindAssist — verification harness for the embedding naming head.

Runs the real detection pipeline (yolov8s + the custom door/dustbin model)
over recorded clips with the naming head attached, and reports what it changed:

  * which YOLO names were replaced, by what, and how often;
  * how often it abstained, and why;
  * per-clip, so the FALSE-POSITIVE check is easy — point it at a clip
    containing none of the new classes and confirm it stays quiet.

That second check is the one that matters. The stairs class shipped at 0.072
recall with 0.68-0.91 confidence false positives on walls and ceilings, and had
to be pulled. A namer that confidently relabels a wall as a wardrobe repeats
that, so "renames nothing here" is a PASS, not a null result.

Run:
  venv-gpu/Scripts/python.exe verify_namer.py --index name_index.npz
  venv-gpu/Scripts/python.exe verify_namer.py --index n.npz --clips eval_a.mp4
"""
import argparse
import collections
import pathlib
import sys

import cv2

from harvest_crops import list_clips
from name_index import TRUSTED_KEY, Namer
from position import TARGET_CLASSES

COCO_CONF = 0.6      # mirrors infer_server.py
CUSTOM_CONF = 0.4


def run_clip(path, coco, custom, namer, stride, keep_all):
    """-> (renames Counter, abstain-reason Counter, frames, detections)."""
    cap = cv2.VideoCapture(str(path))
    renames = collections.Counter()
    reasons = collections.Counter()
    idx = frames = total_dets = 0
    namer.smoother.reset()          # each clip is an independent sequence
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            dets = []
            for model, conf, trusted in ((coco, COCO_CONF, False),
                                         (custom, CUSTOM_CONF, True)):
                if model is None:
                    continue
                res = model.predict(frame, conf=conf, imgsz=640,
                                    verbose=False)[0]
                for b in res.boxes:
                    name = model.names[int(b.cls)]
                    if not keep_all and name not in TARGET_CLASSES:
                        continue
                    x1, y1, x2, y2 = (float(t) for t in b.xyxyn[0])
                    det = {"name": name, "conf": float(b.conf),
                           "x1": x1, "y1": y1, "x2": x2, "y2": y2}
                    if trusted:
                        det[TRUSTED_KEY] = True
                    dets.append(det)
            decisions = namer.apply(frame, dets)
            for det, dec in zip(dets, decisions):
                if "yolo_name" in det:
                    renames[(det["yolo_name"], det["name"])] += 1
                elif dec.name is None:
                    reasons[dec.reason] += 1
            total_dets += len(dets)
            frames += 1
        idx += 1
    cap.release()
    return renames, reasons, frames, total_dets


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--index", default="name_index.npz")
    ap.add_argument("--clips", nargs="*",
                    help="clip paths; default = every clip in test_output/")
    ap.add_argument("--model", default="yolov8s.pt")
    ap.add_argument("--extra-model", default="door_dustbin_stairs.pt")
    ap.add_argument("--stride", type=int, default=2,
                    help="sample every Nth frame. Keep this SMALL: the "
                         "hysteresis tracker matches boxes between the frames "
                         "it is shown, so a coarse stride breaks tracks that "
                         "hold fine in live playback (eval_a gives 34 renames "
                         "at stride 1 and 1 at stride 10 — a sampling "
                         "artifact, not a namer failure)")
    ap.add_argument("--device", default=0)
    ap.add_argument("--min-sim", type=float, default=None)
    ap.add_argument("--min-margin", type=float, default=None,
                    help="override the shipped thresholds, e.g. to check the "
                         "sweep's recommended setting before adopting it")
    args = ap.parse_args(argv)

    from ultralytics import YOLO
    device = args.device if args.device == "cpu" else int(args.device)
    coco = YOLO(args.model)
    custom = None
    if pathlib.Path(args.extra_model).exists():
        custom = YOLO(args.extra_model)

    namer = Namer.maybe_load(args.index, coco, args.model,
                             vocabulary=TARGET_CLASSES)
    if namer is None:
        print("no usable index — nothing to verify")
        return 1
    namer.index.device = device
    if args.min_sim is not None:
        namer.index.min_sim = args.min_sim
    if args.min_margin is not None:
        namer.index.min_margin = args.min_margin
    print(f"thresholds: min_sim {namer.index.min_sim:.2f}, "
          f"min_margin {namer.index.min_margin:.2f}\n")

    clips = ([pathlib.Path(c) for c in args.clips] if args.clips
             else list_clips("test_output"))
    grand = collections.Counter()
    for clip in clips:
        renames, reasons, frames, dets = run_clip(clip, coco, custom, namer,
                                                  args.stride, keep_all=True)
        grand.update(renames)
        print(f"{clip.name}  ({frames} frames sampled, {dets} detections)")
        if renames:
            for (old, new), n in renames.most_common():
                print(f"    {old:>14s} -> {new:<12s} {n:4d}x")
        else:
            print("    no renames (correct if this clip has none of the "
                  "labelled objects)")
        if reasons:
            print("    abstained: " + ", ".join(f"{k} {v}" for k, v in
                                                reasons.most_common()))
        print()

    print("TOTAL renames across all clips:")
    for (old, new), n in grand.most_common():
        print(f"    {old:>14s} -> {new:<12s} {n:4d}x")
    return 0


if __name__ == "__main__":
    sys.exit(main())
