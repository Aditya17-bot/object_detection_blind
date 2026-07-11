"""BlindAssist — Phase 2 demo: detection + position analysis overlay.

Shows the 3x3 zone grid and labels every target object with what the
guidance layer will know about it:  name | direction phrase | proximity.

Usage:
    python phase2_detect.py                  # live webcam
    python phase2_detect.py --headless 10    # save frames to test_output/
    python phase2_detect.py --source img.jpg
Keys: q = quit, s = snapshot
"""

import argparse
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from position import TARGET_CLASSES, analyze_box

CONF_THRESHOLD = 0.6
DEFAULT_MODEL = "yolov8s.pt"

GREEN = (0, 200, 0)
ORANGE = (0, 140, 255)
RED = (0, 0, 230)
GRID = (200, 200, 200)
OUT_DIR = Path(__file__).parent / "test_output"

# closer objects get hotter box colors
PROX_COLOR = {"very close": RED, "close": ORANGE, "medium": GREEN, "far": GREEN}


def draw_grid(frame):
    h, w = frame.shape[:2]
    for i in (1, 2):
        cv2.line(frame, (w * i // 3, 0), (w * i // 3, h), GRID, 1)
        cv2.line(frame, (0, h * i // 3), (w, h * i // 3), GRID, 1)


def annotate(frame, result, conf_threshold):
    """Draw grid + analyzed target objects. Returns list of ObjectInfo."""
    draw_grid(frame)
    h, w = frame.shape[:2]
    infos = []
    for box in result.boxes:
        conf = float(box.conf[0])
        name = result.names[int(box.cls[0])]
        if conf < conf_threshold or name not in TARGET_CLASSES:
            continue
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
        info = analyze_box(name, conf, x1, y1, x2, y2, w, h)
        infos.append(info)
        color = PROX_COLOR[info.proximity]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{name} | {info.phrase} | {info.proximity}"
        cv2.putText(frame, label, (x1, max(y1 - 8, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    return infos


def main():
    ap = argparse.ArgumentParser(description="BlindAssist Phase 2 demo")
    ap.add_argument("--source", default="0")
    ap.add_argument("--headless", type=int, default=0, metavar="N")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--conf", type=float, default=CONF_THRESHOLD)
    args = ap.parse_args()

    print(f"Loading {args.model}...")
    model = YOLO(args.model)
    OUT_DIR.mkdir(exist_ok=True)

    if args.source.isdigit():
        cap = cv2.VideoCapture(int(args.source))
    elif args.source.lower().startswith(("http://", "https://", "rtsp://")):
        # phone camera stream, e.g. IP Webcam app: http://<phone-ip>:8080/video
        cap = cv2.VideoCapture(args.source)
    else:
        src = Path(args.source)
        if src.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
            frame = cv2.imread(str(src))
            infos = annotate(frame, model(frame, verbose=False)[0], args.conf)
            for i in infos:
                print(f"  {i.name}: {i.phrase}, {i.proximity} "
                      f"(conf {i.confidence:.2f}, area {i.area:.3f})")
            out = OUT_DIR / f"phase2_{src.stem}.jpg"
            cv2.imwrite(str(out), frame)
            print(f"Saved {out}")
            return
        cap = cv2.VideoCapture(str(src))

    if not cap.isOpened():
        raise SystemExit(f"Could not open source {args.source!r}")
    n = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            infos = annotate(frame, model(frame, verbose=False)[0], args.conf)
            n += 1
            if args.headless:
                desc = [f"{i.name}: {i.phrase}, {i.proximity}" for i in infos]
                print(f"frame {n}: {desc or 'no targets'}")
                cv2.imwrite(str(OUT_DIR / f"phase2_headless_{n:03d}.jpg"), frame)
                if n >= args.headless:
                    break
            else:
                cv2.imshow("BlindAssist Phase 2 (q=quit, s=snapshot)", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("s"):
                    snap = OUT_DIR / f"phase2_snap_{int(time.time())}.jpg"
                    cv2.imwrite(str(snap), frame)
                    print(f"Saved {snap}")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
