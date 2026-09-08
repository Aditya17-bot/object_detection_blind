// BlindAssist — speech output (phase A3). The base rule is the same as
// speech.py and the web UI: stale guidance is never spoken — a new
// announcement REPLACES whatever is currently being said or waiting.
//
// Two refinements on top of that rule, both bought by field walks:
//
//  * Speech the user explicitly ASKED for (OCR read-out, summary, scene
//    description, counts) is not cut off by routine walk chatter. A "very
//    close" escalation still cuts through — safety always outranks
//    convenience.
//  * ...and when safety does cut through, the read-out RESUMES afterwards
//    instead of being destroyed. Before this, a summary interrupted by one
//    warning was simply lost, which the user reported (2026-09-08) as the app
//    not finishing one thing before starting the next. Chunking and position
//    live in `logic/speech_queue.dart`.
import 'package:flutter_tts/flutter_tts.dart';

import 'logic/speech_policy.dart';
import 'logic/speech_queue.dart';
import 'settings.dart';

class Speaker {
  final FlutterTts _tts = FlutterTts();
  bool muted = false;

  /// The remaining chunks of the on-demand read-out that owns the channel.
  /// Survives a safety interruption; that is the whole point of it.
  final SpeechQueue _queue = SpeechQueue();

  // On-demand utterance in flight. The completion handler clears it;
  // _onDemandUntil is a belt-and-braces expiry in case a platform TTS never
  // fires its handler (routine guidance must not stay blocked forever).
  bool _onDemandActive = false;
  DateTime _onDemandUntil = DateTime.fromMillisecondsSinceEpoch(0);

  /// Unspoken chunks count as "playing": routine guidance must not slip into
  /// the gap between two sentences of an answer the user asked for.
  bool get _onDemandPlaying =>
      _queue.hasMore ||
      (_onDemandActive && DateTime.now().isBefore(_onDemandUntil));

  // The phone's own speaker reaches its own microphone, and the recognizer is
  // grammar-constrained, so it force-matches our TTS back into trained
  // phrases: "Bottle on your right" can come back as a directional query, and
  // the app answers its own voice. The dedupe in main.dart caught the exact
  // repeats; it cannot catch a phrase that force-matches into a DIFFERENT
  // command. So the recognizer is ignored while we are talking, plus a short
  // tail for the room's reverberation and the plugin's own latency.
  static const Duration _echoTail = Duration(milliseconds: 900);
  DateTime _quietUntil = DateTime.fromMillisecondsSinceEpoch(0);
  bool _speaking = false;

  /// Bumped for every utterance handed to the platform. A cancel callback that
  /// arrives with a stale value was caused by US starting the next utterance,
  /// not by the end of anything — see [_cancelled].
  int _seq = 0;

  /// The last thing we said, lowercased. Used to tell our own echo apart from
  /// the user talking over us — see [couldBeEcho].
  String _lastSpoken = '';

  /// True while our own voice could still be reaching the microphone.
  bool get isEchoing => _speaking || DateTime.now().isBefore(_quietUntil);

  /// Is [heard] plausibly our OWN voice coming back, rather than the user?
  ///
  /// A purely TIME-based gate makes the app deaf for the whole of every
  /// announcement plus a tail. In walk mode that is most of the time, and it
  /// is exactly when a user most wants to interrupt — which is why "read" and
  /// "find" so often did nothing on the 2026-09-05 walk.
  ///
  /// Content settles it. Our own speech is guidance ("Door at 11 o'clock,
  /// close"); it never contains a bare command word like "read". So inside the
  /// echo window we reject only text whose every word we just said, and let
  /// anything else through as genuinely new speech.
  bool couldBeEcho(String heard) =>
      isEchoing && isProbablyEcho(heard, _lastSpoken);

  /// Called when the platform reports the whole read-out finished. The ONLY
  /// reliable end-of-speech signal there is: everything else in this class
  /// estimates duration from character count, which is what let a long summary
  /// outlive its focus hold and get cut off by a walk warning. main.dart uses
  /// this to release the focus hold at the real end.
  ///
  /// Deliberately NOT fired for a cancellation caused by our own next
  /// utterance. It used to be, and the consequence was the exact bug the user
  /// reported: `_say` took the focus hold, called us, our internal `stop()`
  /// cancelled the utterance still in flight, the cancel callback released the
  /// hold that had just been taken — and the answer was then spoken with no
  /// protection at all, so the next walk warning cut into it.
  void Function()? onDone;

  double _nowSeconds() => DateTime.now().millisecondsSinceEpoch / 1000.0;

  /// Natural end of an utterance: speak the next chunk, or finish.
  void _completed() {
    _speaking = false;
    _quietUntil = DateTime.now().add(_echoTail);
    final next = _queue.resumeOrDrop(_nowSeconds());
    if (next != null) {
      _speakChunk(next, onDemand: true);
      return;
    }
    _onDemandActive = false;
    onDone?.call();
  }

