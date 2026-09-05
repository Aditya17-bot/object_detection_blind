"""Letting the model phrase a memory, without letting it invent one.

The deterministic sentence is already correct: "Cell phone, about 2 hours ago,
near a dining table". It is also stilted, and a natural one — "The last time I
saw your phone it was on the table, about two hours ago" — is easier to act on.

The obvious way to get that is to hand the record to an LLM. The obvious way is
also how this project's central claim gets quietly destroyed: PATENT_RESEARCH
§4.7/§9 is that no guidance token originates in the model, and a freely-written
sentence about where the user's things are is exactly a guidance token.

So the same rule as `agent.argument_is_grounded` applies one layer up. **The
model may choose the WORDS. It may not choose the FACTS.** Whatever it writes is
checked against the record it was given:

  * every object name it mentions must be one the object was actually
    BESIDE -- not merely one that was somewhere in the room;
  * every number must appear in the record, or in the age phrase we supplied;
  * it must stay inside a sentence or two.

A reply that fails any of these is DISCARDED and the deterministic sentence is
spoken instead. That asymmetry is the whole design: the model can only ever
improve the phrasing, never change what is claimed, and a weak model, a
truncated reply or a hallucination all degrade to the template the app would
have said anyway.

Pure and dependency-free so the checks are testable without a model.
"""
import re

# Everything the app can name. A sentence about the user's belongings must not
# introduce an object that was never seen, and this is the vocabulary that
# makes "introduce" decidable.
from position import TARGET_CLASSES

# Two sentences is the entire budget: this is spoken aloud to someone waiting
# to act on it, and a paragraph is worse than the template it replaced.
MAX_CHARS = 160

_NUMBER = re.compile(r"\d+")
_WORD = re.compile(r"[a-z]+")

# Number words carry the same risk as digits — "three hours ago" is a claim.
#
# But they must be compared by VALUE, not by spelling. The age phrase this
# module composes says "about 2 hours ago"; a model writing "about two hours
# ago" has restated the same fact in the form a spoken interface should use,
# and an earlier version of this check rejected it as an invented number. That
# false rejection was the single commonest outcome in the first live run
# against llama3.2 — three of four rejections — so the check now normalises
# both sides to digits before comparing.
_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50",
}


def _numbers_in(text):
    """Every quantity in `text`, canonicalised to digit strings."""
    low = str(text).lower()
    found = set(_NUMBER.findall(low))
    for word in _WORD.findall(low):
        if word in _NUMBER_WORDS:
            found.add(_NUMBER_WORDS[word])
    return found


def allowed_vocabulary(record):
    """Object words this sentence is permitted to use.

    `context` is deliberately NOT included, and that is the correction of a
    real failure. The first live run against llama3.2 produced, for a record
    whose `near` was empty and whose `context` held a bed:

        "I was holding my backpack beside the bed yesterday."   (1b)
        "Your backpack was beside the bed, in the room, yesterday."  (3b)

    Both were ACCEPTED by an earlier version of this check, because `bed`
    appeared somewhere in the record. It validated the nouns and not the
    RELATIONSHIP: "also in the room" had been silently upgraded to "beside".

    A spoken sentence cannot carry that distinction reliably, and parsing for
    it would be brittle, so the model is simply never told about `context`.
    Anything it names must be something the object was actually beside. The
    deterministic fallback still uses `context` ("with a bed in view"), where
    the wording is ours and cannot drift.
    """
    words = {record.get("object", "")}
    words.update(record.get("near", ()) or ())
    return {w.lower() for w in words if w}


def _mentioned_classes(text):
    """Target-class names appearing in `text`, including multi-word ones."""
    low = text.lower()
    return {c for c in TARGET_CLASSES if c in low}


def verify_sentence(text, record):
    """True when `text` says nothing the record does not support.

    Rejection reasons are deliberately blunt: this runs on a path where the
    fallback is already correct, so a false rejection costs nothing but a
    slightly stiffer sentence, while a false acceptance puts an invented claim
    about the user's home into their ear.
    """
    if not text or not text.strip():
        return False
    text = text.strip()
    if len(text) > MAX_CHARS:
        return False

    allowed = allowed_vocabulary(record)

    # An object the record never mentioned must not appear, even in passing.
    for cls in _mentioned_classes(text):
        if cls not in allowed:
            return False

    # Numbers are claims. Every quantity in the sentence must come from the
    # record, compared by value so "two" and "2" are the same fact.
    permitted = _numbers_in(record.get("ago_phrase", ""))
    permitted.update(_numbers_in(
        " ".join(str(v) for v in record.values()
                 if not isinstance(v, (list, tuple)))))
    if not _numbers_in(text) <= permitted:
        return False

    # The sentence must still carry the PLACE. Dropping it is not a safety
    # failure but it is a quality one, and the template already does better:
    # llama3.2:1b answered a record of "bottle, near a chair" with "Your
    # bottle was beside you 10 minutes ago" -- no forbidden noun, no invented
    # number, and strictly less useful than the sentence it replaced. The
    # model's whole job here is to phrase the location, so a reply without it
    # has failed at the task even when it has not lied.
    near = [n.lower() for n in (record.get("near", ()) or ())]
    if near and not any(n in text.lower() for n in near):
        return False

    return True


def build_record(name, sighting_dict, ago_phrase, fallback):
    """The structured fact the model is allowed to talk about, and nothing more.

    `fallback` travels with it so the caller always has the deterministic
    sentence to speak when verification fails.
    """
    return {
        "object": name,
        "near": list(sighting_dict.get("near", ()) or ()),
        "context": list(sighting_dict.get("context", ()) or ()),
        "ago_phrase": ago_phrase,
        "fallback": fallback,
    }


PROMPT = """You rephrase one remembered observation for a blind user, out loud.

FACTS (the only things that exist):
  object: {object}
  it was beside: {near}
  when: {ago_phrase}

Write ONE short spoken sentence telling the user where their {object} was.
Rules:
- Speak to the user about THEIR {object}. Never say "I was holding" or "my".
- Use only the facts above. Do not add objects, rooms, places or reasons.
- Say when it was seen. The user needs to know how old this is.
- No numbers except the ones in "when".
- One sentence, under 20 words, no preamble.
"""


def render_prompt(record):
    return PROMPT.format(
        object=record["object"],
        near=", ".join(record["near"]) or "nothing recorded",
        ago_phrase=record["ago_phrase"],
    )


def phrase_memory(record, llm=None):
    """Natural sentence if the model produces a verifiable one, else the
    deterministic fallback. Never raises: this is on the speech path."""
    fallback = record.get("fallback") or ""
    if llm is None:
        return fallback, "template"
    # With nothing recorded beside the object there is no place to phrase, only
    # an age -- and the template already says that perfectly. Calling the model
    # here would buy nothing and was exactly where it started inventing a
    # location out of the room context.
    if not record.get("near"):
        return fallback, "template"
    try:
        text = llm(render_prompt(record))
    except Exception:                    # noqa: BLE001 - model must not break speech
        return fallback, "template"
    if not isinstance(text, str):
        return fallback, "template"
    text = text.strip().strip('"').split("\n")[0].strip()
    if verify_sentence(text, record):
        return text, "model"
    return fallback, "rejected"
