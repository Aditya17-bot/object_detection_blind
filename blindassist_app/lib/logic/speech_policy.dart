/// Who gets to speak, and when. Mirror of `speech_policy.py` — see that file
/// for the full reasoning; the short version:
///
/// The app has five independent things that want the ear (walk warnings,
/// find-mode updates, on-demand read-outs, dialogue replies, mode
/// confirmations) and until now the only arbitration was [Speaker]'s
/// preemption rule. That is a rule about *interruption*, not *order*, so an
/// unrequested read-out could land in the middle of a task the user had just
/// asked for:
///
///     user: "find the bottle"
///     app:  "Finding bottle"
///     app:  "Bottle on your right, close"
///     app:  "Nothing on your right"        <- nobody asked
///
/// The missing concept is FOCUS: while a task the user asked for is running it
/// owns the channel. Routine guidance is dropped (never queued — stale
/// guidance spoken late is worse than not spoken), informational read-outs
/// wait, the user's own steering commands still go through, and safety speech
/// is never gated.
library;

// Priorities: classes of message, not urgency scores. Each answers "on whose
// behalf is this being said".
const int kSafety = 3; // very close obstacle, connection lost — always speaks
const int kResponse = 2; // the answer to something the user asked for
const int kConfirm = 1; // acknowledgement of a state change
const int kRoutine = 0; // walk warnings, find updates — droppable by design

/// Commands that steer the app. Never blocked when the user actually said
/// them: being unable to interrupt is how an assistive device becomes
/// frightening.
const Set<String> kSteering = {
  'walk', 'find', 'stop', 'mute', 'sonar', 'clock', 'zones', 'repeat', 'ask',
};

/// Commands that produce a spoken read-out and nothing else — the "cluster"
/// the user reported: individually correct, collectively noise.
const Set<String> kInformational = {
  'describe', 'check', 'path', 'count', 'recall', 'read', 'photo',
};

/// Every hold expires: one that is never released would silence the app.
const double kMaxHoldSeconds = 90.0;

/// Timed focus for tasks that finish the moment they have spoken.
const double kDefaultFocusSeconds = 6.0;

/// Focus arbitration. One instance per app, driven by the caller's clock.
class SpeechPolicy {
  SpeechPolicy(
      {this.focusSeconds = kDefaultFocusSeconds,
      this.maxHoldSeconds = kMaxHoldSeconds});

  final double focusSeconds;
  final double maxHoldSeconds;

  String? focusTag;
  double focusUntil = 0;

  /// Give [tag] the speech channel. [seconds] null means "until released" —
  /// used by find, which runs until the target is located rather than until it
  /// has spoken once. Still capped by [maxHoldSeconds].
  void begin(String tag, double now, {double? seconds}) {
    focusTag = tag;
    final span = seconds ?? maxHoldSeconds;
    focusUntil = now + (span < maxHoldSeconds ? span : maxHoldSeconds);
  }

  /// Push [tag]'s hold out to at least now+[seconds], never shortening it.
  ///
  /// Covers the time a sentence takes to SAY. Releasing focus when a task
  /// changes state rather than when it has finished speaking is what let a
  /// walk warning cut the find announcement off mid-word: the engine
  /// auto-returns to walk the instant it announces the target, so the channel
  /// was free again before the user had heard the answer. No-op unless [tag]
  /// currently holds focus, so a finished task cannot extend its successor's.
  void extend(String tag, double now, double seconds) {
    if (focusTag != tag) return;
    final until = now + (seconds < maxHoldSeconds ? seconds : maxHoldSeconds);
    if (until > focusUntil) focusUntil = until;
  }

  /// Release the channel if [tag] holds it. Releasing a tag that does not hold
  /// focus is a no-op, so a late completion cannot cancel the task that
  /// replaced it.
  void end(String tag, double now) {
    if (focusTag == tag) {
      focusTag = null;
      focusUntil = 0;
    }
  }

  bool focused(double now) => focusTag != null && now < focusUntil;

