"""BlindAssist — agent layer: capability registry, two-tier router, executor.

Pure logic, same philosophy as position.py / decision.py: no camera, no model,
no microphone, no network at import time. Everything here takes plain data and
injected callables, so the whole layer is unit-testable in milliseconds.

WHY THIS EXISTS
---------------
The 13 capabilities were declared in four places (voice.py's parser, its phrase
list, webapp.py's dispatch, and the Dart equivalents) and had already drifted:
webapp.py silently dropped read/sonar/stop/repeat/mute. TOOLS below is the one
declarative table; it drives the recognizer's phrase list, the LLM's tool
schema, the single executor, and a committed capabilities.json manifest that
the test suites assert against.

THE AUTHORITY BOUNDARY (the part that matters)
----------------------------------------------
Tier 1 hands an utterance to a local offline LLM. That model may SELECT a tool
and an argument. It may NEVER author a word the user hears:

  * validate_action() treats the model's output as untrusted input — unknown
    tool, unknown class, missing argument, malformed value, prose instead of
    JSON, timeout, or any exception all become ABSTAIN.
  * even the clarifying question is chosen from ASK_TEMPLATES by key, not
    written by the model.

So every spoken token still originates in decision.py / position.py (the same
functions the buttons call, pinned by the same tests) or in a fixed template.
Fabricated perception is impossible by construction, not discouraged by prompt.

AND THE ROUTER NEVER RAISES. An exception on the voice thread silently kills
speech recognition for the whole session — that is not hypothetical, it is what
happened when "clock mode" reached a dispatcher that did not know about it (see
webapp.py:_on_voice_command). route() catches everything and abstains.
"""

import json
import time
from dataclasses import dataclass, field

from position import TARGET_CLASSES
from voice import grammar_phrases as _voice_grammar_phrases
from voice import parse_command, resolve_class

# --------------------------------------------------------------------------
# Fixed spoken templates — the ONLY strings this module may put in the user's
# ear. The model picks a key; it never writes the sentence.
# --------------------------------------------------------------------------

ASK_TEMPLATES = {
    "unknown": ("Sorry, I can't do that. I can find things, describe the "
                "scene, count them, read text, or check your path."),
    "not_understood": "Sorry, I didn't catch that. Say it again?",
    "which_object": "Which object should I look for?",
    "unsupported": "That control isn't available here.",
    "listening": "Yes?",
    "working": "One moment",
}
DEFAULT_ASK = "unknown"

# The subset the MODEL may choose from. "listening", "working" and
# "unsupported" are control acknowledgements the host speaks at a moment it
# alone knows about; letting the router pick them produced a real failure —
# llama3.2:3b answered "how are you today" with "Yes?", which sounds like the
# app mis-heard a trigger word. Anything else the model asks for is clamped to
# DEFAULT_ASK rather than spoken.
MODEL_TEMPLATES = ("unknown", "not_understood", "which_object")

# Saying "assistant" opens the open-dictation window (see voice.TRIGGER_WORDS).
# Kept in the registry as an INTERNAL tool: it is a control action, not a
# capability, so it is never offered to the LLM.
TRIGGER_HINT = "assistant"


# --------------------------------------------------------------------------
# Capability registry — the single source
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolSpec:
    """One capability. `name` is byte-identical to the action string
    parse_command already emits, so tier 0 and tier 1 produce the same shape."""
    name: str
    description: str          # one line, goes to the LLM verbatim
    arg: str = None           # None | "class" | "onoff" | "template"
    required: bool = False
    examples: tuple = ()      # spoken forms; also feed the recognizer grammar
    internal: bool = False    # true -> never offered to the LLM


