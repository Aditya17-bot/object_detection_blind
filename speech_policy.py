"""BlindAssist — who gets to speak, and when.

Why this exists
---------------
The app has five independent things that want the ear: walk-mode obstacle
warnings, find-mode target updates, on-demand read-outs (describe / check /
path / count / recall / OCR), dialogue-layer replies, and mode confirmations.
Until now the only arbitration was `Speaker`'s preemption rule — an on-demand
read-out cannot be cut by routine chatter, and "very close" cuts through
anything. That is a rule about *interruption*. It says nothing about *order*,
so an unrequested read-out could land in the middle of a task the user had
just asked for:

    user: "find the bottle"
    app:  "Finding bottle"
    app:  "Bottle on your right, close"
    app:  "Nothing on your right"        <- nobody asked

The missing concept is FOCUS. When the user asks for something, that task owns
the speech channel until it finishes. While it holds focus:

  * routine guidance is DROPPED (never queued — stale guidance spoken late is
    worse than guidance not spoken at all, the same rule Speaker already
    follows);
  * informational read-outs wait, whoever triggered them;
  * the user's own steering commands (mode, stop, mute, sonar, repeat) still go
    through, because a user must always be able to change their mind;
  * safety speech always goes through, because the point of the app is not
    hitting things.

The second half of the problem is INPUT, not output. The recognizer is
grammar-constrained, so it cannot return "I did not understand" — it returns
its best match over the trained phrases for *any* audio, including a passing
conversation or the app's own TTS. Anything the deterministic parser cannot
make sense of is therefore far more likely to be noise than a paraphrase, and
routing it to a language model whose measured out-of-scope over-trigger rate is
55% turns noise into spoken actions. `is_plausible_request()` is the floor that
has to be cleared before the dialogue layer is consulted at all.

Pure logic: no audio, no TTS, no clock of its own. Mirrored 1:1 in
`blindassist_app/lib/logic/speech_policy.dart`.
"""

# --- priorities -------------------------------------------------------------
# Higher speaks over lower. These are *classes of message*, not urgency scores:
# the question each one answers is "on whose behalf is this being said".
SAFETY = 3      # very close obstacle, connection lost/restored — always speaks
RESPONSE = 2    # the answer to something the user explicitly asked for
CONFIRM = 1     # acknowledgement of a state change ("Finding bottle")
ROUTINE = 0     # walk warnings, find position updates — droppable by design

# Commands that steer the app. The user must always be able to change mode,
# stop a long read-out, or mute, even mid-task — being unable to interrupt is
# how an assistive device becomes frightening. Never blocked when the user
# actually said them.
STEERING = frozenset({"walk", "find", "stop", "mute", "sonar", "clock",
                      "zones", "repeat", "ask"})

# Commands that produce a spoken read-out and nothing else. These are the
# "cluster" the user reported: individually correct, collectively noise. They
# wait while another task holds focus.
INFORMATIONAL = frozenset({"colour", "light", "describe", "check", "path",
                           "count", "recall", "read", "photo"})

# A hold that is never released would silence the app forever, so every hold
# expires. Long enough that a real search is not cut short, short enough that a
# missed release is a nuisance rather than a failure.
MAX_HOLD_SECONDS = 90.0

# A timed focus, for tasks that finish the moment they have spoken.
DEFAULT_FOCUS_SECONDS = 6.0


