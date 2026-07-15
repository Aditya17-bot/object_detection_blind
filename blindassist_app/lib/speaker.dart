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

  Future<void> init() async {
    await _tts.setLanguage('en-US');
    await _tts.setSpeechRate(0.55); // plugin scale ~0..1; ≈175 wpm feel
    await _tts.setVolume(1.0);
    await _tts.awaitSpeakCompletion(false); // say() must never block
    _tts.setCompletionHandler(() => _onDemandActive = false);
    _tts.setCancelHandler(() => _onDemandActive = false);
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
    await _tts.stop(); // latest wins — never finish stale guidance
    _onDemandActive = onDemand;
    if (onDemand) {
      // rough speaking-time estimate at ~15 chars/s, clamped 3-30 s
      final secs = (message.length / 15).clamp(3, 30).toDouble();
      _onDemandUntil =
          DateTime.now().add(Duration(milliseconds: (secs * 1000).round()));
    }
    await _tts.speak(message);
  }

  /// Voice "stop": halt whatever is being said right now.
  Future<void> stop() async {
    _onDemandActive = false;
    await _tts.stop();
  }

  Future<void> dispose() => _tts.stop();
}
