"""BlindAssist — voice commands (innovation feature #2).

Two layers, same philosophy as position.py / decision.py / speech.py:

  parse_command(text)  — PURE logic: recognized text -> command tuple.
                         No vosk, no audio, fully unit-testable.
  VoiceListener        — microphone -> Vosk (offline speech recognition)
                         -> parse_command -> on_command callback, all on a
                         daemon thread. Heavy imports stay inside start().

Vosk runs completely offline: the one-time ~40 MB English model download
lives in vosk-model-small-en-us-0.15/ next to this file. The recognizer is
constrained to a GRAMMAR of exactly the phrases we understand, which makes
recognition far more reliable than free dictation on a small model.

Commands (a few everyday synonyms are mapped to COCO names):
  "walk mode" / "walk"          -> ("walk", None)
  "find <object>"               -> ("find", "<coco class>")
  "describe" / "describe scene" -> ("describe", None)
"""

import json
import queue
import threading
from pathlib import Path

from position import TARGET_CLASSES

MODEL_DIR = Path(__file__).parent / "vosk-model-small-en-us-0.15"

# spoken word -> COCO class ("find phone" should just work)
SYNONYMS = {
    "phone": "cell phone", "mobile": "cell phone",
    "table": "dining table", "sofa": "couch",
    "fridge": "refrigerator", "television": "tv", "plant": "potted plant",
    "bag": "backpack", "man": "person", "woman": "person",
}

_FINDABLE = {name: name for name in TARGET_CLASSES}
_FINDABLE.update(SYNONYMS)


def _match_object(rest):
    """Longest findable phrase inside `rest`, mapped to its COCO class, or
    None. Longest first so 'cell phone' beats 'phone'."""
    for phrase in sorted(_FINDABLE, key=len, reverse=True):
        if phrase in rest:
            return _FINDABLE[phrase]
    return None


def parse_command(text):
    """Recognized utterance -> (action, target) or None. Actions:
    walk / find / describe / clock / zones / recall. Tolerant of filler
    words: 'please find the bottle' works."""
    words = text.lower().split()
    if not words:
        return None
    if "describe" in words or "scene" in words or "summary" in words:
        return ("describe", None)
    if "clock" in words:
        return ("clock", None)
    if "zone" in words or "zones" in words:
        return ("zones", None)
    if "where" in words:  # object-memory query: "where is my cup"
        rest = " ".join(words[words.index("where") + 1:])
        obj = _match_object(rest)
        if obj:
            return ("recall", obj)
    if "walk" in words:
        return ("walk", None)
    if "find" in words:
        obj = _match_object(" ".join(words[words.index("find") + 1:]))
        if obj:
            return ("find", obj)
    return None


def grammar_phrases():
    """Every phrase the recognizer should be able to hear."""
    phrases = ["walk mode", "walk", "describe", "describe scene", "summary",
               "clock mode", "zone mode"]
    for name in sorted(_FINDABLE):
        phrases.append(f"find {name}")
        phrases.append(f"find the {name}")
        phrases.append(f"where is {name}")
        phrases.append(f"where is the {name}")
    return phrases


class VoiceListener:
    """Continuously listens on the default microphone and fires
    on_command(("find", "bottle")) etc. Never raises out of the thread:
    failures land in self.error so the UI can show 'voice unavailable'."""

    def __init__(self, on_command, model_dir=MODEL_DIR, samplerate=16000):
        self._on_command = on_command
        self._model_dir = Path(model_dir)
        self._samplerate = samplerate
        self._audio = queue.Queue()
        self._stop = threading.Event()
        self._thread = None
        self.error = None
        self.last_heard = None     # last utterance that parsed to a command

    def start(self):
        if not self._model_dir.is_dir():
            self.error = f"speech model not found at {self._model_dir.name}"
            return False
        try:
            import sounddevice  # noqa: F401 — fail early if there's no mic
            sounddevice.check_input_settings(samplerate=self._samplerate,
                                             channels=1, dtype="int16")
        except Exception as exc:
            self.error = f"microphone unavailable ({exc})"
            return False
        self._thread = threading.Thread(target=self._worker, daemon=True,
                                        name="blindassist-voice")
        self._thread.start()
        return True

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(2.0)

    @property
    def active(self):
        return self._thread is not None and self._thread.is_alive()

    # -- worker -------------------------------------------------------------

    def _worker(self):
        try:
            import sounddevice
            from vosk import KaldiRecognizer, Model, SetLogLevel
            SetLogLevel(-1)  # keep the console clean
            model = Model(str(self._model_dir))
            grammar = json.dumps(grammar_phrases() + ["[unk]"])
            rec = KaldiRecognizer(model, self._samplerate, grammar)

            def capture(indata, frames, t, status):
                self._audio.put(bytes(indata))

            with sounddevice.RawInputStream(samplerate=self._samplerate,
                                            blocksize=8000, dtype="int16",
                                            channels=1, callback=capture):
                while not self._stop.is_set():
                    try:
                        data = self._audio.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if not rec.AcceptWaveform(data):
                        continue
                    text = json.loads(rec.Result()).get("text", "")
                    text = text.replace("[unk]", "").strip()
                    if not text:
                        continue
                    command = parse_command(text)
                    if command:
                        self.last_heard = text
                        self._on_command(command)
        except Exception as exc:   # mic vanished mid-run, model load failed...
            self.error = f"voice stopped ({exc})"
