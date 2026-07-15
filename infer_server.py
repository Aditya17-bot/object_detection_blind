"""BlindAssist remote inference server.

The phone (Flutter app) can't run YOLO in real time on its Exynos 990 (measured
~2.5 s/inference for both the GPU and NNAPI delegates — see CLAUDE.md). So the
phone ships each camera frame's RAW YUV420 planes here and this server does the
heavy work: reconstruct BGR, run yolov8s (strong model) + the custom
door/dustbin model, return the detections as JSON. On this laptop that is
~140 ms/frame, so the phone gets real-time guidance over Wi-Fi while keeping
ALL its native features (sonar, haptics, voice, OCR).

Protocol — POST /infer, multipart/form-data:
  fields: width height yStride uvStride uvPixelStride rotation   (ints)
  files : y u v                                                  (raw plane bytes)
Response JSON: {"detections": [{"name","conf","x1","y1","x2","y2"}, ...]}
  boxes are normalized 0..1 in the UPRIGHT (rotated) frame — exactly the
  coordinate space the app's ObjectInfo expects.

Run:  python infer_server.py --host 0.0.0.0
Then point the app's kServerHost at this laptop's LAN IP.
"""
import argparse
import time

import cv2
import numpy as np
from flask import Flask, jsonify, request
from ultralytics import YOLO

from position import TARGET_CLASSES

# yolov8s is the strong model (nano was the phone's weak spot); door/dustbin
# come from the dedicated custom model. Conf floors mirror the tuned webapp
# values (door/dustbin 0.4 — a partial/far doorway lives in the 0.4-0.5 band).
COCO_CONF = 0.6
CUSTOM_CONF = 0.4
_CUSTOM_FLOOR = {"door": 0.4, "dustbin": 0.4}

# Android sensorOrientation -> cv2 rotation. Derived to MATCH detector.dart's
# _fillInput mapping so left/right (and therefore every direction announced)
# is identical to the on-device path: rotation 90 == ROTATE_90_CLOCKWISE.
_ROT = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def yuv420_to_bgr(y, u, v, w, h, y_stride, uv_stride, uv_pixel_stride):
    """Reconstruct a BGR image from Android YUV420_888 planes. Same color
    coefficients as detector.dart so the pixels match the on-device pipeline."""
    yb = np.frombuffer(y, np.uint8)
    ub = np.frombuffer(u, np.uint8)
    vb = np.frombuffer(v, np.uint8)
    Y = yb[:h * y_stride].reshape(h, y_stride)[:, :w].astype(np.float32)
    rows = (np.arange(h) >> 1)
    cols = (np.arange(w) >> 1)
    uv_idx = rows[:, None] * uv_stride + cols[None, :] * uv_pixel_stride
    uv_idx = np.clip(uv_idx, 0, min(len(ub), len(vb)) - 1)
    U = ub[uv_idx].astype(np.float32) - 128.0
    V = vb[uv_idx].astype(np.float32) - 128.0
    R = Y + 1.402 * V
    G = Y - 0.344136 * U - 0.714136 * V
    B = Y + 1.772 * U
    bgr = np.clip(np.stack([B, G, R], axis=-1), 0, 255).astype(np.uint8)
    return bgr


def build_app(coco_path="yolov8s.pt", custom_path="door_dustbin_stairs.pt"):
    app = Flask(__name__)
    coco = YOLO(coco_path)
    try:
        custom = YOLO(custom_path)
        print(f"Custom model loaded: {sorted(custom.names.values())}")
    except Exception as exc:  # noqa: BLE001 — app still useful with COCO only
        custom = None
        print(f"Custom model unavailable ({exc}) — COCO classes only")

    def _collect(result, names, conf_floor):
        out = []
        for b in result.boxes:
            name = names[int(b.cls)]
            conf = float(b.conf)
            if name not in TARGET_CLASSES:
                continue
            if conf < _CUSTOM_FLOOR.get(name, conf_floor):
                continue
            x1, y1, x2, y2 = (float(t) for t in b.xyxyn[0])
            out.append({"name": name, "conf": conf,
                        "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        return out

    @app.post("/infer")
    def infer():
        t0 = time.monotonic()
        f = request.form
        w = int(f["width"])
        h = int(f["height"])
        rotation = int(f.get("rotation", 0))
        frame = yuv420_to_bgr(
            request.files["y"].read(), request.files["u"].read(),
            request.files["v"].read(), w, h,
            int(f["yStride"]), int(f["uvStride"]), int(f["uvPixelStride"]))
        if rotation in _ROT:
            frame = cv2.rotate(frame, _ROT[rotation])

        dets = _collect(coco.predict(frame, conf=COCO_CONF, verbose=False)[0],
                        coco.names, COCO_CONF)
        if custom is not None:
            dets += _collect(
                custom.predict(frame, conf=CUSTOM_CONF, verbose=False)[0],
                custom.names, CUSTOM_CONF)
        ms = (time.monotonic() - t0) * 1000
        print(f"/infer {w}x{h} rot{rotation} -> {len(dets)} dets in {ms:.0f}ms")
        return jsonify({"detections": dets})

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "custom": custom is not None})

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0",
                    help="0.0.0.0 exposes on the LAN for the phone")
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument("--model", default="yolov8s.pt")
    ap.add_argument("--extra-model", default="door_dustbin_stairs.pt")
    args = ap.parse_args()
    app = build_app(args.model, args.extra_model)
    print(f"BlindAssist inference server on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True)
