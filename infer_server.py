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
import socket
import threading
import time

import cv2
import numpy as np
from flask import Flask, jsonify, request
from ultralytics import YOLO

from agent_server import register_agent_routes
from detect_merge import merge_detections, merge_report
from name_index import TRUSTED_KEY, Namer
from position import TARGET_CLASSES

# yolov8s is the strong model (nano was the phone's weak spot); door/dustbin
# come from the dedicated custom model. Conf floors mirror the tuned webapp
# values (door/dustbin 0.4 — a partial/far doorway lives in the 0.4-0.5 band).
COCO_CONF = 0.6
CUSTOM_CONF = 0.4
# Per-class floors for the custom model. The 0.4 was chosen for DOORS, where a
# partial or far doorway genuinely lives in the 0.4-0.5 band, and dustbin
# inherited it without ever being justified for that class. Raised to 0.6 on
# 2026-09-05: the dustbin head is the weak one (see CLAUDE.md, and the stairs
# class was disabled outright for the same reason), and the field log for one
# frame was
#     suitcase@0.91 backpack@0.70 dustbin@0.81 dustbin@0.70 dustbin@0.46
# -- three dustbin boxes, two of them barely over the old floor, on an object
# the user knows is a suitcase. The confident false positive at 0.81 survives
# this and is a NAMING problem, not a threshold one; only labelled crops of
# this room fix that.
_CUSTOM_FLOOR = {"door": 0.4, "dustbin": 0.6}

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
    # Android commonly ships the Y plane as (h-1)*stride + w bytes — the LAST
    # row is not padded out to the stride. Pad so the reshape below can't
    # crash; padded bytes land past [:, :w] of the final row and are never read.
    if len(yb) < h * y_stride:
        yb = np.pad(yb, (0, h * y_stride - len(yb)))
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


# --- UDP auto-discovery -----------------------------------------------------
# The hotspot IP changes every session; baking it into the app meant an APK
# rebuild per session. Instead the app broadcasts DISCOVER_MSG on
# DISCOVERY_PORT and we reply with the HTTP port — the app takes the server's
# IP from the reply packet itself.
DISCOVERY_PORT = 5002
DISCOVER_MSG = b"BLINDASSIST_DISCOVER"
REPLY_PREFIX = b"BLINDASSIST_INFER "


