// BlindAssist — speech output (phase A3). Same rule as speech.py and the
// web UI: stale guidance is never spoken — a new announcement REPLACES
// whatever is currently being said or waiting.
import 'package:flutter_tts/flutter_tts.dart';

class Speaker {
  final FlutterTts _tts = FlutterTts();
  bool muted = false;

  Future<void> init() async {
    await _tts.setLanguage('en-US');
    await _tts.setSpeechRate(0.55); // plugin scale ~0..1; ≈175 wpm feel
    await _tts.setVolume(1.0);
    await _tts.awaitSpeakCompletion(false); // say() must never block
  }

  /// Speak [message], cutting off anything currently being spoken.
  Future<void> say(String message) async {
    if (muted) return;
    await _tts.stop(); // latest wins — never finish stale guidance
    await _tts.speak(message);
  }

  Future<void> dispose() => _tts.stop();
}
