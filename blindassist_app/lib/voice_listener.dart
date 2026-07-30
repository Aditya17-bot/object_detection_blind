// BlindAssist — offline voice commands (phase A4). Vosk with the SAME
// grammar-constrained small-English model used on the desktop — the model
// zip ships inside the APK, so recognition works with zero internet.
//
// TWO RECOGNIZERS, ONE MODEL
// --------------------------
// The command recognizer is grammar-constrained: only the enumerated phrases
// can be transcribed at all, which is what makes a 40 MB model reliable enough
// to act on. The cost is that free speech is not mis-heard, it is never heard.
// Saying a trigger word ("assistant") therefore swaps in a SECOND recognizer
// built on the same already-loaded model with no grammar, captures one
// utterance, and swaps back. The laptop's Whisper path stays the accurate
// option; this one keeps free speech working with the laptop off, which is the
// same degradation rule the rest of the app follows.
//
// The swap is a stop/dispose/re-init cycle because vosk_flutter binds one
// SpeechService to one recognizer and owns the microphone. Every failure path
// here ends by restoring the command recognizer: losing dictation is an
// inconvenience, losing voice control for the rest of the session is not.
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

  Model? _model;
  Recognizer? _recognizer;
  SpeechService? _speech;
  StreamSubscription<String>? _sub;
  String? error;
  bool get active => _speech != null && error == null;
  String? lastHeard;

  bool _dictating = false;

  /// True while the open-dictation window is capturing. main.dart reads it to
  /// keep the UI honest about which recognizer owns the microphone.
  bool get dictating => _dictating;

  Future<bool> start() async {
    try {
      final vosk = VoskFlutterPlugin.instance();
      final modelPath = await ModelLoader()
          .loadFromAssets('assets/models/vosk-model-small-en-us-0.15.zip');
      _model = await vosk.createModel(modelPath);
      await _startCommandService();
      return true;
    } catch (e) {
      error = '$e';
      return false;
    }
  }

  /// Bring up the grammar-constrained recognizer and hand it the microphone.
  Future<void> _startCommandService() async {
    final vosk = VoskFlutterPlugin.instance();
    _recognizer = await vosk.createRecognizer(
      model: _model!,
      sampleRate: 16000,
      grammar: [...grammarPhrases(), '[unk]'],
    );
    _speech = await _startService(_recognizer!, _handleResult);
  }

  /// Common wiring: subscribe to results, start the microphone.
  Future<SpeechService> _startService(
      Recognizer recognizer, void Function(String) onResult) async {
    final service =
        await VoskFlutterPlugin.instance().initSpeechService(recognizer);
    _sub = service.onResult().listen(onResult);
    await service.start();
    return service;
  }

  /// Tear down whatever currently owns the microphone. Safe to call twice.
  Future<void> _stopService() async {
    await _sub?.cancel();
    _sub = null;
    try {
      await _speech?.stop();
      await _speech?.dispose();
    } catch (_) {
      // a service that is already gone must not block the swap back
    }
    _speech = null;
  }

  String _clean(String resultJson) {
    try {
      return (jsonDecode(resultJson)['text'] as String? ?? '')
          .replaceAll('[unk]', '')
          .trim();
    } catch (_) {
      return '';
    }
  }

  void _handleResult(String resultJson) {
    final text = _clean(resultJson);
    if (text.isEmpty) return;
    final command = parseCommand(text);
    lastHeard = text;
    if (command != null) {
      onCommand(command, text);
    } else {
      onUnmatched?.call(text);
    }
  }

  /// Capture ONE free-form utterance and return its transcript, or null.
  ///
  /// [leadIn] discards the beginning of the window because the caller has just
  /// spoken an acknowledgement and the phone's own speaker reaches its own
  /// microphone — without it the ack gets transcribed as the question (the
  /// same reason voice.py's _dictate has a lead-in).
  ///
  /// Never throws and always ends with the command recognizer live again.
  Future<String?> dictate({
    Duration leadIn = const Duration(milliseconds: 900),
    Duration window = const Duration(seconds: 6),
  }) async {
    if (_dictating || _model == null) return null;
    _dictating = true;
    final done = Completer<String?>();
    Recognizer? open;
    try {
      await _stopService();
      await Future.delayed(leadIn); // let the spoken ack finish and decay
      open = await VoskFlutterPlugin.instance()
          .createRecognizer(model: _model!, sampleRate: 16000); // no grammar
      _speech = await _startService(open, (json) {
        final text = _clean(json);
        // Vosk emits a result on every silence boundary, including empty ones
        // at the start of the window; the first real words end the capture.
        if (text.isNotEmpty && !done.isCompleted) done.complete(text);
      });
      // A user who says nothing must not hold the microphone hostage: the
      // window closes on its own and command recognition comes straight back.
      final heard = await done.future.timeout(window, onTimeout: () => null);
      if (heard != null) lastHeard = heard;
      return heard;
    } catch (e) {
      // ignore: avoid_print
      print('BlindAssist dictation failed: $e');
      return null;
    } finally {
      await _stopService();
      try {
        await open?.dispose();
      } catch (_) {}
      try {
        await _startCommandService();
      } catch (e) {
        // The one failure that actually matters — voice control is now dead
        // and the caller has to say so out loud.
        error = 'voice stopped after dictation ($e)';
      }
      _dictating = false;
    }
  }

  Future<void> dispose() async {
    await _stopService();
    try {
      await _recognizer?.dispose();
      _model?.dispose(); // frees the native model; the recognizer refs it
    } catch (_) {}
    _recognizer = null;
    _model = null;
  }
}
