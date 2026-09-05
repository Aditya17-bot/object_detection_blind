"""BlindAssist — web frontend. Camera -> YOLO -> position -> decision ->
speech, presented in the browser instead of an OpenCV window.

Run:
    python webapp.py                             # walk mode, webcam
    python webapp.py --source http://<ip>:8080/video
    python webapp.py --source test_output\clip.mp4   # demo on a clip (loops)
    python webapp.py --mute                      # silent dry run
then open http://127.0.0.1:5000

The browser page adds what an OpenCV window can't:
  - live annotated video (MJPEG) with the announcement banner
  - big accessible Walk/Find controls, describe-scene button, mute, rate
  - a running announcement feed (aria-live, so screen readers speak it too)
  - SONAR mode: the page synthesizes stereo-panned beeps with WebAudio —
    pan follows the obstacle's center_x, beep rate/pitch rise as it gets
    closer. Earphones recommended. (Innovation feature #1; done client-side
    so the Python side needs no audio dependency beyond pyttsx3.)

Pipeline code is untouched: this file only wires position.py / decision.py /
speech.py / phase2's annotate() behind Flask. All heavy imports happen at
start_engine() time so unit tests can import this module cheaply.
"""

import argparse
import json
import threading
import time
from collections import deque
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

import agent
from agent_server import register_agent_routes
from decision import GuidanceEngine, find_target, pick_obstacle
from position import FIND_CLASSES, OBSTACLE_CLASSES

# proximity -> 0..3 for the sonar (far/none = 0 keeps the page logic simple)
_SONAR_LEVEL = {"very close": 3, "close": 2, "medium": 1, "far": 0}

# Per-class confidence floors for the custom model, applied on top of
# --extra-conf. ("stairs" needs no entry here: it was dropped from
# TARGET_CLASSES entirely — 0.072 recall + high-conf false positives on
# walls/ceilings — so annotate() already ignores it.)
_CUSTOM_CLASS_CONF = {"door": 0.5, "dustbin": 0.5}


