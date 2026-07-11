"""BlindAssist — Phase 1: webcam + YOLOv8n detection sanity check.

Usage:
    python phase1_detect.py                  # live webcam with drawn boxes
    python phase1_detect.py --source img.jpg # single image (shows + saves result)
    python phase1_detect.py --source clip.mp4
    python phase1_detect.py --headless 30    # no window: grab 30 webcam frames,
                                             # save annotated ones to test_output/

Keys (live mode):  q = quit,  s = save snapshot to test_output/
"""

import argparse
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from position import TARGET_CLASSES  # single source of truth for classes
# False alarms are worse than misses for a blind user, so threshold is high.
CONF_THRESHOLD = 0.6
DEFAULT_MODEL = "yolov8s.pt"

GREEN = (0, 200, 0)
GRAY = (140, 140, 140)
OUT_DIR = Path(__file__).parent / "test_output"


def annotate(frame, result):
    """Draw detection boxes. Returns (frame, list of (name, conf) for targets)."""
    targets_found = []
    names = result.names
    for box in result.boxes:
        conf = float(box.conf[0])
        if conf < CONF_THRESHOLD:
            continue
        name = names[int(box.cls[0])]
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
        is_target = name in TARGET_CLASSES
        color = GREEN if is_target else GRAY
        thickness = 2 if is_target else 1
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
        label = f"{name} {conf:.2f}"
        cv2.putText(frame, label, (x1, max(y1 - 8, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        if is_target:
            targets_found.append((name, conf))
    return frame, targets_found


def run_image(model, path):
    frame = cv2.imread(str(path))
    if frame is None:
        raise SystemExit(f"Could not read image: {path}")
    result = model(frame, verbose=False)[0]
    frame, targets = annotate(frame, result)
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"result_{Path(path).stem}.jpg"
    cv2.imwrite(str(out), frame)
    print(f"Targets detected: {targets or 'none'}")
    print(f"Saved annotated image to {out}")


def run_stream(model, source, headless_frames=0):
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise SystemExit(f"Could not open video source: {source!r}. "
                         "If this is a webcam, check it isn't in use elsewhere.")
    OUT_DIR.mkdir(exist_ok=True)
    frame_count, t0 = 0, time.time()
    fps = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("End of stream.")
                break
            result = model(frame, verbose=False)[0]
            frame, targets = annotate(frame, result)

            frame_count += 1
            elapsed = time.time() - t0
            if elapsed > 0.5:
                fps = frame_count / elapsed
            cv2.putText(frame, f"{fps:.1f} FPS", (10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 160, 255), 2)

            if headless_frames:
                out = OUT_DIR / f"headless_{frame_count:03d}.jpg"
                cv2.imwrite(str(out), frame)
                print(f"frame {frame_count}: {fps:.1f} FPS, targets: {targets or 'none'}")
                if frame_count >= headless_frames:
                    break
            else:
                cv2.imshow("BlindAssist Phase 1 (q=quit, s=snapshot)", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("s"):
                    snap = OUT_DIR / f"snapshot_{int(time.time())}.jpg"
                    cv2.imwrite(str(snap), frame)
                    print(f"Saved {snap}")
    finally:
        cap.release()
        cv2.destroyAllWindows()
    print(f"Average FPS: {fps:.1f}")


def main():
    global CONF_THRESHOLD
    ap = argparse.ArgumentParser(description="BlindAssist Phase 1 detection test")
    ap.add_argument("--source", default="0",
                    help="0 for webcam (default), or path to image/video")
    ap.add_argument("--headless", type=int, default=0, metavar="N",
                    help="no window; process N frames and save to test_output/")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="e.g. yolov8n.pt (fastest) or yolov8s.pt (more accurate)")
    ap.add_argument("--conf", type=float, default=CONF_THRESHOLD)
    args = ap.parse_args()

    CONF_THRESHOLD = args.conf
    print(f"Loading {args.model} (conf threshold {args.conf})...")
    model = YOLO(args.model)

    src = args.source
    if src.isdigit():
        run_stream(model, int(src), args.headless)
    elif Path(src).suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        run_image(model, src)
    else:
        run_stream(model, src, args.headless)


if __name__ == "__main__":
    main()
