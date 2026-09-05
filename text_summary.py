"""Summarising a photographed page, without inventing what it says.

`read` already captures a still and OCRs it offline. Reading a full letter aloud
takes minutes, and most of the time the user only needs to know whether it is
worth hearing: a summary answers that, and `read` is still there for the rest.

**No retrieval, deliberately.** RAG solves "the corpus does not fit in the
context window". One photographed page is 300-600 words — under a thousand
tokens — so an embedding store and a retriever would buy latency and complexity
for a problem that does not exist here. Retrieval earns its place only for a
different feature: asking questions across many previously scanned documents.

**The failure mode that matters is a fabricated figure.** A summary of a bill
or a medical letter that invents an amount, a date or a reference number is not
a quality problem, it is a safety one, and small models fabricate exactly those.
So the same rule as `memory_phrasing`: every number in the summary must appear
in the source text. That is mechanically checkable, unlike the prose, and it
covers the class of error with real consequences.

What this canNOT check is honest and worth stating: the source is arbitrary
text, so there is no vocabulary to validate nouns against the way there is for
a memory record. A summary may still mischaracterise the document in words.
That is why the spoken answer always ends by offering the full text — the
summary is a triage aid, never a substitute for reading it.
"""
import re

# Long enough to say what a letter is about, short enough to stay a summary.
# Beyond this the user should just have `read` speak the thing.
MAX_CHARS = 400

# Below this there is nothing to summarise, and asking a model to try is how
# you get a confident paragraph about three words of menu.
MIN_SOURCE_CHARS = 80

_NUMBER = re.compile(r"\d+")

# Digits spelled out, so "three hundred" cannot smuggle past a digit check.
_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "twenty": "20",
    "thirty": "30", "forty": "40", "fifty": "50", "hundred": "100",
    "thousand": "1000",
}

_WORD = re.compile(r"[a-z]+")

# Meta-commentary the model addresses to ITSELF rather than to the user, and
# whole parenthetical asides. llama3.2:3b ended a live prescription summary
# with "(Note: I have followed the rules provided, avoiding adding any extra
# information)" -- not false, so verification will never catch it, and not
# something a blind user asking about their medicine should have read to them.
# Parentheses in a one-sentence spoken summary carry nothing worth the risk.
_PARENTHETICAL = re.compile(r"\s*\([^)]*\)")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Words that carry no content, so they cannot make a restatement look new.
_FILLER = {"a", "an", "the", "and", "or", "it", "its", "is", "are", "was",
           "were", "this", "that", "of", "to", "for", "in", "on", "with",
           "about", "as", "be", "has", "have", "also"}


def clean_reply(text):
    """Strip a model's asides and its self-repetition.

    Small models restate their own first sentence -- one live reply was "This
    document is a prescription for a patient. It contains instructions... The
    document is a prescription for a patient, and it contains instructions..."
    Saying it twice wastes the listener's time, and time is the whole reason a
    summary exists.
    """
    text = _PARENTHETICAL.sub("", " ".join((text or "").split()))
    said, kept = set(), []
    for part in _SENTENCE_SPLIT.split(text):
        part = part.strip()
        if not part:
            continue
        words = {w for w in re.sub(r"[^a-z ]", " ", part.lower()).split()
                 if w not in _FILLER}
        # A restatement rarely repeats a sentence verbatim; it merges two
        # earlier ones and adds a conjunction. So the test is CONTENT overlap,
        # not equality: a sentence that says almost nothing new is dropped.
        if words and len(words & said) / len(words) >= 0.8:
            continue
        said |= words
        kept.append(part)
    return " ".join(kept).strip()


def _numbers_in(text):
    """Every quantity in `text`, canonicalised to digit strings."""
    low = str(text).lower()
    found = set(_NUMBER.findall(low))
    for w in _WORD.findall(low):
        if w in _NUMBER_WORDS:
            found.add(_NUMBER_WORDS[w])
    return found


def trim_to_sentence(text, limit=MAX_CHARS):
    """Cut `text` to `limit` at a sentence boundary where possible.

    Length is a VERBOSITY problem, not a truthfulness one, and rejecting a long
    reply outright threw away summaries that said nothing false. A live
    llama3.2:3b summary of a prescription was refused for exactly this: it
    contained no figures at all and was simply wordy. Truncating mirrors what
    `agent.clean_say` already does for chat replies.
    """
    text = " ".join((text or "").split()).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for end in (". ", "! ", "? "):
        i = cut.rfind(end)
        if i > limit // 3:
            return cut[:i + 1].strip()
    i = cut.rfind(" ")
    return (cut[:i] if i > 0 else cut).strip()


def verify_summary(summary, source):
    """True when `summary` states no figure the source does not contain.

    Deliberately one-sided, and deliberately about FIGURES only. A false
    rejection costs the user a summary they could have had; a false acceptance
    puts an invented amount or date into the ear of someone who cannot check it
    against the page. Length is handled by `trim_to_sentence` rather than here,
    because a wordy summary is not a false one.
    """
    if not summary or not summary.strip():
        return False
    return _numbers_in(summary) <= _numbers_in(source)


PROMPT = """Summarise this text for a blind user who cannot see the page.

TEXT:
{text}

Say in one or two short sentences what this document IS and what it is about.
Rules:
- Use only what the text says. Never add facts, amounts, dates or names.
- If it is a letter or a bill, say who it appears to be from and what it wants.
- Do not quote figures unless they appear in the text exactly.
- No preamble, no "this document says". Under 50 words.
"""

# Appended to every accepted summary. The summary is a triage aid: the user
# decides from it whether to spend two minutes on the full text, and they can
# only make that choice if they are told the full text is available.
FULL_TEXT_OFFER = "Say read for the full text."


def render_prompt(text, max_source=6000):
    """The prompt for `text`, truncated to something a small model can hold."""
    return PROMPT.format(text=text[:max_source])


def summarise(text, llm=None):
    """(spoken message, how) for OCR'd `text`.

    `how` is one of: too_short, no_model, model, rejected, failed — reported so
    the field log can tell a model that was never asked from one that was
    overruled.
    """
    text = (text or "").strip()
    if len(text) < MIN_SOURCE_CHARS:
        return "There is not enough text here to summarise.", "too_short"
    if llm is None:
        return "Summarising needs the laptop. Say read for the text.", "no_model"

    try:
        reply = llm(render_prompt(text))
    except Exception:                    # noqa: BLE001 - never break speech
        return "I could not summarise that. Say read for the full text.", "failed"
    if not isinstance(reply, str):
        return "I could not summarise that. Say read for the full text.", "failed"

    reply = trim_to_sentence(clean_reply(reply.strip().strip('"')))
    if not verify_summary(reply, text):
        # The summary said something the page does not. The user gets the page.
        return ("I could not summarise that safely. Say read for the full text.",
                "rejected")
    return f"{reply} {FULL_TEXT_OFFER}", "model"
