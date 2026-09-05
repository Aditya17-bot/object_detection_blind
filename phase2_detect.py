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

from name_index import TRUSTED_KEY
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


def collect_dets(result, conf_threshold, frame_w, frame_h, keep_all=False,
                 trusted=False):
    """Raw detections as plain dicts, before any position analysis.

    Carries BOTH normalized coords (what the naming head and the phone
    protocol use) and the original pixel box (what analyze_box wants), so
    nothing is lost to a round trip through floats.

    keep_all skips the TARGET_CLASSES filter — required when a naming head is
    active, because the boxes worth renaming are precisely the ones YOLO gave a
    word we don't target ("vase" for a dustbin), and filtering first throws
    them away.

    trusted marks detections the naming head must not touch — used for the
    dedicated door/dustbin model, whose classes exist because COCO had no word
    for them, so there is no forced-choice error to correct.
    """
    dets = []
    for box in result.boxes:
        conf = float(box.conf[0])
        name = result.names[int(box.cls[0])]
        if conf < conf_threshold:
            continue
        if not keep_all and name not in TARGET_CLASSES:
            continue
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
        det = {"name": name, "conf": conf, "px": (x1, y1, x2, y2),
               "x1": x1 / frame_w, "y1": y1 / frame_h,
               "x2": x2 / frame_w, "y2": y2 / frame_h}
        if trusted:
            det[TRUSTED_KEY] = True
        dets.append(det)
    return dets


def apply_namer(namer, clean_frame, dets):
    """Rename in place, then drop anything the app has no vocabulary for.

    Call this ONCE per frame over the merged detections of every model: the
    namer's hysteresis tracks boxes between frames, and calling it per model
    would have each pass overwrite the other's tracks.
    """
    if namer is None:
        return dets
    namer.apply(clean_frame, dets)
    return [d for d in dets if d["name"] in TARGET_CLASSES]


def infos_from_dets(dets, frame_w, frame_h):
    """Position analysis for each detection, carrying the name-trust flag
    through: a dedicated-model class or a committed rename from the naming
    head must not be re-gated on detector confidence downstream."""
    return [analyze_box(d["name"], d["conf"], *d["px"], frame_w, frame_h,
                        trusted_name=bool(d.get(TRUSTED_KEY)))
            for d in dets]


def draw_dets(frame, dets, infos):
    """Boxes + labels. A renamed detection shows what YOLO had called it —
    the demo UI is where that substitution has to be visible."""
    for det, info in zip(dets, infos):
        x1, y1, x2, y2 = det["px"]
        color = PROX_COLOR[info.proximity]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        name = info.name
        if "yolo_name" in det:
            name = f"{name} (was {det['yolo_name']})"
        label = f"{name} | {info.phrase} | {info.proximity}"
        cv2.putText(frame, label, (x1, max(y1 - 8, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)


def annotate(frame, result, conf_threshold, namer=None, clean=None):
    """Draw grid + analyzed target objects. Returns list of ObjectInfo.

    `clean` is an un-drawn-on copy of the frame; the naming head must embed
    those pixels, not ones with boxes and grid lines burned into them.
    """
    draw_grid(frame)
    h, w = frame.shape[:2]
    dets = collect_dets(result, conf_threshold, w, h,
                        keep_all=namer is not None)
    dets = apply_namer(namer, clean if clean is not None else frame, dets)
    infos = infos_from_dets(dets, w, h)
    draw_dets(frame, dets, infos)
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