class SpeechPolicy:
    """Focus arbitration. One instance per app, driven by an injected clock.

    `begin`/`end` bracket a task; `allow_command` and `allow_speech` are asked
    before anything runs or is spoken. Nothing here touches audio, so the whole
    policy is unit-testable with plain numbers.
    """

    def __init__(self, focus_seconds=DEFAULT_FOCUS_SECONDS,
                 max_hold_seconds=MAX_HOLD_SECONDS):
        self.focus_seconds = focus_seconds
        self.max_hold_seconds = max_hold_seconds
        self.focus_tag = None
        self.focus_until = 0.0

    # -- focus ---------------------------------------------------------------
    def begin(self, tag, now, seconds=None):
        """Give `tag` the speech channel.

        `seconds=None` means "until explicitly released" — used for find, which
        runs until the target is located rather than until it has spoken once.
        It is still capped: see MAX_HOLD_SECONDS.
        """
        self.focus_tag = tag
        span = self.max_hold_seconds if seconds is None else seconds
        self.focus_until = now + min(span, self.max_hold_seconds)

    def extend(self, tag, now, seconds):
        """Push `tag`'s hold out to at least now+seconds, never shortening it.

        Used to cover the time a sentence takes to SAY. Releasing focus when a
        task changes state rather than when it has finished speaking is what
        let a walk warning cut the find announcement off mid-word on the
        2026-08-02 walk: the engine auto-returns to walk mode the instant it
        announces the target, so the channel was free again before the user had
        heard the answer. No-op unless `tag` currently holds focus, so a
        finished task cannot extend its successor's hold.
        """
        if self.focus_tag != tag:
            return
        self.focus_until = max(self.focus_until,
                               now + min(seconds, self.max_hold_seconds))

    def end(self, tag, now):
        """Release the channel if `tag` holds it. Releasing a tag that does not
        hold focus is a no-op, so a late completion cannot cancel the task that
        replaced it."""
        if self.focus_tag == tag:
            self.focus_tag = None
            self.focus_until = 0.0

    def focused(self, now):
        return self.focus_tag is not None and now < self.focus_until

    def active_tag(self, now):
        return self.focus_tag if self.focused(now) else None

    # -- the two decisions ---------------------------------------------------
    def allow_command(self, action, now, solicited=True):
        """May this capability RUN? Gating the command and not just its speech
        matters: `read` pauses the camera stream and `find` changes mode, so a
        spurious trigger costs more than a spurious sentence.

        `solicited` is False for anything the deterministic parser could not
        resolve and the dialogue layer guessed at. A guess never interrupts a
        task the user actually asked for.

        A command the user DID say is never blocked. Focus exists to stop
        routine guidance and the dialogue layer's guesses from treading on a
        task in progress -- it was never meant to stop the user, and when it
        did the app simply ignored them. Field log, 2026-09-05:

            policy: dropped "describe" (focus=photo, solicited=True)
            policy: dropped "check"    (focus=describe, solicited=True)

        Those were heard correctly, parsed correctly and thrown away. To a user
        who cannot see the screen that is indistinguishable from not being
        heard at all.
        """
        if not self.focused(now):
            return True
        if action == self.focus_tag or action == _tag_action(self.focus_tag):
            return True
        return solicited

    def allow_speech(self, priority, tag, now, solicited=True):
        """May this MESSAGE be spoken?

        Anything above routine chatter that the user actually asked for goes
        through: if allow_command let the capability run, refusing to speak its
        result would leave the user with silence and no way to tell why. Only
        ROUTINE guidance, and anything the dialogue layer guessed at, is gated.
        """
        if priority >= SAFETY:
            return True                      # never gated, never delayed
        if not self.focused(now):
            return True
        if tag == self.focus_tag:
            return True
        if priority >= CONFIRM and solicited:
            return True                      # a deliberate request takes over
        return False


def _tag_action(tag):
    """'find:bottle' -> 'find'. Tags carry their argument so two finds for
    different objects are different tasks, but the action still has to match."""
    if tag is None:
        return None
    return tag.split(":", 1)[0]


# --- input floor ------------------------------------------------------------
# Words that carry a capability or an object. A recognizer result made only of
# glue words is noise: the grammar cannot emit anything else, so "the is my on"
# is what a passing conversation sounds like after being force-matched, not a
# phrasing anyone chose.
_CONTENT_WORDS = frozenset({
    # capability keywords
    "find", "look", "locate", "search", "where", "describe", "scene",
    "summary", "around", "read", "text", "count", "many", "path", "clear",
    "way", "walk", "stop", "repeat", "again", "sonar", "mute", "unmute",
    "clock", "zone", "zones", "assistant", "question",
    # directional query
    "left", "right", "ahead", "front", "forward", "anything", "something",
})


def is_plausible_request(text, class_words=()):
    """Could this recognizer output be a request the user actually made?

    The floor before the dialogue layer is consulted. Deliberately crude and
    deliberately cheap — it is not trying to understand the utterance, only to
    reject the output the grammar produces from non-speech.

    Two conditions, both necessary:
      * at least two words (a single force-matched token is never a request);
      * at least one CONTENT word — a capability keyword or an object name.

    `class_words` is the object vocabulary, injected so this module does not
    import position.py and the caller can pass the synonyms it accepts.
    """
    if not text:
        return False
    words = text.lower().split()
    if len(words) < 2:
        return False
    content = _CONTENT_WORDS | {w.lower() for w in class_words}
    return any(w in content for w in words)


# --- echo discrimination ----------------------------------------------------
# Mirror of speech_policy.dart. The phone's speaker reaches its own microphone
# and the recognizer is grammar-constrained, so our own TTS force-matches back
# into trained phrases and the app answers its own voice.
#
# A purely TIME-based guard (ignore the microphone while speaking, plus a tail)
# is safe and far too blunt: in walk mode the app talks every few seconds, so
# the microphone is deaf for most of the session - exactly when a user most
# wants to interrupt. Content settles it. Our own speech is guidance ("Door at
# 11 o'clock, close") and never contains a bare command word like "read", so
# inside the echo window we reject only text whose every word we just said.


def is_probably_echo(heard, last_spoken):
    """Is `heard` plausibly our own voice, given we just said `last_spoken`?

    Callers apply this ONLY inside the echo window; outside it nothing is echo.
    """
    words = [w for w in (heard or "").lower().split() if w]
    if not words:
        return True          # nothing said = nothing to act on
    spoken = (last_spoken or "").lower()
    return all(w in spoken for w in words)
