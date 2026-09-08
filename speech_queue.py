"""BlindAssist — chunking and resumption for spoken read-outs.

Why this exists
---------------
`Speaker` has always had ONE rule for a new message: latest wins, the current
utterance is cut off. That is right for guidance (stale guidance spoken late is
worse than not spoken) and wrong for everything the user asked for. On the
2026-09-08 walk a summary was cut mid-sentence by a "very close" warning and
then simply never came back — the user reported it as the app not finishing one
thing before starting the next.

Safety must still interrupt: a person stepping into the path outranks a page of
text. What was missing is the other half — after the warning, the read-out the
user asked for RESUMES instead of being destroyed.

So an on-demand read-out is spoken as a sequence of chunks split at sentence
boundaries, and the position in that sequence survives an interruption. The
chunk that was cut is repeated from its start: the user heard half of it, and
half a sentence is not information.

Pure logic, no TTS: mirrored 1:1 in `lib/logic/speech_queue.dart`.
"""

import re

# ~12 s of speech at the configured rate. Small enough that resuming after an
# interruption repeats little, large enough that the pauses between chunks do
# not turn a paragraph into a list.
MAX_CHUNK_CHARS = 180

# A read-out that was interrupted this long ago is not worth resuming: the
# user has walked on and the answer is about a scene that has moved.
STALE_AFTER_SECONDS = 90.0

_SENTENCE_END = re.compile(r'(?<=[.!?;:])\s+')


def split_for_speech(text, max_chars=MAX_CHUNK_CHARS):
    """Split [text] into speakable chunks at the most natural boundary that
    fits: sentence, then clause, then word. Never mid-word, and never an empty
    chunk — a chunk boundary is a place the read-out can be resumed from."""
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    for sentence in _SENTENCE_END.split(text):
        sentence = sentence.strip()
        if sentence:
            chunks.extend(_split_long(sentence, max_chars))
    return chunks


def _split_long(sentence, max_chars):
    """One sentence, split further only if it would not fit. Commas first —
    they are where a reader would breathe — then words."""
    if len(sentence) <= max_chars:
        return [sentence]
    parts = []
    current = ""
    for piece in _clause_pieces(sentence, max_chars):
        if not current:
            current = piece
        elif len(current) + 1 + len(piece) <= max_chars:
            current = current + " " + piece
        else:
            parts.append(current)
            current = piece
    if current:
        parts.append(current)
    # A single word longer than the limit is left whole: breaking it would be
    # unspeakable, and TTS engines handle long tokens fine.
    return parts


def _clause_pieces(sentence, max_chars):
    pieces = [p.strip() for p in re.split(r'(?<=,)\s+', sentence) if p.strip()]
    out = []
    for piece in pieces:
        if len(piece) <= max_chars:
            out.append(piece)
        else:
            out.extend(piece.split())
    return out


class SpeechQueue:
    """The remaining chunks of the read-out that currently owns the channel.

    Deliberately dumb about time: the caller supplies `now`, so the same code
    runs under test without sleeping.
    """

    def __init__(self, max_chars=MAX_CHUNK_CHARS,
                 stale_after=STALE_AFTER_SECONDS):
        self._max_chars = max_chars
        self._stale_after = stale_after
        self._chunks = []
        self._index = 0
        self._started = 0.0

    def load(self, message, now=0.0):
        """Begin a new read-out, discarding anything left of the last one."""
        self._chunks = split_for_speech(message, self._max_chars)
        self._index = 0
        self._started = now
        return len(self._chunks)

    def clear(self):
        self._chunks = []
        self._index = 0

    @property
    def remaining(self):
        return max(0, len(self._chunks) - self._index)

    @property
    def has_more(self):
        return self.remaining > 0

    def take(self):
        """The next chunk to speak, or None when the read-out is finished."""
        if not self.has_more:
            return None
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk

    def rewind(self):
        """The chunk just taken was cut off before it finished. Say it again
        when the channel comes back — half a sentence is not information."""
        if self._index > 0:
            self._index -= 1

    def is_stale(self, now):
        """Has this read-out been waiting so long that resuming it would answer
        a question about a scene the user has already left?"""
        return self._started and (now - self._started) > self._stale_after

    def resume_or_drop(self, now):
        """Called when the channel comes free after an interruption. Returns
        the chunk to speak, or None — and a stale read-out is DROPPED rather
        than spoken late, the same rule that governs guidance."""
        if self.is_stale(now):
            self.clear()
            return None
        return self.take()