  /// The platform cancelled an utterance. Almost always that is us, replacing
  /// it — in which case nothing has ended and nobody should be told. Only a
  /// cancellation with no replacement behind it (audio focus lost to a call,
  /// the engine reset) is a real end, and it is recognised by no new utterance
  /// having started shortly afterwards.
  void _cancelled() {
    final seq = _seq;
    Future.delayed(const Duration(milliseconds: 300), () {
      if (seq != _seq) return; // we started the next utterance: not an end
      _speaking = false;
      _quietUntil = DateTime.now().add(_echoTail);
      final next = _queue.resumeOrDrop(_nowSeconds());
      if (next != null) {
        _speakChunk(next, onDemand: true);
        return;
      }
      _onDemandActive = false;
      onDone?.call();
    });
  }

  /// Apply the configured accent. Separate from [init] so the features page
  /// can change it live and hear the result immediately.
  ///
  /// Falls back silently: an engine without the requested locale keeps the one
  /// it has, which is strictly better than throwing and leaving the app mute.
  Future<void> applyVoice([String? locale]) async {
    final want = locale ?? AppSettings.ttsLocale;
    try {
      final available = await _tts.isLanguageAvailable(want);
      if (available == true) await _tts.setLanguage(want);
    } catch (_) {
      // keep whatever the engine defaulted to
    }
  }

  Future<void> init() async {
    await _tts.setLanguage('en-US');
    await applyVoice();
    await _tts.setSpeechRate(0.55); // plugin scale ~0..1; ≈175 wpm feel
    await _tts.setVolume(1.0);
    await _tts.awaitSpeakCompletion(false); // say() must never block
    _tts.setCompletionHandler(_completed);
    _tts.setCancelHandler(_cancelled);
  }

  /// Speak [message], cutting off anything currently being spoken.
  ///
  /// [onDemand]: the user asked for this (describe, OCR, summary, count,
  /// recall) — it is spoken in chunks, protected from routine interruptions,
  /// and resumed if safety cuts in.
  /// [urgent]: safety escalation — interrupts everything, even on-demand, and
  /// the on-demand read-out picks up again once it has been said.
  Future<void> say(String message,
      {bool onDemand = false, bool urgent = false}) async {
    if (muted) return;
    if (_onDemandPlaying && !onDemand && !urgent) return; // drop, don't queue
    if (urgent) {
      // Interrupting mid-sentence: say that sentence again afterwards. The
      // user heard half of it, and half a sentence is not information.
      if (_speaking && _onDemandPlaying) _queue.rewind();
      await _speakChunk(message, onDemand: false);
      return;
    }
    if (onDemand) {
      _queue.load(message, now: _nowSeconds());
      final first = _queue.take();
      if (first == null) return; // nothing but whitespace
      await _speakChunk(first, onDemand: true);
      return;
    }
    _queue.clear(); // routine speech ends any read-out still in progress
    await _speakChunk(message, onDemand: false);
  }

  Future<void> _speakChunk(String chunk, {required bool onDemand}) async {
    _seq++;
    _lastSpoken = chunk.toLowerCase();
    await _tts.stop(); // latest wins — never finish stale guidance
    if (onDemand) _onDemandActive = true;
    _speaking = true;
    // Belt and braces: if the platform never fires a handler, the echo guard
    // must still lift, or the app would stop hearing anything at all.
    final secs = (chunk.length / 15).clamp(2, 30).toDouble();
    _quietUntil = DateTime.now()
        .add(Duration(milliseconds: (secs * 1000).round()) + _echoTail);
    if (_onDemandActive) {
      // Rough speaking-time estimate at ~15 chars/s, covering everything still
      // queued as well as this chunk. ONLY a failsafe for a platform that
      // never fires a handler — the completion handler is what normally
      // advances the read-out — so the ceiling is generous.
      final pending = chunk.length + _queue.remaining * kMaxChunkChars;
      final onDemandSecs = (pending / 15).clamp(3, 120).toDouble();
      _onDemandUntil = DateTime.now()
          .add(Duration(milliseconds: (onDemandSecs * 1000).round()));
    }
    await _tts.speak(chunk);
  }

  /// Voice "stop": halt whatever is being said right now, and abandon the rest
  /// of any read-out — "stop" means the task, not just the sentence.
  Future<void> stop() async {
    _queue.clear();
    _seq++;
    _speaking = false;
    _onDemandActive = false;
    _quietUntil = DateTime.now().add(_echoTail);
    await _tts.stop();
    onDone?.call();
  }

  Future<void> dispose() => _tts.stop();
}