class AssistantEngine:
    """Owns the capture/inference thread and everything it produces.

    The Flask handlers only ever touch `snapshot()`, `latest_jpeg()` and the
    small control methods, all guarded by one lock; the worker thread is the
    only writer. Same real-time clock rule as phase4: speech happens in real
    time, so the GuidanceEngine clock is real time even for clips.
    """

    def __init__(self, source="0", mode="walk", target=None,
                 model_name="yolov8s.pt", conf=0.6, rate=175, muted=False,
                 voice=True, extra_model="door_dustbin_stairs.pt",
                 extra_conf=0.4, agent_model=None, whisper_model=None,
                 name_index=None):
        self.source = source
        self.model_name = model_name
        self.conf = conf
        self.extra_model = extra_model   # custom door/dustbin/stairs weights
        self.extra_conf = extra_conf
        self._extra = None
        # Embedding naming head (name_index.py). None = raw YOLO names, which
        # is exactly the behaviour before it existed.
        self.name_index = name_index
        self._namer = None
        self.muted = muted
        self._rate = rate
        self._lock = threading.Lock()
        self._engine = GuidanceEngine(mode=mode, target=target)
        self._speaker = None
        self._thread = None
        self._stop = threading.Event()
        self._jpeg = None            # latest annotated frame, JPEG bytes
        self._detections = []        # plain dicts for /state
        self._sonar = {"level": 0, "pan": 0.0, "name": None}
        self._announcements = deque(maxlen=60)   # {"t", "text", "kind"}
        self._fps = 0.0
        self._started = time.monotonic()
        self._last_infos = []
        self.error = None
        self._want_voice = voice
        self._voice = None
        # Desired sonar state, mirrored by the browser on its next poll. Starts
        # FALSE to match the page's own default — otherwise the first poll
        # would switch the beeps on for a user who never asked.
        self.sonar_on = False
        self._last_spoken = None     # for the "repeat" capability
        self.last_route = None       # which tier answered, for the status pill
        self.last_dictation = None   # last free-form utterance heard
        # Tier 1 is opt-in: with no --agent-model the router is tier-0 only and
        # the whole system behaves exactly as it did before the agent existed.
        self._llm = (agent.OllamaRouter(model=agent_model)
                     if agent_model else None)
        self._router = agent.AgentRouter(llm=self._llm)
        self._transcriber = None
        if whisper_model:
            from transcribe import Transcriber
            self._transcriber = Transcriber(whisper_model)
        self._hooks = agent.Hooks(
            set_sonar=self._set_sonar,
            set_mute=lambda on: setattr(self, "muted", on),
            stop=lambda: self._speaker and self._speaker.stop(),
            repeat=lambda: self._last_spoken,
            # OCR is a phone capability (camera still + ML Kit); saying so is
            # the point of the Hooks table — an unwired capability announces
            # itself instead of silently doing nothing.
            read_text=None,
            dictate=lambda: None,    # VoiceListener owns the capture window
        )

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        """Load the model, open the source and start the worker thread.
        Raises SystemExit with a readable message if the source won't open."""
        import cv2                      # heavy imports deferred on purpose
        from ultralytics import YOLO
        from speech import Speaker

        self._cv2 = cv2
        print(f"Loading {self.model_name}...")
        self._model = YOLO(self.model_name)
        extra = Path(self.extra_model) if self.extra_model else None
        if extra is not None and extra.exists():
            self._extra = YOLO(str(extra))
            print(f"Custom model ON: {extra.name} "
                  f"-> {sorted(self._extra.names.values())}")
        elif extra is not None:
            print(f"Custom model {extra.name} not found — COCO classes only")
        if self.name_index:
            from name_index import Namer
            from position import TARGET_CLASSES
            self._namer = Namer.maybe_load(self.name_index, self._model,
                                           self.model_name,
                                           vocabulary=TARGET_CLASSES)
        self._cap, self.source_name, self.is_file = self._open(self.source)
        if not self._cap.isOpened():
            raise SystemExit(f"Could not open source {self.source!r}")
        self._speaker = Speaker(rate=self._rate)
        if self._llm is not None:
            # load the model NOW: Ollama unloads an idle model and the reload
            # would land on exactly the utterance the user cared about
            print(f"Agent tier 1: warming up {self._llm.model}...")
            print("  ready" if self._llm.warmup()
                  else f"  UNAVAILABLE — {self._llm.error} (tier 0 still works)")
        if self._transcriber is not None:
            print(f"Loading speech transcription ({self._transcriber.model_size})...")
            if not self._transcriber.load():
                print(f"  UNAVAILABLE — {self._transcriber.error}")
        if self._want_voice:
            from voice import VoiceListener
            # the capability registry drives the recognizer's grammar
            self._voice = VoiceListener(
                self._on_voice_command,
                phrases=agent.grammar_phrases(),
                on_dictation=(self._on_dictation
                              if self._transcriber is not None else None))
            if self._voice.start():
                print("Voice commands ON — say 'find bottle', 'walk mode', "
                      "'describe'")
                if self._transcriber is not None:
                    print("  say 'assistant' for a free-form question")
            else:
                print(f"Voice commands unavailable: {self._voice.error}")
        self._thread = threading.Thread(target=self._worker, daemon=True,
                                        name="blindassist-camera")
        self._thread.start()

    def _open(self, source):
        cv2 = self._cv2
        if source.isdigit():
            return cv2.VideoCapture(int(source)), f"webcam{source}", False
        if source.lower().startswith(("http://", "https://", "rtsp://")):
            return cv2.VideoCapture(source), "stream", False
        path = Path(source)
        return cv2.VideoCapture(str(path)), path.stem, True

    def close(self):
        self._stop.set()
        if self._voice:
            self._voice.close()
        if self._thread:
            self._thread.join(2.0)
        if self._speaker:
            self._speaker.close()

    def _set_sonar(self, on):
        # the beeps are synthesized in the BROWSER; the server only publishes
        # the desired state and the page reconciles on its next poll
        self.sonar_on = (not self.sonar_on) if on is None else bool(on)

    def _on_voice_command(self, command):
        """VoiceListener thread -> the single executor.

        Tier 0 has already parsed the utterance, so this is the execute half
        of route-then-execute; the ~200 lines of hand-written branches this
        replaces had silently drifted out of sync with the parser (read,
        sonar, stop, repeat and mute all did nothing here).

        MUST NOT raise: an exception propagates into the VoiceListener worker
        and silently kills voice for the whole session — that is exactly what
        happened when 'clock mode' arrived before the old dispatch knew about
        it. execute_action only ever sees registry-validated tools, and the
        try/except is the belt to that braces."""
        try:
            self._run([agent.Action(command[0], command[1])], "voice")
        except Exception as exc:      # noqa: BLE001 — voice must survive
            print(f"voice dispatch failed ({exc})")

    def _on_dictation(self, pcm, samplerate):
        """The open-dictation window closed — transcribe it and route it.

        Runs on the voice thread. The "One moment" ack matters: transcription
        plus a local LLM is seconds of silence, and unexplained silence is the
        exact failure this project already designs against (it is why Find
        mode says "Still looking for X")."""
        t = time.monotonic() - self._started
        self._announce(agent.ASK_TEMPLATES["working"], t, "voice")
        text = self._transcriber.transcribe_pcm(pcm, samplerate)
        if not text:
            self._announce(agent.ASK_TEMPLATES["not_understood"], t, "voice")
            return
        self.last_dictation = text
        result = self.route(text)
        self._run_result(result, "agent")

    # -- routing + execution -----------------------------------------------

    def agent_state(self):
        """Deterministic facts for the router — built from the detector's own
        output, never from a description."""
        with self._lock:
            return agent.state_summary(self._last_infos, self._engine,
                                       time.monotonic() - self._started)

    def route(self, text):
        """Utterance -> RouteResult, against the current frame's facts."""
        result = self._router.route(text, self.agent_state())
        self.last_route = result.source
        return result

    def run_route(self, result, kind="agent"):
        """Execute a RouteResult and return what was spoken."""
        self.last_route = result.source
        return self._run_result(result, kind)

    def _run_result(self, result, kind):
        if result.ask and not result.actions:
            self._announce(result.message,
                           time.monotonic() - self._started, kind)
            return [result.message]
        return self._run(result.actions, kind)

    def _run(self, actions, kind):
        """Execute validated actions and speak whatever they return.

        Announcing happens OUTSIDE the lock — _announce takes it too, and the
        lock is not reentrant."""
        t = time.monotonic() - self._started
        with self._lock:
            infos = list(self._last_infos)
            messages = [agent.execute_action(a, self._engine, infos, t,
                                             self._hooks) for a in actions]
        spoken = [m for m in messages if m]
        for message in spoken:
            self._announce(message, t, kind)
        return spoken

    # -- worker ------------------------------------------------------------

    def _worker(self):
        from phase2_detect import (apply_namer, collect_dets, draw_dets,
                                   draw_grid, infos_from_dets)
        from phase3_detect import draw_banner
        cv2 = self._cv2
        banner = "..."
        frame_times = deque(maxlen=20)
        while not self._stop.is_set():
            ok, frame = self._cap.read()
            if not ok:
                if self.is_file:     # demo clips loop forever
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                self.error = "Camera/stream stopped delivering frames"
                break
            t = time.monotonic() - self._started
            # BEFORE anything draws: the naming head has to embed real pixels,
            # not the grid lines and labels we are about to burn in.
            clean = frame.copy()
            fh, fw = frame.shape[:2]
            keep_all = self._namer is not None
            result = self._model(frame, verbose=False)[0]
            dets = collect_dets(result, self.conf, fw, fh, keep_all)
            if self._extra is not None:  # doors/dustbins/stairs, 2nd pass
                extra = self._extra(frame, verbose=False)[0]
                dets += [
                    d for d in collect_dets(extra, self.extra_conf, fw, fh,
                                            keep_all, trusted=True)
                    if d["conf"] >= _CUSTOM_CLASS_CONF.get(d["name"], 0.0)]
            # one call over the MERGED detections — see apply_namer's note on
            # why per-model calls would break the hysteresis tracks
            dets = apply_namer(self._namer, clean, dets)
            draw_grid(frame)
            infos = infos_from_dets(dets, fw, fh)
            draw_dets(frame, dets, infos)
            with self._lock:
                msg = self._engine.update(infos, t)
                self._last_infos = infos
                mode, target = self._engine.mode, self._engine.target
            if msg:
                self._announce(msg, t, "guidance")
                banner = msg
            draw_banner(frame, banner, fresh=bool(msg))
            ok2, buf = cv2.imencode(".jpg", frame,
                                    [cv2.IMWRITE_JPEG_QUALITY, 80])
            frame_times.append(time.monotonic())
            fps = 0.0
            if len(frame_times) >= 2:
                span = frame_times[-1] - frame_times[0]
                fps = (len(frame_times) - 1) / span if span > 0 else 0.0
            # sonar tracks the walking obstacle — or, in find mode, the
            # searched-for object, so the beeps lead the user to it
            if mode == "find":
                tracked = find_target(infos, target)
            else:
                tracked = pick_obstacle(infos)
            with self._lock:
                if ok2:
                    self._jpeg = buf.tobytes()
                self._fps = fps
                self._detections = [{
                    "name": i.name, "phrase": i.phrase,
                    "proximity": i.proximity,
                    "confidence": round(i.confidence, 2),
                } for i in infos]
                self._sonar = {
                    "level": max(_SONAR_LEVEL[tracked.proximity], 1),
                    # center_x 0..1 -> stereo pan -1..1
                    "pan": round(tracked.center_x * 2 - 1, 3),
                    "name": tracked.name,
                } if tracked else {"level": 0, "pan": 0.0, "name": None}

    def _announce(self, text, t, kind):
        with self._lock:
            self._announcements.append(
                {"t": round(t, 1), "text": text, "kind": kind})
            self._last_spoken = text
        if not self.muted and self._speaker:
            self._speaker.say(text)
        print(f"[{t:6.2f}s] SAY: {text}")

    # -- control (called from Flask handlers) ------------------------------

    def set_mode(self, mode, target=None):
        with self._lock:
            self._engine.set_mode(mode, target)

    def describe(self):
        with self._lock:
            infos = list(self._last_infos)
        t = time.monotonic() - self._started
        with self._lock:
            summary = self._engine.describe(infos, t)
        self._announce(summary, t, "summary")
        return summary

    def set_rate(self, rate):
        # pyttsx3 rate lives on the worker-thread engine; recreate the speaker
        from speech import Speaker
        self._rate = rate
        if self._speaker:
            self._speaker.close()
            self._speaker = Speaker(rate=rate)

    # -- read side ----------------------------------------------------------

    def latest_jpeg(self):
        with self._lock:
            return self._jpeg

    def snapshot(self):
        with self._lock:
            return {
                "mode": self._engine.mode,
                "target": self._engine.target,
                "muted": self.muted,
                "rate": self._rate,
                "fps": round(self._fps, 1),
                "model": (self.model_name + " + custom"
                          if self._extra is not None else self.model_name),
                "source": getattr(self, "source_name", self.source),
                "detections": self._detections,
                "sonar": self._sonar,
                "announcements": list(self._announcements),
                "sonar_on": self.sonar_on,
                "voice": {
                    "active": bool(self._voice and self._voice.active),
                    "last": self._voice.last_heard if self._voice else None,
                    "error": self._voice.error if self._voice else None,
                },
                "router": {
                    "enabled": self._router.enabled,
                    "model": self._llm.model if self._llm else None,
                    "source": self.last_route,
                    "transcript": self.last_dictation,
                    "error": (self._llm.error if self._llm else None)
                             or (self._transcriber.error
                                 if self._transcriber else None),
                },
                "error": self.error,
            }