TOOLS = (
    ToolSpec("walk", "switch to continuous obstacle warnings while walking",
             examples=("walk mode", "walk")),
    ToolSpec("find", "start searching for one object and report where it is",
             arg="class", required=True,
             examples=("find bottle", "find the door")),
    ToolSpec("describe", "one-sentence summary of everything visible now",
             examples=("describe", "describe scene", "summary")),
    ToolSpec("count", "how many of one object class are visible right now",
             arg="class", required=True, examples=("how many chairs",)),
    ToolSpec("recall", "where an object was last seen, after it left the view",
             arg="class", required=True, examples=("where is the cup",)),
    ToolSpec("path", "which walking direction is clearest right now",
             examples=("clear path", "which way")),
    ToolSpec("check", "what is in one direction; argument left, ahead or right",
             arg="direction", required=True,
             examples=("what is on my left", "is there anything in front of me",
                       "anything on my right")),
    ToolSpec("read", "read printed text aloud from the camera",
             examples=("read", "read text")),
    # A photo is for someone ELSE to look at — the user cannot review it. It
    # exists so a blind user can capture something and hand it to a sighted
    # person, so it must land in the phone's gallery, not app-private storage.
    ToolSpec("photo", "take a photo and save it to the phone's gallery",
             examples=("take a picture", "take a photo", "photo")),
    # No model, no network: both are computed from the camera's own pixels on
    # the phone, so they answer with the laptop off. Matching clothes and
    # knowing whether a room is lit are ordinary daily problems that object
    # detection does not touch.
    ToolSpec("colour", "name the colour of whatever the camera is pointed at",
             examples=("what colour is this", "what color is this", "colour")),
    ToolSpec("light", "how bright it is here, e.g. whether a room is lit",
             examples=("is the light on", "how bright is it",
                       "is it dark here")),
    ToolSpec("clock", "speak directions as clock bearings, e.g. 2 o'clock",
             examples=("clock mode",)),
    ToolSpec("zones", "speak directions as left, ahead and right",
             examples=("zone mode",)),
    ToolSpec("sonar", "the proximity beeps; argument on or off, omit to toggle",
             arg="onoff", examples=("sonar", "sonar on", "sonar off")),
    ToolSpec("mute", "the spoken voice; argument on to silence, off to restore",
             arg="onoff", required=True, examples=("mute", "unmute")),
    ToolSpec("stop", "stop the current announcement",
             examples=("stop",)),
    ToolSpec("repeat", "say the last announcement again",
             examples=("repeat", "say again")),
    # Selectable by the model, and the destination of every validation failure.
    ToolSpec("abstain",
             "the request is not something these tools do, or you cannot tell "
             "which tool is meant — prefer this over guessing",
             arg="template", examples=()),
    # Internal: the open-dictation trigger word. Not a capability.
    ToolSpec("ask", "open the dictation window", internal=True,
             examples=(TRIGGER_HINT,)),
)

BY_NAME = {spec.name: spec for spec in TOOLS}

# The class enumeration is derived from the DETECTOR's own class list, so a
# tool argument can never name something the pipeline cannot detect.
ARG_ENUMS = {
    "class": tuple(sorted(TARGET_CLASSES)),
    "onoff": ("on", "off"),
    "template": tuple(sorted(ASK_TEMPLATES)),
    "direction": ("left", "ahead", "right"),
}

# Spoken variants the model (or a phone) may send for a direction. Same
# forgiving-in/strict-out rule as every other argument: resolved here, then it
# still has to be a member of ARG_ENUMS["direction"].
_DIRECTION_ALIASES = {"front": "ahead", "forward": "ahead", "centre": "ahead",
                      "center": "ahead", "straight": "ahead",
                      "in front": "ahead", "in front of me": "ahead",
                      "my left": "left", "my right": "right",
                      "on my left": "left", "on my right": "right"}

# Keys the model might plausibly use for its argument. Forgiving on the way in,
# strict on the way out — the value still has to survive ARG_ENUMS.
_ARG_KEYS = ("object", "value", "target", "class", "arg", "name", "template",
             "state")

# Tools whose effect lives OUTSIDE the guidance engine and therefore needs a
# hook. If the host does not supply one, the capability is genuinely absent and
# we say so instead of silently doing nothing (the bug this table replaces).
_HOOK_TOOLS = {"sonar", "mute", "stop", "repeat", "read", "photo", "ask"}


@dataclass(frozen=True)
class Action:
    tool: str
    arg: str = None

    def as_command(self):
        """The (action, target) tuple shape the existing dispatchers use."""
        return (self.tool, self.arg)


