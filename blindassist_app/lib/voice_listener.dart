// BlindAssist — offline voice commands (phase A4). Vosk with the SAME
// grammar-constrained small-English model used on the desktop — the model
// zip ships inside the APK, so recognition works with zero internet.
import 'dart:async';
import 'dart:convert';

import 'package:vosk_flutter/vosk_flutter.dart';

import 'logic/voice_commands.dart';

class VoiceListener {
  final void Function(VoiceCommand command, String heard) onCommand;

  /// Heard, but the local parser made nothing of it. Optional second tier:
  /// main.dart forwards these to the laptop's agent router. Local parsing is
  /// never skipped to get here, so trained phrases keep routing on-device.
  final void Function(String heard)? onUnmatched;

  VoiceListener({required this.onCommand, this.onUnmatched});

  SpeechService? _speech;
  StreamSubscription<String>? _sub;
  String? error;
  bool get active => _speech != null && error == null;
  String? lastHeard;

  Future<bool> start() async {
    try {
      final vosk = VoskFlutterPlugin.instance();
      final modelPath = await ModelLoader()
          .loadFromAssets('assets/models/vosk-model-small-en-us-0.15.zip');
      final model = await vosk.createModel(modelPath);
      final recognizer = await vosk.createRecognizer(
        model: model,
        sampleRate: 16000,
        grammar: [...grammarPhrases(), '[unk]'],
      );
      final speech = await vosk.initSpeechService(recognizer);
      _sub = speech.onResult().listen(_handleResult);
      await speech.start();
      _speech = speech;
      return true;
    } catch (e) {
      error = '$e';
      return false;
    }
  }

  void _handleResult(String resultJson) {
    final text = (jsonDecode(resultJson)['text'] as String? ?? '')
        .replaceAll('[unk]', '')
        .trim();
    if (text.isEmpty) return;
    final command = parseCommand(text);
    lastHeard = text;
    if (command != null) {
      onCommand(command, text);
    } else {
      onUnmatched?.call(text);
    }
  }

  Future<void> dispose() async {
    await _sub?.cancel();
    await _speech?.stop();
    _speech?.dispose();
    _speech = null;
  }
}
