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
    """The findable phrase nearest the START of `rest`, mapped to its COCO
    class, or None.

    EARLIEST first, then longest. Longest-anywhere was the original rule and it
    picks the wrong object the moment a second class word is present: the field
    log has "find dustbin toilets" (a grammar-forced mishearing) resolving to
    `toilet`, which is neither what was said nor even the first thing the
    sentence names. The user's object is the one they said first after "find";
    length still breaks ties at the same position so "cell phone" beats
    "phone"."""
    best = None
    for phrase, name in _FINDABLE.items():
        at = rest.find(phrase)
        if at < 0:
            continue
        if best is None or at < best[0] or (at == best[0]
                                            and len(phrase) > best[1]):
            best = (at, len(phrase), name)
    return best[2] if best else None


def named_classes(text):
    """Every DISTINCT object class named anywhere in `text`.

    The signature of grammar-forced noise, and the reason it needs its own
    detector: Vosk emits `[unk]` only for sound it cannot place at all, so
    ambient noise that happens to land on trained words arrives with ZERO
    unplaceable tokens and sails through the unknown-ratio floor. The
    2026-09-07 field log is full of it — "cupboard find dustbin",
    "find dustbin toilets", "mobile photo person on anything on my left dining
    the" — and one of those put the app into find mode for an object nobody
    asked about.

    Real requests name ONE thing. Two different objects in one utterance is
    evidence of a bag of force-matched words rather than a sentence."""
    words = text.lower().split()
    found = set()
    for phrase, name in _FINDABLE.items():
        parts = phrase.split()
        # WHOLE words only. Substring matching looks equivalent and is not:
        # "how many chairs" contains "man" (a person synonym) and "cupboard"
        # contains "cup", so a plain `in` test reports two objects in ordinary
        # single-object requests and would reject them as noise.
        for i in range(len(words) - len(parts) + 1):
            if words[i:i + len(parts)] == parts:
                found.add(name)
                break
    return found


# Which capability each keyword belongs to. Mirrors the keyword tests in
# parse_command, and exists for the same reason named_classes does: an
# utterance that names TWO capabilities is a bag of force-matched words, not a
# sentence. The 2026-09-07 field log ran `describe` from "describe light left"
# and "the clock summary", and `read` from "the many where of me is there read
# walk".
#
# Direction words are deliberately absent: "left" is only a capability with a
# question word in front of it, and "find the door on my left" is one request.
# The dictation trigger is absent too — "assistant find the door" is a trigger
# plus a request BY DESIGN, and counting it would reject the documented form.
_CAPABILITY_WORDS = {
    "walk": "walk", "find": "find",
    "describe": "describe", "scene": "describe", "summary": "describe",
    "many": "count", "where": "recall",
    "path": "path", "way": "path",
    "read": "read", "picture": "photo", "photo": "photo",
    "summarise": "summarise", "summarize": "summarise",
    "colour": "colour", "color": "colour",
    "bright": "light", "dark": "light", "light": "light",
    "clock": "clock", "zone": "zones", "zones": "zones",
    "sonar": "sonar", "mute": "mute", "unmute": "mute",
    "stop": "stop", "repeat": "repeat", "again": "repeat",
    "help": "help",
}

# The longest phrase the grammar can legitimately produce is "is there anything
# in front of me" (7 words). Anything much past that is the recognizer chaining
# trained phrases out of room noise, whatever else it contains.
MAX_REQUEST_WORDS = 8


def named_capabilities(text):
    """Every DISTINCT capability named anywhere in `text`."""
    return {_CAPABILITY_WORDS[w] for w in text.lower().split()
            if w in _CAPABILITY_WORDS}