@dataclass
class RouteResult:
    actions: list = field(default_factory=list)
    source: str = "abstain"      # grammar | llm | chat | abstain
    latency_ms: float = 0.0
    ask: str = None              # ASK_TEMPLATES key when source == "abstain"
    error: str = None            # why tier 1 failed, for the UI/eval log
    say: str = None              # MODEL-AUTHORED conversational reply (chat)

    @property
    def message(self):
        """What to speak: a model-authored chat reply, an abstention template,
        or None. `say` is the ONE string in this system the model wrote — see
        the module docstring's authority-boundary note."""
        if self.say:
            return self.say
        return ASK_TEMPLATES[self.ask] if self.ask else None


# --------------------------------------------------------------------------
# Derived artifacts — grammar, schemas, manifest
# --------------------------------------------------------------------------

def grammar_phrases():
    """Every phrase the recognizer should be able to hear.

    A SUPERSET of voice.grammar_phrases(): the shipped list is kept verbatim so
    recognition of the trained phrasings cannot regress, and the registry adds
    its own examples plus the dictation trigger. Passed to VoiceListener at
    construction, so the registry drives the recognizer at runtime rather than
    merely documenting it."""
    phrases = set(_voice_grammar_phrases())
    for spec in TOOLS:
        phrases.update(spec.examples)
    return sorted(phrases)


def tool_schemas():
    """OpenAI-style function schemas for the registry (paper table T1, and for
    hosts that prefer the tools API over the prompt listing below)."""
    schemas = []
    for spec in TOOLS:
        if spec.internal:
            continue
        params = {"type": "object", "properties": {}, "required": []}
        if spec.arg:
            params["properties"]["value"] = {
                "type": "string", "enum": list(ARG_ENUMS[spec.arg])}
            if spec.required:
                params["required"].append("value")
        schemas.append({"type": "function", "function": {
            "name": spec.name, "description": spec.description,
            "parameters": params}})
    return schemas


def prompt_tool_list():
    """Compact text listing sent to the model. Small instruct models follow a
    plain enumeration plus format=json far more reliably than the tool-call
    API, and the class enum is emitted ONCE here rather than repeated inside
    every tool's schema — the prompt-size lever that keeps tier-1 latency
    survivable on a CPU."""
    lines = []
    for spec in TOOLS:
        if spec.internal:
            continue
        if spec.arg == "class":
            arg = "object" + ("" if spec.required else " (optional)")
        elif spec.arg == "onoff":
            arg = "on or off" + ("" if spec.required else " (optional)")
        elif spec.arg == "direction":
            arg = "left, ahead or right"
        elif spec.arg == "template":
            arg = " or ".join(MODEL_TEMPLATES)
        else:
            arg = "none"
        lines.append(f"{spec.name} | arg: {arg} | {spec.description}")
    return "\n".join(lines)


def capabilities_manifest():
    """The cross-site contract, written to capabilities.json and asserted
    against by the Python tests (and by the Dart suite once the port lands)."""
    return {
        "version": 1,
        "tools": [{"name": s.name, "arg": s.arg, "required": s.required,
                   "internal": s.internal, "examples": list(s.examples)}
                  for s in TOOLS],
        "enums": {k: list(v) for k, v in ARG_ENUMS.items()},
        "ask_templates": dict(ASK_TEMPLATES),
    }


# --------------------------------------------------------------------------
# Validation — the authority boundary
# --------------------------------------------------------------------------