def create_app(engine):
    """Flask app around an AssistantEngine (real or fake — see test_webapp)."""
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            find_classes=sorted(FIND_CLASSES),
            obstacle_classes=sorted(OBSTACLE_CLASSES))

    @app.route("/video")
    def video():
        def frames():
            last = None
            while True:
                jpeg = engine.latest_jpeg()
                if jpeg is not None and jpeg is not last:
                    last = jpeg
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                           + jpeg + b"\r\n")
                time.sleep(0.03)
        return Response(frames(),
                        mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/state")
    def state():
        return jsonify(engine.snapshot())

    @app.route("/mode", methods=["POST"])
    def mode():
        data = request.get_json(force=True)
        m = data.get("mode")
        target = data.get("target")
        if m not in ("walk", "find"):
            return jsonify(error="mode must be walk or find"), 400
        if m == "find" and target not in FIND_CLASSES | OBSTACLE_CLASSES:
            return jsonify(error=f"unknown target {target!r}"), 400
        engine.set_mode(m, target if m == "find" else None)
        return jsonify(ok=True)

    @app.route("/describe", methods=["POST"])
    def describe():
        return jsonify(summary=engine.describe())

    @app.route("/mute", methods=["POST"])
    def mute():
        engine.muted = bool(request.get_json(force=True).get("muted"))
        return jsonify(ok=True, muted=engine.muted)

    @app.route("/rate", methods=["POST"])
    def rate():
        value = request.get_json(force=True).get("rate")
        if not isinstance(value, int) or not 80 <= value <= 300:
            return jsonify(error="rate must be an int 80..300"), 400
        engine.set_rate(value)
        return jsonify(ok=True, rate=value)

    # POST /agent — type an utterance and watch it route and execute. This is
    # how the whole layer is exercised with no microphone and no Whisper
    # model, and it is the demo affordance: the response says which tier
    # answered.
    router = getattr(engine, "_router", None)
    if router is not None:
        register_agent_routes(
            app, router,
            transcriber=getattr(engine, "_transcriber", None),
            execute=engine.run_route,
            get_state=engine.agent_state)

    return app


def main():
    ap = argparse.ArgumentParser(description="BlindAssist web frontend")
    ap.add_argument("--source", default="0",
                    help="webcam index, video file, or http/rtsp URL")
    ap.add_argument("--mode", choices=("walk", "find"), default="walk")
    ap.add_argument("--target", help="class to look for in find mode")
    ap.add_argument("--model", default="yolov8s.pt")
    ap.add_argument("--conf", type=float, default=0.6)
    ap.add_argument("--extra-model", default="door_dustbin_stairs.pt",
                    help="custom door/dustbin/stairs weights "
                         "(skipped if the file is missing)")
    ap.add_argument("--extra-conf", type=float, default=0.4,
                    help="confidence threshold for the custom model "
                         "(0.4: partial/far doors live in the 0.4-0.5 band)")
    ap.add_argument("--name-index", default="name_index.npz",
                    help="embedding naming head built by build_name_index.py; "
                         "pass '' to disable and use raw YOLO names")
    ap.add_argument("--rate", type=int, default=175)
    ap.add_argument("--mute", action="store_true")
    ap.add_argument("--no-voice", action="store_true",
                    help="disable microphone voice commands")
    ap.add_argument("--agent-model",
                    help="local Ollama model for tier-1 routing, e.g. "
                         "qwen2.5:1.5b-instruct. Omit for tier 0 only "
                         "(exactly the behaviour before the agent existed). "
                         "Run `python bench_llm.py` first to check it is fast "
                         "enough on this machine.")
    ap.add_argument("--whisper-model", nargs="?", const="small.en",
                    help="enable the 'assistant' free-speech trigger using a "
                         "local faster-whisper model (default small.en)")
    ap.add_argument("--host", default="127.0.0.1",
                    help="use 0.0.0.0 to open the UI from a phone on the "
                         "same Wi-Fi (allow python through the firewall)")
    ap.add_argument("--port", type=int, default=5000)
    args = ap.parse_args()
    if args.mode == "find" and not args.target:
        ap.error("--mode find requires --target")

    engine = AssistantEngine(source=args.source, mode=args.mode,
                             target=args.target, model_name=args.model,
                             conf=args.conf, rate=args.rate, muted=args.mute,
                             voice=not args.no_voice,
                             extra_model=args.extra_model,
                             extra_conf=args.extra_conf,
                             agent_model=args.agent_model,
                             whisper_model=args.whisper_model,
                             name_index=args.name_index)
    engine.start()
    app = create_app(engine)
    print(f"\n  BlindAssist running -> http://127.0.0.1:{args.port}")
    if args.host == "0.0.0.0":
        import socket
        try:  # the LAN address a phone on the same Wi-Fi should open
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]
            s.close()
            print(f"  On your phone     -> http://{lan_ip}:{args.port}")
        except OSError:
            pass
    print()
    try:
        # threaded so /video (a long-lived stream) never blocks /state
        app.run(host=args.host, port=args.port, threaded=True,
                use_reloader=False)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
