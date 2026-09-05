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
  "assistant" / "question"      -> ("ask", None), the open-dictation trigger

The closed grammar is exactly why a trigger word is needed: free speech is not
mis-parsed here, it is never HEARD. Saying a trigger opens a short window whose
raw audio goes to transcribe.py (Whisper) and then to agent.AgentRouter, so
tier 0 keeps its accuracy and its zero latency for everything else.
"""

import json
import queue
import threading
import time
from pathlib import Path

from position import TARGET_CLASSES

MODEL_DIR = Path(__file__).parent / "vosk-model-small-en-us-0.15"

# spoken word -> COCO class ("find phone" should just work)
SYNONYMS = {
    "phone": "cell phone", "mobile": "cell phone",
    "table": "dining table", "sofa": "couch",
    "fridge": "refrigerator", "television": "tv", "plant": "potted plant",
    "bag": "backpack", "man": "person", "woman": "person",
    # wardrobe/window are namer-only classes (see position.py). "almirah" is
    # the everyday Indian-English word for a wardrobe and is what this user
    # actually says.
    "cupboard": "wardrobe", "almirah": "wardrobe", "closet": "wardrobe",
    # "basket" alone is safe — no other class contains the word. Listed longer
    # forms too because _match_object takes the LONGEST match, so "laundry
    # bag" resolves to the basket and never to the generic "bag" -> backpack.
    "laundry": "laundry basket", "basket": "laundry basket",
    "hamper": "laundry basket", "laundry bag": "laundry basket",
}


def _plural(phrase):
    """Naive English plural of the LAST word ('cell phone' -> 'cell phones').
    Good enough for the constrained grammar; irregulars are added explicitly."""
    if phrase.endswith(("s", "sh", "ch", "x")):
        return phrase + "es"
    return phrase + "s"


_FINDABLE = {name: name for name in TARGET_CLASSES}
_FINDABLE.update(SYNONYMS)
# plurals: "how many chairs" is what people actually say — without these the
# constrained grammar can't even HEAR the plural form
_FINDABLE.update({_plural(k): v for k, v in list(_FINDABLE.items())})
_FINDABLE["people"] = "person"


def _match_object(rest):
    """Longest findable phrase inside `rest`, mapped to its COCO class, or
    None. Longest first so 'cell phone' beats 'phone'."""
    for phrase in sorted(_FINDABLE, key=len, reverse=True):
        if phrase in rest:
            return _FINDABLE[phrase]
    return None


def resolve_class(text):
    """Spoken words -> COCO class name, or None. Handles synonyms and plurals
    ('sofas' -> 'couch'). Public so the agent layer can validate a tool
    argument against exactly the vocabulary this parser accepts — tier 1 must
    never be able to name an object tier 0 would refuse."""
    if not text:
        return None
    text = text.strip().lower()
    return _FINDABLE.get(text) or _match_object(text)


# Saying one of these opens the open-dictation window: the recognizer's grammar
# is a closed list, so free speech is not mis-heard, it is never heard at all.
# An explicit trigger keeps tier 0 instant and untouched — only an utterance the
# user deliberately marked as a question takes the slow open path.
TRIGGER_WORDS = ("assistant", "question")

# Directional query vocabulary ("what's on my left", "anything in front of
# me"). Two halves must BOTH appear: a direction and a question word. That
# conjunction is what stops "move slightly left" style chatter, or a bare
# "left" heard mid-sentence, from firing a query.
_DIRECTION_WORDS = {"left": "left", "right": "right", "ahead": "ahead",
                    "front": "ahead", "forward": "ahead"}
_CHECK_WORDS = ("anything", "something", "what", "whats", "what's", "check",
                "there", "see", "is")
# "left" and "right" are ordinary English words; "how much battery is LEFT"
# routed to check(left) in the 2026-08-01 evaluation run. They only count as a
# direction when a positional word introduces them. "ahead"/"front"/"forward"
# need no such guard — they have no non-spatial reading here.
_UNAMBIGUOUS_DIRECTIONS = {"ahead", "front", "forward"}
_DIRECTION_LEAD = {"my", "the", "on", "to", "your", "check", "toward",
                   "towards"}


def _find_direction(words):
    """The direction this utterance asks about, or None."""
    for i, word in enumerate(words):
        if word not in _DIRECTION_WORDS:
            continue
        if (word in _UNAMBIGUOUS_DIRECTIONS
                or (i > 0 and words[i - 1] in _DIRECTION_LEAD)):
            return _DIRECTION_WORDS[word]
    return None


def parse_command(text):
    """Recognized utterance -> (action, target) or None. Actions:
    walk / find / describe / clock / zones / recall / stop / repeat /
    sonar / mute. Tolerant of filler words: 'please find the bottle' works."""
    words = text.lower().split()
    if not words:
        return None
    if "stop" in words:            # halt current speech (e.g. a long OCR read)
        return ("stop", None)
    if "repeat" in words or "again" in words:
        return ("repeat", None)    # say the last announcement again
    if "sonar" in words:           # hands-free toggle for the earphone beeps
        target = "on" if "on" in words else ("off" if "off" in words else None)
        return ("sonar", target)
    if "unmute" in words:
        return ("mute", "off")
    if "mute" in words:
        return ("mute", "on")
    if "describe" in words or "scene" in words or "summary" in words:
        return ("describe", None)
    if "clock" in words:
        return ("clock", None)
    if "zone" in words or "zones" in words:
        return ("zones", None)
    if "path" in words or ("which" in words and "way" in words):
        return ("path", None)  # clear-path finder: "which way is clear"
    if "read" in words:
        return ("read", None)  # OCR: read printed text aloud
    # Photo. Checked BEFORE the object queries so "take a picture" never gets
    # dragged into find/count by a stray class word later in the utterance.
    if "picture" in words or "photo" in words:
        return ("photo", None)
    if "how" in words and "many" in words:  # count query: "how many chairs"
        obj = _match_object(" ".join(words[words.index("many") + 1:]))
        if obj:
            return ("count", obj)
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
    # Directional query, AFTER find so "find the door on my left" still finds.
    # Deliberately tier 0: "is there anything in front of me" is the question
    # this system exists to answer, and it must work with no server and no LLM.
    direction = _find_direction(words)
    if direction and any(w in words for w in _CHECK_WORDS):
        return ("check", direction)
    # LAST, deliberately: every existing command keeps its exact precedence, so
    # the trigger can only fire on an utterance nothing else claimed.
    if any(w in words for w in TRIGGER_WORDS):
        return ("ask", None)
    return None


def grammar_phrases():
    """Every phrase the recognizer should be able to hear."""
    phrases = ["walk mode", "walk", "describe", "describe scene", "summary",
               "clock mode", "zone mode", "clear path", "which way",
               "read", "read text",
               "stop", "repeat", "say again", "sonar", "sonar on", "sonar off",
               "mute", "unmute", *TRIGGER_WORDS]
    for spoken in ("on my left", "on my right", "in front of me", "ahead"):
        phrases.append(f"what is {spoken}")
        phrases.append(f"whats {spoken}")
        phrases.append(f"is there anything {spoken}")
        phrases.append(f"anything {spoken}")
    phrases += ["check left", "check right", "check ahead"]
    for name in sorted(_FINDABLE):
        phrases.append(f"find {name}")
        phrases.append(f"find the {name}")
        phrases.append(f"where is {name}")
        phrases.append(f"where is the {name}")
        phrases.append(f"how many {name}")
    return phrases


class VoiceListener:
    """Continuously listens on the default microphone and fires
    on_command(("find", "bottle")) etc. Never raises out of the thread:
    failures land in self.error so the UI can show 'voice unavailable'."""

    def __init__(self, on_command, model_dir=MODEL_DIR, samplerate=16000,
                 phrases=None, on_dictation=None, dictate_seconds=4.0,
                 lead_in=1.0):
        self._on_command = on_command
        self._model_dir = Path(model_dir)
        self._samplerate = samplerate
        # phrases=None keeps the shipped grammar; webapp.py passes
        # agent.grammar_phrases() so the capability registry drives the
        # recognizer at runtime instead of merely documenting it.
        self._phrases = list(phrases) if phrases else grammar_phrases()
        self._on_dictation = on_dictation
        self._dictate_seconds = dictate_seconds
        self._lead_in = lead_in
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
            grammar = json.dumps(self._phrases + ["[unk]"])
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
                    if not command:
                        continue
                    self.last_heard = text
                    self._on_command(command)
                    if command[0] == "ask" and self._on_dictation:
                        self._dictate(rec)
        except Exception as exc:   # mic vanished mid-run, model load failed...
            self.error = f"voice stopped ({exc})"

    def _dictate(self, rec):
        """Capture a few seconds of open speech and hand the raw PCM to
        on_dictation. Reuses THIS thread's audio stream — opening a second
        input stream while the first is live fails on most backends.

        The lead-in exists because on_command has just made the host speak an
        acknowledgement, and the laptop's own TTS reaches its own microphone;
        discarding that window stops the ack being transcribed as the question.
        """
        deadline = time.monotonic() + self._lead_in
        while time.monotonic() < deadline and not self._stop.is_set():
            try:
                self._audio.get(timeout=0.2)      # discard the ack
            except queue.Empty:
                pass
        chunks = []
        deadline = time.monotonic() + self._dictate_seconds
        while time.monotonic() < deadline and not self._stop.is_set():
            try:
                chunks.append(self._audio.get(timeout=0.2))
            except queue.Empty:
                pass
        rec.Reset()      # the grammar recognizer must not see the dictation
        if chunks:
            try:
                self._on_dictation(b"".join(chunks), self._samplerate)
            except Exception as exc:   # a bad handler must not end voice
                print(f"voice: dictation handler failed ({exc})")