def argument_is_grounded(spec, arg, utterance):
    """Did the user actually say this argument?

    The model may CHOOSE a capability. It may not INVENT the capability's
    argument. Measured on the 2026-08-02 field walk, `llama3.2:3b` given the
    single word "door" emitted `check(left)` — a direction that appears nowhere
    in the input — and did the same for "the cup", "bag" and "the person". The
    user heard "Nothing on your left" repeatedly and had said no such thing.

    Tool-name and enum validation cannot catch this: `left` IS a valid
    direction and `check` IS a real capability, so the action is well-formed.
    What is wrong with it is not its shape but its PROVENANCE — it is a fact
    about the user's request that came from the model rather than the user.
    That is the same boundary §4.7 draws around perceptual claims, applied to
    the argument slot.

    Deliberately applied to DIRECTION and STATE arguments only, NOT to class
    names, and the asymmetry is the whole design:

      * A direction argument is drawn from {left, right, ahead} and those are
        also the words a person says. There is no paraphrase of "left" that
        is not the word "left", so if the utterance contains no direction, the
        model did not infer one — it made one up.
      * A class argument is exactly where paraphrase lives: "the exit" means
        the door, "my water bottle" means the bottle, "the fridge" means the
        refrigerator. Requiring the class name to appear verbatim would delete
        the capability tier 1 exists to provide (paraphrase accuracy 0% -> 47%
        in the frozen evaluation). Class names stay guarded by vocabulary
        membership instead, which is what stops them naming something the
        detector cannot see.

    Free-text arguments (a spoken template) are exempt: they have no
    counterpart in the utterance by construction.
    """
    if not utterance or spec.arg is None or arg is None:
        return True
    words = utterance.lower().split()
    if spec.arg == "direction":
        return any(_DIRECTION_ALIASES.get(w, w) == arg for w in words)
    if spec.arg == "onoff":
        return arg in words
    return True                       # class names, templates, free-form slots


def validate_action(raw, utterance=None):
    """One raw model action -> Action, or None if it must be rejected.

    Rejects: non-objects, unknown tool names, internal tools (the model may not
    drive the dictation window), missing required arguments, class names the
    detector does not know, anything outside an argument's enum, and — when
    `utterance` is supplied — any argument the user did not actually say (see
    `argument_is_grounded`). Synonyms and plurals are resolved through the
    PARSER's own vocabulary, so tier 1 cannot accept an object name that tier 0
    would refuse."""
    if not isinstance(raw, dict):
        return None
    name = raw.get("tool") or raw.get("name") or raw.get("function")
    if isinstance(name, dict):            # {"function": {"name": ...}}
        name = name.get("name")
    if not isinstance(name, str):
        return None
    spec = BY_NAME.get(name.strip().lower())
    if spec is None or spec.internal:
        return None

    value = raw.get("args") if isinstance(raw.get("args"), dict) else raw
    if not isinstance(value, dict):
        value = {}
    arg = None
    for key in _ARG_KEYS:
        if isinstance(value.get(key), str) and value[key].strip():
            arg = value[key].strip()
            break

    if spec.arg is None:
        return Action(spec.name)          # stray arguments are simply dropped
    if arg is None:
        if spec.required:
            return None
        return Action(spec.name)
    if spec.arg == "class":
        arg = resolve_class(arg)
        if arg is None:
            return None
    else:
        arg = arg.lower()
        if spec.arg == "direction":
            arg = _DIRECTION_ALIASES.get(arg, arg)
        if spec.arg == "template" and arg not in MODEL_TEMPLATES:
            arg = DEFAULT_ASK          # clamped, never spoken as chosen
        if arg not in ARG_ENUMS[spec.arg]:
            return None
    if not argument_is_grounded(spec, arg, utterance):
        # Required argument invented -> the action is unusable, reject it.
        # Optional one invented -> keep the capability, drop the invention
        # (an ungrounded "sonar off" becomes a plain toggle rather than a
        # silent, unrequested state change).
        if spec.required:
            return None
        return Action(spec.name)
    return Action(spec.name, arg)


# --------------------------------------------------------------------------
# Deterministic state summary
# --------------------------------------------------------------------------

def state_summary(infos, engine=None, now=0.0):
    """Compact FACTS for the router, built from the detector's own output and
    engine state — never from a description.

    This is what lets "is it still there" resolve against ObjectInfo instead of
    the model's imagination, and it is why the model's job stays small enough
    for a 1-4 B local model: map English onto a tool plus an argument from a
    closed set."""
    grouped = {}
    for i in infos or ():
        entry = grouped.setdefault(i.name, {"name": i.name, "zone": i.h_zone,
                                            "proximity": i.proximity,
                                            "count": 0, "_area": -1.0})
        entry["count"] += 1
        if i.area > entry["_area"]:       # describe the most visible instance
            entry.update(zone=i.h_zone, proximity=i.proximity, _area=i.area)
    visible = [{k: v for k, v in e.items() if k != "_area"}
               for e in grouped.values()]

    memory = getattr(engine, "_memory", None) or {}
    ttl = getattr(engine, "memory_ttl", 30.0)
    remembered = sorted(name for name, (_, seen) in memory.items()
                        if now - seen <= ttl)
    return {
        "mode": getattr(engine, "mode", "walk"),
        "target": getattr(engine, "target", None),
        "clock": bool(getattr(engine, "use_clock", True)),
        "visible": visible,
        "last_said": getattr(engine, "_last_msg", None),
        "remembered": remembered,
    }