  String? activeTag(double now) => focused(now) ? focusTag : null;

  /// May this capability RUN? Gating the command and not just its speech
  /// matters: `read` pauses the camera stream and `find` changes mode, so a
  /// spurious trigger costs more than a spurious sentence.
  ///
  /// [solicited] is false for anything the deterministic parser could not
  /// resolve and the dialogue layer guessed at. A guess never interrupts a
  /// task the user actually asked for.
  bool allowCommand(String action, double now, {bool solicited = true}) {
    if (!focused(now)) return true;
    if (action == focusTag || action == _tagAction(focusTag)) return true;
    if (kSteering.contains(action)) return solicited;
    return false;
  }

  /// May this MESSAGE be spoken?
  bool allowSpeech(int priority, String tag, double now,
      {bool solicited = true}) {
    if (priority >= kSafety) return true; // never gated, never delayed
    if (!focused(now)) return true;
    if (tag == focusTag) return true;
    if (priority >= kResponse && solicited) return true;
    return false;
  }
}

/// 'find:bottle' -> 'find'. Tags carry their argument so two finds for
/// different objects are different tasks, but the action still has to match.
String? _tagAction(String? tag) {
  if (tag == null) return null;
  final i = tag.indexOf(':');
  return i < 0 ? tag : tag.substring(0, i);
}

// --- input floor ------------------------------------------------------------
// A recognizer result made only of glue words is noise: the grammar cannot
// emit anything else, so "the is my on" is what a passing conversation sounds
// like after being force-matched, not a phrasing anyone chose.
const Set<String> _contentWords = {
  'find', 'look', 'locate', 'search', 'where', 'describe', 'scene',
  'summary', 'around', 'read', 'text', 'count', 'many', 'path', 'clear',
  'way', 'walk', 'stop', 'repeat', 'again', 'sonar', 'mute', 'unmute',
  'clock', 'zone', 'zones', 'assistant', 'question',
  'left', 'right', 'ahead', 'front', 'forward', 'anything', 'something',
};

/// Could this recognizer output be a request the user actually made?
///
/// The floor before the dialogue layer is consulted. Deliberately crude: it is
/// not trying to understand the utterance, only to reject what the grammar
/// produces from non-speech. Two necessary conditions — at least two words,
/// and at least one capability keyword or object name.
bool isPlausibleRequest(String? text, {Iterable<String> classWords = const []}) {
  if (text == null || text.isEmpty) return false;
  final words = text.toLowerCase().split(RegExp(r'\s+'))
    ..removeWhere((w) => w.isEmpty);
  if (words.length < 2) return false;
  final content = {..._contentWords, ...classWords.map((w) => w.toLowerCase())};
  return words.any(content.contains);
}

// --- echo discrimination ----------------------------------------------------
// The phone's speaker reaches the phone's own microphone, and the recognizer is
// grammar-constrained, so it force-matches our own TTS back into trained
// phrases: "Bottle on your right" came back as a directional query and the app
// answered its own voice.
//
// A purely TIME-based guard (ignore the microphone while speaking, plus a tail)
// is safe and far too blunt. In walk mode the app talks every few seconds, so
// the microphone was deaf for most of the session - precisely when a user most
// wants to interrupt. The user reported it as "it's not hearing me properly
// when I say read, find" (2026-09-05).
//
// Content settles it. Our own speech is guidance ("Door at 11 o'clock, close");
// it never contains a bare command word like "read". So within the echo window
// reject only text whose every word we just said, and treat anything else as a
// human talking over us.

/// Is [heard] plausibly our own voice, given we just said [lastSpoken]?
/// Callers apply this ONLY inside the echo window; outside it, nothing is echo.
bool isProbablyEcho(String heard, String lastSpoken) {
  final words = heard.toLowerCase().split(RegExp(r'\s+'))
    ..removeWhere((w) => w.isEmpty);
  if (words.isEmpty) return true; // nothing said = nothing to act on
  final spoken = lastSpoken.toLowerCase();
  return words.every(spoken.contains);
}