def looks_like_one_request(text):
    """Could this recognizer output be ONE thing a person asked for?

    Three conditions, each of which the 2026-09-07 field log broke:
      * at most one object class named ("cupboard find dustbin");
      * at most one capability named ("describe light left");
      * no longer than MAX_REQUEST_WORDS ("do laptops ahead laptop on my left
        bottle on here right").

    None of these can be seen by the unknown-token ratio, because words forced
    onto the grammar are not unplaceable — the recognizer is certain about
    every one of them. Mirror of voice_commands.dart.
    """
    if not text:
        return False
    if len(text.split()) > MAX_REQUEST_WORDS:
        return False
    if len(named_classes(text)) > 1:
        return False
    return len(named_capabilities(text)) <= 1


def names_multiple_objects(text):
    """True when `text` names two or more different classes — see
    [named_classes]. Mirror of voice_commands.dart."""
    return len(named_classes(text)) > 1


# Settings are the one class of command whose cost is asymmetric in the
# dangerous direction. Everything else answers out loud, so a spurious trigger
# is a sentence the user can ignore and correct. Mute, sonar, clock and zones
# change behaviour PERSISTENTLY and leave no trace a blind user can check —
# and the app has already been silently muted in the field once
# (2026-09-07: "mute it", then every later command ran without a voice).
#
# The recognizer's grammar is closed, so ambient speech does not fail to
# match — it matches the nearest trained phrase and is CERTAIN about it. On
# the 2026-09-07 walk audio, replayed through the shipped grammar, the room
# produced 'is mute womans', which contains "mute" and therefore muted the
# app. No unknown-token test can see this: there were no unknown tokens.
#
# So a setting command must BE a setting phrase, not merely contain one: every
# word has to come from that command's own vocabulary or this filler list.
SETTING_ACTIONS = frozenset({"mute", "sonar", "clock", "zones"})

_SETTING_VOCAB = {
    "mute": frozenset({"mute", "unmute", "voice", "sound", "speak", "on",
                       "off", "mode"}),
    "sonar": frozenset({"sonar", "on", "off", "mode"}),
    "clock": frozenset({"clock", "mode", "on", "off"}),
    "zones": frozenset({"zone", "zones", "mode", "on", "off"}),
}

# Politeness and articles a person really does put around a bare command.
# Deliberately short: every word added here is a word ambient speech is
# allowed to contain while still flipping a setting. "is" is NOT in it, which
# is what rejects 'is mute womans'.
_SETTING_FILLER = frozenset({
    "please", "the", "a", "an", "it", "to", "turn", "switch", "put", "go",
    "back", "now", "my", "and", "can", "you", "let's", "lets",
})