def render_state(state):
    """The state block as the few lines the model actually reads."""
    if not state:
        return "Mode: walk. Nothing visible."
    parts = [f"Mode: {state.get('mode', 'walk')}"]
    if state.get("target"):
        parts[0] += f" (searching for {state['target']})"
    visible = state.get("visible") or []
    if visible:
        seen = ", ".join(
            f"{v['count']} {v['name']} {v.get('zone', 'center')}"
            f" {v.get('proximity', 'medium')}" for v in visible)
        parts.append(f"Visible now: {seen}")
    else:
        parts.append("Visible now: nothing")
    if state.get("remembered"):
        parts.append("Seen recently: " + ", ".join(state["remembered"]))
    if state.get("last_said"):
        parts.append(f"Last said: {state['last_said']}")
    return ". ".join(parts)


# --------------------------------------------------------------------------
# The two-tier router
# --------------------------------------------------------------------------

# Longest model-authored reply we will speak. A blind user cannot skim, cannot
# skip ahead, and cannot see that a monologue is coming — length is a usability
# property here, not a formatting preference. Overruns are cut at a sentence.
# Raised 240 -> 400 on 2026-08-03 when open conversation was enabled: "what can
# this app do" has a genuinely longer honest answer than a guidance phrase, and
# "stop" already exists for a reply the user does not want to sit through.
MAX_SAY_CHARS = 400
# Shorter than this WITHOUT terminal punctuation reads as a truncation, not a
# reply. "Yes." and "No." are fine; "I don" is not.
MIN_SAY_CHARS = 12


def clean_say(raw):
    """Model free text -> a speakable reply, or None if it is not usable.

    The model may write this sentence (user decision 2026-07-31, chat mode),
    which makes it untrusted input like any other: a non-string, an empty
    string, or a JSON blob that leaked through is rejected rather than read
    aloud, and anything over MAX_SAY_CHARS is truncated at the last sentence
    end so the user never gets a monologue they cannot interrupt."""
    if not isinstance(raw, str):
        return None
    text = " ".join(raw.split())
    if not text or text.startswith(("{", "[")):
        return None
    if len(text) > MAX_SAY_CHARS:
        cut = text[:MAX_SAY_CHARS]
        stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = cut[:stop + 1] if stop > 40 else cut.rsplit(" ", 1)[0]
    text = text.strip()
    if not text:
        return None
    # A reply cut off mid-sentence by the token budget: Ollama's JSON mode
    # closes the string when num_predict runs out, so the router receives a
    # syntactically perfect `{"say": "I don"}`. Speaking half a word is worse
    # than abstaining, and the 2026-08-01 eval run produced exactly that twice.
    if len(text) < MIN_SAY_CHARS and text[-1] not in ".!?":
        return None
    return text


# Tool names a model reaches for when it means "just answer". None of them is a
# real capability, so validate_action would reject them — which would throw the
# answer away instead of speaking it.
_SAY_TOOLS = ("say", "answer", "speak", "reply", "chat", "respond")


def _say_shaped_action(raw):
    """A chat reply dressed up as a tool call -> the sentence, else None."""
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("tool") or item.get("name")
        if not isinstance(name, str) or name.strip().lower() not in _SAY_TOOLS:
            continue
        args = item.get("args") if isinstance(item.get("args"), dict) else item
        for key in ("value", "text", "message", "say", "content", "answer"):
            said = clean_say(args.get(key) if isinstance(args, dict) else None)
            if said:
                return said
    return None