def start_discovery_responder(http_port, port=DISCOVERY_PORT):
    """Listen for app discovery broadcasts, reply with our HTTP port.
    Returns the socket (tests close it; the daemon thread dies with it)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))

    def _serve():
        while True:
            try:
                data, addr = sock.recvfrom(64)
            except OSError:  # socket closed — shut down
                return
            if data.strip() == DISCOVER_MSG:
                sock.sendto(REPLY_PREFIX + str(http_port).encode(), addr)
                print(f"discovery ping from {addr[0]} — replied")

    threading.Thread(target=_serve, daemon=True).start()
    return sock


_AUTO = object()  # sentinel: custom_model=None must mean "explicitly none"


def build_app(coco_path="yolov8s.pt", custom_path="door_dustbin_stairs.pt",
              coco_model=None, custom_model=_AUTO, imgsz=640,
              router=None, transcriber=None, name_index=None, namer=None,
              summary_llm=None):
    """coco_model/custom_model override the paths — lets tests inject fakes
    without loading real weights (same pattern as test_webapp.py).
    custom_model=None disables the custom model; leaving it unset loads
    custom_path as usual. imgsz is the inference resolution: 640 is the
    models' native size; 480 measured ~1.6x faster on this laptop
    (747 -> 470 ms/frame both models, 2026-07-16) at a small accuracy cost —
    the latency knob when frames time out."""
    app = Flask(__name__)
    coco = coco_model if coco_model is not None else YOLO(coco_path)
    custom = None if custom_model is _AUTO else custom_model
    if custom_model is _AUTO:
        try:
            custom = YOLO(custom_path)
            print(f"Custom model loaded: {sorted(custom.names.values())}")
        except Exception as exc:  # noqa: BLE001 — app still useful COCO-only
            custom = None
            print(f"Custom model unavailable ({exc}) — COCO classes only")

    # Naming head: YOLO decides WHERE, this decides WHAT. Optional — with no
    # index file the server behaves exactly as it did before, which is also the
    # state every test that doesn't ask for one runs in.
    if namer is None and name_index:
        namer = Namer.maybe_load(name_index, coco, coco_path,
                                 vocabulary=TARGET_CLASSES)

    # Warm up now, not on the first phone frame: the first predict pays
    # torch/ultralytics graph init (1-2 s), which would blow the app's 1.2 s
    # frame timeout and make the first user experience a spoken failure.
    dummy = np.zeros((640, 640, 3), np.uint8)
    coco.predict(dummy, conf=COCO_CONF, imgsz=imgsz, verbose=False)
    if custom is not None:
        custom.predict(dummy, conf=CUSTOM_CONF, imgsz=imgsz, verbose=False)
    if namer is not None:
        # the first embed() pays the same graph-init cost as the first predict
        namer.index.classify_crops([dummy[:64, :64]])
        namer.smoother.reset()

    # Serialize inference: ultralytics predict is not thread-safe, and when
    # the phone times out and abandons a request the server keeps computing
    # it — without a lock the NEXT frame runs concurrently on the same model
    # and both slow down. Uncontended in normal one-frame-at-a-time operation.
    infer_lock = threading.Lock()

    def _collect(result, names, conf_floor, keep_all=False, trusted=False):
        out = []
        for b in result.boxes:
            name = names[int(b.cls)]
            conf = float(b.conf)
            # With a naming head active the class filter moves to AFTER
            # naming: a dustbin YOLO calls "vase" has to reach the namer, and
            # this filter would have thrown the box away first.
            if not keep_all and name not in TARGET_CLASSES:
                continue
            if conf < _CUSTOM_FLOOR.get(name, conf_floor):
                continue
            x1, y1, x2, y2 = (float(t) for t in b.xyxyn[0])
            det = {"name": name, "conf": conf,
                   "x1": x1, "y1": y1, "x2": x2, "y2": y2}
            if trusted:
                det[TRUSTED_KEY] = True
            out.append(det)
        return out

    @app.post("/infer")
    def infer():
        t0 = time.monotonic()
        f = request.form
        w = int(f["width"])
        h = int(f["height"])
        rotation = int(f.get("rotation", 0))
        # Two frame shapes, and the app picks per frame.
        #
        # "jpeg" is the normal one since 2026-09-05: the phone's hardware
        # encoder ships ~45 KB instead of the ~506 KB of raw planes. That
        # upload was measured at 320-510 ms on the user's hotspot against
        # ~171 ms for all inference here, and it was losing frames to the
        # app's 1.2 s timeout — which breaks the guidance engine's two-frame
        # persistence and makes announcements erratic.
        #
        # The raw "y"/"u"/"v" planes remain supported so an older APK, or a
        # handset whose platform channel fails, still works.
        if "jpeg" in request.files:
            buf = np.frombuffer(request.files["jpeg"].read(), np.uint8)
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if frame is None:
                return jsonify({"error": "undecodable jpeg"}), 400
        else:
            frame = yuv420_to_bgr(
                request.files["y"].read(), request.files["u"].read(),
                request.files["v"].read(), w, h,
                int(f["yStride"]), int(f["uvStride"]),
                int(f["uvPixelStride"]))
        if rotation in _ROT:
            frame = cv2.rotate(frame, _ROT[rotation])

        keep_all = namer is not None
        with infer_lock:
            dets = _collect(
                coco.predict(frame, conf=COCO_CONF, imgsz=imgsz,
                             verbose=False)[0],
                coco.names, COCO_CONF, keep_all)
            if custom is not None:
                dets += _collect(
                    custom.predict(frame, conf=CUSTOM_CONF, imgsz=imgsz,
                                   verbose=False)[0],
                    custom.names, CUSTOM_CONF, keep_all, trusted=True)
            if namer is not None:
                namer.apply(frame, dets)
                # Names the app doesn't know fail SILENTLY downstream (wrong
                # proximity thresholds, no metres, never walk-warned), so the
                # class filter is applied here instead — after the namer has
                # had its say, on the name the user will actually hear.
                dets = [d for d in dets if d["name"] in TARGET_CLASSES]
        # Both models NMS only their OWN output, so one object could be
        # returned twice under two names ("my suitcase is shown as both
        # dustbin and suitcase"). Merged AFTER naming, so the naming head's
        # verdict is available as a tie-break and it still sees every box.
        before = dets
        dets = merge_detections(
            dets, floors=dict(_CUSTOM_FLOOR), default_floor=COCO_CONF)
        merged = merge_report(before, dets)
        ms = (time.monotonic() - t0) * 1000
        renamed = sum(1 for d in dets if "yolo_name" in d)
        kind = "jpeg" if "jpeg" in request.files else "raw"
        print(f"/infer {w}x{h} rot{rotation} {kind} -> {len(dets)} dets "
              f"in {ms:.0f}ms"
              + (f" ({renamed} renamed)" if renamed else "")
              + (f" [{merged}]" if merged else ""))
        return jsonify({"detections": dets})

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "custom": custom is not None,
                        "namer": namer is not None,
                        "agent": router is not None and router.enabled})

    # POST /agent — the phone posts an utterance (typed) or a WAV of the
    # dictation window; we transcribe and route, and the phone EXECUTES the
    # returned actions locally. Deliberately no execution here: this server
    # has no GuidanceEngine and no frame state, and inventing one would put a
    # second source of truth behind the user's ear.
    if router is not None:
        register_agent_routes(app, router, transcriber,
                              summary_llm=summary_llm)

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0",
                    help="0.0.0.0 exposes on the LAN for the phone")
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument("--model", default="yolov8s.pt")
    ap.add_argument("--extra-model", default="door_dustbin_stairs.pt")
    ap.add_argument("--name-index", default="name_index.npz",
                    help="embedding naming head built by build_name_index.py; "
                         "pass '' to disable and use raw YOLO names")
    ap.add_argument("--imgsz", type=int, default=640,
                    help="inference resolution; 480 is ~1.6x faster at a "
                         "small accuracy cost")
    ap.add_argument("--agent-model", nargs="?", const="llama3.2:1b",
                    help="local Ollama model for tier-1 routing and chat. The "
                         "bare flag gives llama3.2:1b, chosen 2026-09-05 for "
                         "LATENCY: it shares one 4 GB GPU with both YOLO "
                         "models, and measured under a live frame stream it "
                         "routes in ~281 ms median where llama3.2:3b took "
                         "6766-8016 ms and timed out on the handset. The 3b "
                         "model abstains better on noise (see CLAUDE.md) and "
                         "is still worth passing explicitly when the phone is "
                         "not streaming. Omit the flag for keyword routing "
                         "only.")
    ap.add_argument("--summary-model", nargs="?", const="llama3.2:3b",
                    help="model for /summarise only. Defaults to llama3.2:3b "
                         "when --agent-model is set to something smaller: "
                         "summarising runs with the camera paused so latency "
                         "barely matters, and llama3.2:1b is not safe at it "
                         "(it reported a real overdraft letter as saying the "
                         "account had been closed). Pass the same name as "
                         "--agent-model to use one model for everything.")
    ap.add_argument("--whisper-model", nargs="?", const="small.en",
                    help="local faster-whisper model for WAV uploads to "
                         "/agent (default small.en)")
    args = ap.parse_args()

    import agent
    llm = agent.OllamaRouter(model=args.agent_model) if args.agent_model else None
    if llm is not None:
        print(f"Agent tier 1: warming up {llm.model}...")
        print("  ready" if llm.warmup()
              else f"  UNAVAILABLE — {llm.error} (keyword routing still works)")
    # A SEPARATE, larger model for /summarise. Routing runs while frames stream
    # and wants the smallest model that can classify; summarising runs with the
    # camera paused, so it can afford a better one -- and needs it, because 1b
    # reported a real overdraft letter as saying the account had been closed.
    # Not warmed up: it is loaded on the first summary the user asks for, which
    # costs a few seconds once rather than holding VRAM the detectors need.
    summary_llm = None
    if args.summary_model and args.summary_model != args.agent_model:
        # A long timeout, because this model is NOT resident: 1b + 3b + both
        # detectors exceed the 4 GB card, so ollama loads it on demand and the
        # first summary of a session pays ~10 s for the load. The routing
        # default of 8 s was killing exactly that request and reporting it to
        # the user as a failure. Latency here is affordable -- the camera is
        # paused and the user is holding the phone over a page -- and
        # keep_alive means only the first one pays.
        summary_llm = agent.OllamaRouter(model=args.summary_model,
                                         timeout=90.0, cpu_only=True)
        print(f"Summaries use {summary_llm.model} on CPU "
              "(loaded on first use; keeps the GPU for routing and detection)")
    transcriber = None
    if args.whisper_model:
        from transcribe import Transcriber
        transcriber = Transcriber(args.whisper_model)
        print(f"Loading speech transcription ({args.whisper_model})...")
        if not transcriber.load():
            print(f"  UNAVAILABLE — {transcriber.error}")

    app = build_app(args.model, args.extra_model, imgsz=args.imgsz,
                    router=agent.AgentRouter(llm=llm), transcriber=transcriber,
                    name_index=args.name_index, summary_llm=summary_llm)
    start_discovery_responder(args.port)
    print(f"BlindAssist inference server on http://{args.host}:{args.port} "
          f"(UDP discovery on {DISCOVERY_PORT})")
    app.run(host=args.host, port=args.port, threaded=True)