def setting_is_deliberate(action, text):
    """True when `text` is a plain request for `action` and nothing else.

    Only applies to SETTING_ACTIONS; every other action returns True, because
    for those the user hears the result immediately. Mirror of
    voice_commands.dart.
    """
    if action not in SETTING_ACTIONS:
        return True
    allowed = _SETTING_VOCAB[action] | _SETTING_FILLER
    words = text.lower().split()
    return bool(words) and all(w in allowed for w in words)


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
    # "stop walk mode" / "stop the guidance" is a request to switch the
    # continuous warnings OFF, not to cut the current sentence — and it is what
    # a user reaches for first, so it is checked BEFORE the bare "stop". The
    # conjunction keeps plain "stop" instant, which is what it is for.
    if "stop" in words and ("guidance" in words or "walk" in words
                            or "walking" in words):
        return ("guidance", "off")
    if "stop" in words:            # halt current speech (e.g. a long OCR read)
        return ("stop", None)
    # The continuous warnings as a whole. BEFORE walk/find/describe: "quiet
    # mode" and "guidance off" name no other capability, and putting it here
    # means "guidance on" cannot be dragged into anything else by its "on".
    if "guidance" in words or "quiet" in words:
        if "quiet" in words or "off" in words or "pause" in words:
            return ("guidance", "off")
        if "on" in words or "resume" in words or "start" in words:
            return ("guidance", "on")
        return ("guidance", None)
    if "repeat" in words or "again" in words:
        return ("repeat", None)    # say the last announcement again
    if "sonar" in words:           # hands-free toggle for the earphone beeps
        target = "on" if "on" in words else ("off" if "off" in words else None)
        return ("sonar", target)
    # Every way back from mute, BEFORE the mute test so "voice on" is not read
    # as a request to mute. "unmute" is kept for typed and agent input; the
    # spoken forms exist because the model cannot pronounce it (see
    # UNHEARABLE_WORDS), which left a muted app with no voice route back.
    if "unmute" in words or "speak" in words or (
            "on" in words and ("voice" in words or "sound" in words)):
        return ("mute", "off")
    if "mute" in words:
        return ("mute", "on")
    # "what is around me" and "what do you see" are the two phrasings people
    # reach for before they learn the word "describe" — and tier 1 got them
    # wrong (llama3.2:1b abstained on the first and had to be asked twice for
    # the second), so they are answered deterministically here. No direction
    # word, so `check` cannot claim them.
    if ("describe" in words or "scene" in words or "summary" in words
            or "around" in words
            or ("see" in words and ("you" in words or "what" in words))):
        return ("describe", None)
    if "clock" in words:
        return ("clock", None)
    if "zone" in words or "zones" in words:
        return ("zones", None)
    if "path" in words or ("which" in words and "way" in words):
        return ("path", None)  # clear-path finder: "which way is clear"
    # Help BEFORE everything that could claim one of its words: "what can you
    # do" has "do" in it and "what can this app do" has "this". Deterministic on
    # purpose — llama3.2:1b abstained on every phrasing of this question, and a
    # capability list is the last thing that should be improvised.
    if "help" in words or (
            "what" in words and "can" in words and
            ("do" in words or "say" in words)):
        return ("help", None)
    # Summarise BEFORE read, so "summarise this" is not swallowed by a stray
    # "read". "summary" alone stays with describe, which has owned it since
    # the scene-summary feature and is what users already say for it.
    if "summarise" in words or "summarize" in words:
        return ("summarise", None)
    if "read" in words:
        return ("read", None)  # OCR: read printed text aloud
    # Colour and brightness, both BEFORE the object queries so "what colour is
    # the chair" is not dragged into find by the trailing class word.
    if "colour" in words or "color" in words:
        return ("colour", None)
    if "bright" in words or "dark" in words or "light" in words:
        return ("light", None)
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


# Words the shipped Vosk model has no pronunciation for. Vosk drops them from
# the grammar with a warning nobody reads, so a phrase built from one is not
# misheard — it is UNHEARABLE, exactly like a phrase that was never added.
#
# `unmute` is the one that mattered: on the 2026-09-07 walk the user said "mute
# it", the app muted, and there was then NO SPOKEN WAY BACK — every command
# after that ran silently, which is indistinguishable from the app having
# stopped hearing. Hence the "voice on" / "sound on" / "speak" phrasings, all
# of which the model does know.
#
# The other three are Indian-English and plural synonyms; they stay in the
# PARSER (typed input and the agent tier still resolve them) and only leave the
# grammar. Kept honest by test_voice.VocabularyTest, which builds the real
# grammar against the real model and fails on any word the model would drop.
UNHEARABLE_WORDS = frozenset({"almirah", "almirahs", "laundrys", "unmute"})


def _hearable(phrase):
    return not any(w in UNHEARABLE_WORDS for w in phrase.split())


def grammar_phrases():
    """Every phrase the recognizer should be able to hear."""
    phrases = ["walk mode", "walk", "describe", "describe scene", "summary",
               "clock mode", "zone mode", "clear path", "which way",
               "read", "read text",
               "stop", "repeat", "say again", "sonar", "sonar on", "sonar off",
               "mute", "voice on", "sound on", "speak", *TRIGGER_WORDS]
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
    return [p for p in phrases if _hearable(p)]


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
                    # Two different object names in one utterance is noise —
                    # see named_classes. The desktop recognizer force-matches
                    # ambient sound exactly as the handset's does.
                    if not looks_like_one_request(text):
                        continue
                    command = parse_command(text)
                    if not command:
                        continue
                    # A setting must have been ASKED for, not merely contained
                    # in the noise — see setting_is_deliberate.
                    if not setting_is_deliberate(command[0], text):
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