class AgentRouter:
    """Tier 0 = the shipped keyword grammar (~0 ms, no model, works offline).
    Tier 1 = a local offline LLM, consulted ONLY on a tier-0 miss.

    llm=None leaves tier 1 disabled, and the router is then behaviourally
    identical to today's system — a property enforced by a regression test over
    every phrase in the grammar. Degradation is toward FEWER capabilities,
    never toward wrong ones.

    allow_chat opens the narrow hole in the authority boundary: on a tier-0
    miss the model may return a sentence of its own instead of a tool call, and
    that sentence is spoken. It is answered from `state` — the detector's own
    output — never from the model's world knowledge, and it can only ever be a
    REPLY. Guidance (walk warnings, find, distance, clear path, check) is still
    generated exclusively by decision.py. allow_chat=False restores the
    original absolute rule and is what the paper's ablation arm uses."""

    def __init__(self, llm=None, parse=parse_command, max_actions=2,
                 allow_chat=True):
        self.llm = llm
        self._parse = parse
        self.max_actions = max_actions
        self.allow_chat = allow_chat

    @property
    def enabled(self):
        return self.llm is not None

    def route(self, text, state=None):
        started = time.monotonic()

        def done(**kw):
            kw.setdefault("latency_ms", (time.monotonic() - started) * 1000)
            return RouteResult(**kw)

        text = (text or "").strip()
        if not text:
            return done(ask="not_understood")

        # -- tier 0 --------------------------------------------------------
        try:
            command = self._parse(text)
        except Exception as exc:          # a broken parser must not kill voice
            command = None
            print(f"agent: tier-0 parse failed ({exc})")
        if command:
            return done(actions=[Action(command[0], command[1])],
                        source="grammar")

        # -- tier 1 --------------------------------------------------------
        if self.llm is None:
            return done(ask=DEFAULT_ASK)
        try:
            raw = self.llm.route(text, render_state(state), prompt_tool_list())
        except Exception as exc:          # timeout, refused connection, garbage
            return done(ask=DEFAULT_ASK, error=f"llm unavailable ({exc})")

        # A conversational reply, checked BEFORE the action list: the model
        # answers a question with {"say": "..."} and calls a tool with
        # {"actions": [...]}. An action always wins if it sent both — doing the
        # thing beats talking about it.
        said = None
        if isinstance(raw, dict) and not raw.get("actions"):
            said = clean_say(raw.get("say") or raw.get("answer"))
        else:
            if isinstance(raw, dict):
                raw = raw["actions"]
            # Small models routinely express the reply as a tool call named
            # "say" — llama3.2:3b does it on roughly every chat turn. Accept
            # the shape rather than losing the answer to a format quibble; the
            # text still goes through clean_say and is still only ever a reply.
            said = _say_shaped_action(raw)
        if said:
            if not self.allow_chat:
                return done(ask=DEFAULT_ASK, error="chat disabled")
            return done(say=said, source="chat")

        if isinstance(raw, dict):
            raw = raw.get("actions", raw)
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list) or not raw:
            # prose, an empty answer, or anything else unparseable. Never text
            # to speak — the model has no authority to author a reply.
            return done(ask=DEFAULT_ASK, error="no tool call in model output")

        actions = []
        for item in raw[:self.max_actions]:
            # `text` is passed so an argument the user never said is rejected:
            # the model chooses the capability, the user supplies its argument.
            action = validate_action(item, text)
            if action is None:
                return done(ask=DEFAULT_ASK, error=f"rejected action {item!r}")
            if action.tool == "abstain":
                return done(ask=action.arg or DEFAULT_ASK, source="abstain")
            actions.append(action)
        if not actions:
            return done(ask=DEFAULT_ASK, error="no valid actions")
        return done(actions=actions, source="llm")


# --------------------------------------------------------------------------
# The single executor
# --------------------------------------------------------------------------

@dataclass
class Hooks:
    """Effects that live outside the GuidanceEngine, injected by the host.

    Deliberately does NOT include set_mode/set_clock: those are pure engine
    calls, and routing them through a host callback that re-takes the host's
    lock would deadlock (webapp.py holds it across execute_action). Anything
    left as None means the host genuinely lacks that capability, and the
    executor says so out loud rather than doing nothing."""
    set_sonar: object = None      # (bool | None) -> None; None means toggle
    set_mute: object = None       # (bool) -> None
    stop: object = None           # () -> None
    repeat: object = None         # () -> str | None  (the text to say again)
    read_text: object = None      # () -> str | None
    take_photo: object = None     # () -> str | None  (what to say afterwards)
    dictate: object = None        # () -> None; opens the dictation window

    def get(self, tool):
        return {"sonar": self.set_sonar, "mute": self.set_mute,
                "stop": self.stop, "repeat": self.repeat,
                "read": self.read_text, "photo": self.take_photo,
                "ask": self.dictate}.get(tool)


