// BlindAssist — speech output (phase A3). Same rule as speech.py and the
// web UI: stale guidance is never spoken — a new announcement REPLACES
// whatever is currently being said or waiting.
//
// One refinement on top of that rule: speech the user explicitly ASKED for
// (OCR read-out, scene description, counts) must not be cut off by routine
// walk chatter — a page of text was unreadable when any obstacle in view
// interrupted it 1.5 s in. Routine guidance is DROPPED while an on-demand
// utterance plays; a "very close" escalation still cuts through (safety
// always outranks convenience).
import 'package:flutter_tts/flutter_tts.dart';

import 'logic/speech_policy.dart';
import 'settings.dart';

class Speaker {
  final FlutterTts _tts = FlutterTts();
  bool muted = false;

  // On-demand utterance in flight. The completion/cancel handlers clear it;
  // _onDemandUntil is a belt-and-braces expiry in case a platform TTS never
  // fires its handler (routine guidance must not stay blocked forever).
  bool _onDemandActive = false;
  DateTime _onDemandUntil = DateTime.fromMillisecondsSinceEpoch(0);

  bool get _onDemandPlaying =>
      _onDemandActive && DateTime.now().isBefore(_onDemandUntil);

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

  void _finished() {
    _onDemandActive = false;
    _speaking = false;
    _quietUntil = DateTime.now().add(_echoTail);
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
    _tts.setCompletionHandler(_finished);
    _tts.setCancelHandler(_finished);
  }

  /// Speak [message], cutting off anything currently being spoken.
  ///
  /// [onDemand]: the user asked for this (describe, OCR, count, recall) —
  /// protect it from routine interruptions until it finishes.
  /// [urgent]: safety escalation — interrupts everything, even on-demand.
  Future<void> say(String message,
      {bool onDemand = false, bool urgent = false}) async {
    if (muted) return;
    if (_onDemandPlaying && !onDemand && !urgent) return; // drop, don't queue
    _lastSpoken = message.toLowerCase();
    await _tts.stop(); // latest wins — never finish stale guidance
    _onDemandActive = onDemand;
    _speaking = true;
    // Belt and braces: if the platform never fires a handler, the echo guard
    // must still lift, or the app would stop hearing anything at all.
    final secs = (message.length / 15).clamp(2, 30).toDouble();
    _quietUntil = DateTime.now()
        .add(Duration(milliseconds: (secs * 1000).round()) + _echoTail);
    if (onDemand) {
      // rough speaking-time estimate at ~15 chars/s, clamped 3-30 s
      final onDemandSecs = (message.length / 15).clamp(3, 30).toDouble();
      _onDemandUntil = DateTime.now()
          .add(Duration(milliseconds: (onDemandSecs * 1000).round()));
    }
    await _tts.speak(message);
  }

  /// Voice "stop": halt whatever is being said right now.
  Future<void> stop() async {
    _finished();
    await _tts.stop();
  }

  Future<void> dispose() => _tts.stop();
}
