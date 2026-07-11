"""BlindAssist — Phase 3 demo: detection + position + DECISION logic.

Adds the guidance layer on top of the phase 2 overlay: every frame runs
through GuidanceEngine and the ONE chosen announcement (if any) is printed,
logged, and drawn as a banner — exactly what the TTS will speak in phase 4.

Recorded clips are timed by video time (frame / fps), not wall time, so
cooldown behaviour is reproducible no matter how fast the machine is.

Usage:
    python phase3_detect.py                            # walk mode, webcam
    python phase3_detect.py --source clip.mp4          # whole clip, windowed
    python phase3_detect.py --source clip.mp4 --headless   # whole clip, no window
    python phase3_detect.py --mode find --target bottle --source clip.mp4
    python phase3_detect.py --source http://<phone-ip>:8080/video
Keys: q = quit, s = snapshot, d = describe scene (summary announcement)

Announcements are appended to test_output/phase3_<source>_<mode>.log and an
annotated frame is saved per announcement for review.
"""

import argparse
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from decision import (GuidanceEngine, find_message, find_target,
                      pick_obstacle, summarize_scene, walk_message)
from phase2_detect import CONF_THRESHOLD, DEFAULT_MODEL, OUT_DIR, annotate
from position import FIND_CLASSES, TARGET_CLASSES

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

BANNER_FRESH = (0, 255, 255)   # just announced
BANNER_STALE = (200, 200, 200)  # still showing last announcement


def draw_banner(frame, text, fresh):
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, h - 42), (w, h), (0, 0, 0), -1)
    cv2.putText(frame, text, (10, h - 13), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, BANNER_FRESH if fresh else BANNER_STALE, 2)


def open_source(source):
    """cv2.VideoCapture for webcam index / stream URL / video file.
    Returns (capture, source_name, is_file)."""
    if source.isdigit():
        return cv2.VideoCapture(int(source)), f"webcam{source}", False
    if source.lower().startswith(("http://", "https://", "rtsp://")):
        return cv2.VideoCapture(source), "stream", False
    path = Path(source)
    return cv2.VideoCapture(str(path)), path.stem, True


def run_still_image(model, args):
    """Single image: no cooldown state to exercise, so show the one-shot
    decision plus the scene summary."""
    frame = cv2.imread(args.source)
    if frame is None:
        raise SystemExit(f"Could not read image {args.source!r}")
    infos = annotate(frame, model(frame, verbose=False)[0], args.conf)
    for i in infos:
        print(f"  {i.name}: {i.phrase}, {i.proximity} (conf {i.confidence:.2f})")
    print(f"Scene: {summarize_scene(infos)}")
    if args.mode == "walk":
        obstacle = pick_obstacle(infos)
        msg = walk_message(obstacle, infos) if obstacle else "(no obstacle to warn about)"
    else:
        msg = find_message(find_target(infos, args.target), args.target)
    print(f"SAY: {msg}")
    draw_banner(frame, msg, fresh=True)
    out = OUT_DIR / f"phase3_{Path(args.source).stem}.jpg"
    cv2.imwrite(str(out), frame)
    print(f"Saved {out}")
    return msg


def main():
    ap = argparse.ArgumentParser(description="BlindAssist Phase 3 demo")
    ap.add_argument("--source", default="0",
                    help="webcam index, video/image file, or http/rtsp URL")
    ap.add_argument("--mode", choices=("walk", "find"), default="walk")
    ap.add_argument("--target", help="class to look for in find mode",
                    choices=sorted(TARGET_CLASSES))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--conf", type=float, default=CONF_THRESHOLD)
    ap.add_argument("--headless", nargs="?", type=int, const=0, default=None,
                    metavar="N", help="no window; process N frames "
                    "(default: whole clip for files)")
    args = ap.parse_args()

    if args.mode == "find" and not args.target:
        ap.error("--mode find requires --target "
                 f"(e.g. --target bottle; find classes: {sorted(FIND_CLASSES)})")

    print(f"Loading {args.model}...")
    model = YOLO(args.model)
    OUT_DIR.mkdir(exist_ok=True)

    if Path(args.source).suffix.lower() in IMAGE_EXTS:
        run_still_image(model, args)
        return

    cap, source_name, is_file = open_source(args.source)
    if not cap.isOpened():
        raise SystemExit(f"Could not open source {args.source!r}")
    if args.headless is not None and args.headless == 0 and not is_file:
        raise SystemExit("--headless needs a frame count N for live sources")

    fps = cap.get(cv2.CAP_PROP_FPS) if is_file else 0
    if not fps or fps != fps:  # 0 or NaN -> sensible default
        fps = 30.0

    engine = GuidanceEngine(mode=args.mode, target=args.target)
    log_path = OUT_DIR / f"phase3_{source_name}_{args.mode}.log"
    log = open(log_path, "w", encoding="utf-8")
    print(f"Mode: {args.mode}"
          + (f" (target: {args.target})" if args.target else ""))

    n = 0
    last_banner = "..."
    t0 = time.monotonic()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = n / fps if is_file else time.monotonic() - t0
            infos = annotate(frame, model(frame, verbose=False)[0], args.conf)
            msg = engine.update(infos, t)
            if msg:
                line = f"[{t:6.2f}s frame {n:4d}] SAY: {msg}"
                print(line)
                log.write(line + "\n")
                last_banner = msg
                snap = OUT_DIR / f"phase3_{source_name}_{args.mode}_f{n:04d}.jpg"
                draw_banner(frame, msg, fresh=True)
                cv2.imwrite(str(snap), frame)
            else:
                draw_banner(frame, last_banner, fresh=False)
            n += 1
            if args.headless is not None:
                if args.headless and n >= args.headless:
                    break
            else:
                cv2.imshow("BlindAssist Phase 3 (q=quit, s=snap, d=describe)",
                           frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("s"):
                    snap = OUT_DIR / f"phase3_snap_{int(time.time())}.jpg"
                    cv2.imwrite(str(snap), frame)
                    print(f"Saved {snap}")
                if key == ord("d"):
                    summary = engine.describe(infos, t)
                    line = f"[{t:6.2f}s frame {n:4d}] SAY: {summary}"
                    print(line)
                    log.write(line + "\n")
                    last_banner = summary
    finally:
        cap.release()
        cv2.destroyAllWindows()
        log.close()
    print(f"\n{n} frames processed. Announcement log: {log_path}")


if __name__ == "__main__":
    main()