def execute_action(action, engine, infos, now, hooks=None):
    """Run one validated Action; return the text to speak, or None.

    Does NOT speak: the caller announces, so hosts keep their own locking and
    announcement plumbing. Every returned string comes from decision.py /
    position.py or from ASK_TEMPLATES — see the module docstring."""
    hooks = hooks or Hooks()
    tool, arg = action.tool, action.arg

    if tool == "abstain":
        return ASK_TEMPLATES.get(arg or DEFAULT_ASK, ASK_TEMPLATES[DEFAULT_ASK])

    if tool in _HOOK_TOOLS:
        fn = hooks.get(tool)
        if fn is None:
            return ASK_TEMPLATES["unsupported"]
        if tool == "sonar":
            fn(None if arg is None else arg == "on")
            return "Sonar on" if arg == "on" else (
                "Sonar off" if arg == "off" else None)
        if tool == "mute":
            fn(arg == "on")
            # nothing is spoken when muting: the confirmation would be the last
            # thing heard and would contradict itself
            return None if arg == "on" else "Voice on"
        if tool == "stop":
            fn()
            return None
        if tool == "ask":
            fn()
            # the acknowledgement is a fixed template too: even "Yes?" is not
            # the model's to write
            return ASK_TEMPLATES["listening"]
        return fn()                       # repeat / read return their own text

    if tool == "walk":
        engine.set_mode("walk")
        return "Walk mode"
    if tool == "find":
        engine.set_mode("find", arg)
        return f"Finding {arg}"
    if tool in ("clock", "zones"):
        engine.set_clock(tool == "clock")
        return "Clock mode" if tool == "clock" else "Zone mode"
    if tool == "describe":
        return engine.describe(infos, now)
    if tool == "count":
        return engine.count(infos, arg, now)
    if tool == "recall":
        return engine.recall(arg, now)
    if tool == "path":
        return engine.path(infos, now)
    if tool == "check":
        # None = a direction the engine refused; abstain rather than guess.
        return engine.check(infos, arg, now) or ASK_TEMPLATES["not_understood"]
    return None                           # unreachable: validate_action gates


def execute(result, engine, infos, now, hooks=None):
    """Run a whole RouteResult; returns the list of messages to speak in order.
    An abstention yields exactly its template, a chat reply yields itself."""
    if not result.actions and result.message:
        return [result.message]
    out = []
    for action in result.actions:
        message = execute_action(action, engine, infos, now, hooks)
        if message:
            out.append(message)
    return out


# --------------------------------------------------------------------------
# Local offline LLM client (Ollama)
# --------------------------------------------------------------------------

