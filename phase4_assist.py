"""BlindAssist — Phase 4: the full assistant. Camera -> YOLO -> position ->
decision -> SPOKEN guidance.

Same pipeline and flags as phase3_detect.py, but every announcement the
GuidanceEngine picks is actually spoken (pyttsx3 on its own thread, so the
camera loop never waits for the voice). If a new announcement arrives while
the voice is busy, it replaces the waiting one — stale guidance is never
spoken.

Usage:
    python phase4_assist.py                            # walk mode, webcam
    python phase4_assist.py --source http://<phone-ip>:8080/video
    python phase4_assist.py --mode find --target bottle
    python phase4_assist.py --source clip.mp4          # speaks over the clip
    python phase4_assist.py --mute                     # print-only dry run
Keys: q = quit, s = snapshot, d = describe scene (spoken summary)
"""

import argparse
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from decision import GuidanceEngine
from phase2_detect import CONF_THRESHOLD, DEFAULT_MODEL, OUT_DIR, annotate
from phase3_detect import IMAGE_EXTS, draw_banner, open_source, run_still_image
from position import FIND_CLASSES, TARGET_CLASSES
from speech import Speaker


def main():
    ap = argparse.ArgumentParser(description="BlindAssist Phase 4 assistant")
    ap.add_argument("--source", default="0",
                    help="webcam index, video/image file, or http/rtsp URL")
    ap.add_argument("--mode", choices=("walk", "find"), default="walk")
    ap.add_argument("--target", help="class to look for in find mode",
                    choices=sorted(TARGET_CLASSES))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--conf", type=float, default=CONF_THRESHOLD)
    ap.add_argument("--rate", type=int, default=175,
                    help="speech rate, words per minute")
    ap.add_argument("--mute", action="store_true",
                    help="print announcements instead of speaking")
    args = ap.parse_args()

    if args.mode == "find" and not args.target:
        ap.error("--mode find requires --target "
                 f"(e.g. --target bottle; find classes: {sorted(FIND_CLASSES)})")

    print(f"Loading {args.model}...")
    model = YOLO(args.model)
    OUT_DIR.mkdir(exist_ok=True)
    speaker = None if args.mute else Speaker(rate=args.rate)

    def announce(text):
        if speaker:
            speaker.say(text)

    try:
        if Path(args.source).suffix.lower() in IMAGE_EXTS:
            msg = run_still_image(model, args)
            announce(msg)
            return

        cap, source_name, is_file = open_source(args.source)
        if not cap.isOpened():
            raise SystemExit(f"Could not open source {args.source!r}")
        # speech happens in real time, so the engine clock is real time too —
        # even for clips (unlike phase3's reproducible video-time logs)
        engine = GuidanceEngine(mode=args.mode, target=args.target)
        log_path = OUT_DIR / f"phase4_{source_name}_{args.mode}.log"
        log = open(log_path, "w", encoding="utf-8")
        print(f"Mode: {args.mode}"
              + (f" (target: {args.target})" if args.target else "")
              + (" [muted]" if args.mute else ""))

        n = 0
        last_banner = "..."
        t0 = time.monotonic()
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                t = time.monotonic() - t0
                infos = annotate(frame, model(frame, verbose=False)[0],
                                 args.conf)
                msg = engine.update(infos, t)
                if msg:
                    line = f"[{t:6.2f}s frame {n:4d}] SAY: {msg}"
                    print(line)
                    log.write(line + "\n")
                    announce(msg)
                    last_banner = msg
                draw_banner(frame, last_banner, fresh=bool(msg))
                n += 1
                cv2.imshow("BlindAssist (q=quit, s=snap, d=describe)", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("s"):
                    snap = OUT_DIR / f"phase4_snap_{int(time.time())}.jpg"
                    cv2.imwrite(str(snap), frame)
                    print(f"Saved {snap}")
                if key == ord("d"):
                    summary = engine.describe(infos, t)
                    line = f"[{t:6.2f}s frame {n:4d}] SAY: {summary}"
                    print(line)
                    log.write(line + "\n")
                    announce(summary)
                    last_banner = summary
        finally:
            cap.release()
            cv2.destroyAllWindows()
            log.close()
        print(f"\n{n} frames processed. Announcement log: {log_path}")
    finally:
        if speaker:
            speaker.wait_until_idle()
            speaker.close()


if __name__ == "__main__":
    main()
