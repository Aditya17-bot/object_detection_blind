"""BlindAssist — compare YOLOv8n vs YOLOv8s on identical webcam frames.

Captures N raw frames, runs both models on the same frames, prints
per-model detections and speed, saves side-by-side annotated images
to test_output/compare/.

Usage: python compare_models.py [--frames 6] [--conf 0.35]
(low conf on purpose: we want to SEE the weak/junk detections to compare)
"""

import argparse
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

OUT_DIR = Path(__file__).parent / "test_output" / "compare"


def capture_frames(n, warmup=5):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise SystemExit("Could not open webcam.")
    for _ in range(warmup):  # let exposure settle
        cap.read()
    frames = []
    while len(frames) < n:
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
        time.sleep(0.3)  # spread captures out a little
    cap.release()
    return frames


def run_model(name, frames, conf):
    model = YOLO(name)
    results, times = [], []
    model(frames[0], verbose=False)  # warmup, excluded from timing
    for f in frames:
        t = time.perf_counter()
        r = model(f, conf=conf, verbose=False)[0]
        times.append(time.perf_counter() - t)
        dets = [(r.names[int(b.cls[0])], round(float(b.conf[0]), 2))
                for b in r.boxes]
        results.append((r, dets))
    avg_ms = 1000 * sum(times) / len(times)
    return results, avg_ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=6)
    ap.add_argument("--conf", type=float, default=0.35)
    args = ap.parse_args()

    print(f"Capturing {args.frames} webcam frames...")
    frames = capture_frames(args.frames)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    summary = {}
    for model_name in ("yolov8n.pt", "yolov8s.pt"):
        print(f"\n=== {model_name} ===")
        results, avg_ms = run_model(model_name, frames, args.conf)
        summary[model_name] = avg_ms
        for i, (r, dets) in enumerate(results, 1):
            print(f"  frame {i}: {dets or 'nothing'}")
            annotated = r.plot()  # ultralytics' own box renderer
            cv2.imwrite(str(OUT_DIR / f"f{i:02d}_{model_name.split('.')[0]}.jpg"),
                        annotated)
        print(f"  avg inference: {avg_ms:.0f} ms/frame "
              f"(~{1000/avg_ms:.1f} FPS)")

    print("\nSpeed cost of upgrading: "
          f"{summary['yolov8s.pt']/summary['yolov8n.pt']:.1f}x slower")
    print(f"Annotated frames saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