_SYSTEM = """You are the assistant inside a camera app for a blind user.
You do one of two things with each request: run a tool, or answer in one short
sentence.

Tools:
{tools}

Object names you may use as an argument:
{classes}

To run tools, reply exactly:
{{"actions": [{{"tool": "find", "args": {{"value": "bottle"}}}}]}}

To answer a question or make conversation, reply exactly:
{{"say": "one short sentence"}}

About the app, so you can explain it when asked:
BlindAssist is an offline camera assistant for blind and low-vision users. The
phone camera streams to a small object detector; the app speaks short guidance
like "chair on your right, close". Walk mode warns only about things close
enough to matter. Find mode searches for one object and reports where it is.
It can also describe a scene, count objects, remember where something was last
seen, say which way is clearest, read printed text aloud, take a photo, and
give stereo beeps that get faster as an obstacle gets nearer. Everything runs
without an internet connection, and it never sends pictures anywhere.

Rules:
- Prefer a tool whenever one matches. A tool is always better than talking
  about what the tool would do.
- At most two actions, in the order the user asked for them.
- Use only the tool names and object names listed above.
- ANYTHING ELSE — greetings, small talk, general knowledge, questions about
  yourself or the app, jokes — gets a {{"say": "..."}} reply. Answer it
  normally and helpfully, the way any assistant would. Do not abstain just
  because a question is off-topic; off-topic conversation is allowed and
  expected.
- General knowledge is FINE and you should just answer it, in full, from what
  you know — history, geography, maths, cooking, sport, definitions, jokes,
  advice — exactly as any assistant would. Examples of correct replies:
  {{"say": "Paris."}} / {{"say": "France won it in 1998."}} /
  {{"say": "Ninety-six."}}
  The camera limit below is ONLY about the room around the user. It never
  applies to a question about the wider world, and "I cannot see that" is
  never the right answer to one.
- TWO HARD LIMITS on a "say" reply, and only two:
  1. Never claim anything about the user's SURROUNDINGS — what is in the room,
     where an object is, how far away it is, whether something is there. The
     STATE block is the only thing you know about that; if it does not cover
     what was asked, say you cannot see that and offer the matching tool.
  2. Never give walking, crossing, or safety instructions — route those to
     the path or check tool instead.
- Keep it to one or two short sentences. The user hears this out loud and
  cannot skim it.
- Only abstain when the user clearly wanted an ACTION you have no tool for
  (making a call, sending a message, playing music), reply
  {{"actions": [{{"tool": "abstain", "args": {{"value": "unknown"}}}}]}}."""


class OllamaRouter:
    """Thin client for a locally running Ollama instance.

    keep_alive matters more than it looks: Ollama unloads an idle model after
    five minutes by default, and the reload lands on exactly the utterance the
    user cared about. warmup() and a long keep_alive together are the
    difference between a 2 s route and a 15 s one.

    Uses urllib rather than requests so the agent layer adds no dependency."""

    def __init__(self, model="llama3.2:3b",
                 host="http://127.0.0.1:11434", timeout=8.0,
                 keep_alive="30m", num_predict=128):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.num_predict = num_predict
        self.error = None

    def _post(self, path, payload, timeout=None):
        import urllib.request
        request = urllib.request.Request(
            self.host + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request,
                                    timeout=timeout or self.timeout) as resp:
            return json.loads(resp.read().decode())

    def warmup(self):
        """Load the model now, not on the user's first question. Returns True
        on success; a failure is recorded in .error and left non-fatal — the
        system still works, it just has no tier 1."""
        try:
            self._post("/api/chat", {
                "model": self.model, "stream": False,
                "keep_alive": self.keep_alive,
                "options": {"temperature": 0, "num_predict": 1},
                "messages": [{"role": "user", "content": "hi"}],
            }, timeout=max(self.timeout, 120.0))
            self.error = None
            return True
        except Exception as exc:
            self.error = f"ollama unavailable ({exc})"
            return False

    def route(self, text, state_text, tool_list):
        """Utterance -> raw action list. Raises on transport failure; the
        AgentRouter converts that to an abstention."""
        system = _SYSTEM.format(tools=tool_list,
                                classes=", ".join(ARG_ENUMS["class"]))
        data = self._post("/api/chat", {
            "model": self.model, "stream": False, "format": "json",
            "keep_alive": self.keep_alive,
            # Reasoning models (qwen3 and friends) spend the token budget on a
            # thinking block and return no JSON at all: the 2026-08-01 qwen3:4b
            # arm produced "no tool call in model output" on 102 of 140 calls,
            # at 6-8 s each. Ollama ignores this key on models without a
            # thinking mode, so it is safe to send unconditionally.
            "think": False,
            "options": {"temperature": 0, "num_predict": self.num_predict},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",
                 "content": f"{state_text}\n\nRequest: \"{text}\""},
            ],
        })
        content = (data.get("message") or {}).get("content", "")
        try:
            return json.loads(content)
        except (ValueError, TypeError):
            # prose instead of JSON -> no tool call -> abstain upstream.
            # It is NEVER treated as text to speak.
            return []


# --------------------------------------------------------------------------

MANIFEST_PATH = "capabilities.json"


def _write_manifest(path=MANIFEST_PATH):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(capabilities_manifest(), fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    import sys
    if "--write-manifest" in sys.argv:
        _write_manifest()
    else:
        print(prompt_tool_list())
