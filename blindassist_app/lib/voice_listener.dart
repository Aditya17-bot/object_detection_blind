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

/// Fraction of a result that may be `[unk]` before it is treated as noise
/// rather than speech. Accepted while the ratio is at or BELOW this, so a
/// one-word command with a single unplaceable neighbour ("[unk] read") still
/// gets through — that leniency matters more than it looks, because "read",
/// "walk", "stop" and "repeat" are all single words, and rejecting them on one
/// stray token is what made the app feel deaf on the 2026-09-05 walk.
const double kMaxUnknownRatio = 0.5;

/// Commands whose spurious activation silently changes how the app BEHAVES,
/// with nothing a blind user could notice until the behaviour surprises them.
/// These demand a clean recognition — no unplaceable tokens at all.
///
/// Everything else is an action the user hears the result of immediately and
/// can simply repeat, so the cost of a false accept is low and the cost of a
/// false REJECT (an app that ignores you) is high. The floor is set per
/// command for exactly that reason.
const Set<String> kSettingCommands = {'clock', 'zones', 'sonar', 'mute'};

/// One recognizer result: the words it placed in the grammar, and how many
/// tokens it could not place at all.
class Recognition {
  final String text;
  final int unknownCount;
  const Recognition(this.text, this.unknownCount);

  int get wordCount =>
      text.isEmpty ? 0 : text.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).length;

  /// 0.0 = every token was a grammar word, 1.0 = nothing was placed.
  double get unknownRatio {
    final total = wordCount + unknownCount;
    return total == 0 ? 1.0 : unknownCount / total;
  }
}

/// Parse one Vosk result into placed words and unplaceable tokens.
///
/// Pure and public so the noise floor can be tested without a microphone.
Recognition parseRecognizerResult(String resultJson) {
  try {
    final raw = (jsonDecode(resultJson)['text'] as String? ?? '');
    final tokens = raw.split(RegExp(r'\s+'))..removeWhere((t) => t.isEmpty);
    final unknown = tokens.where((t) => t == '[unk]').length;
    final words = tokens.where((t) => t != '[unk]');
    return Recognition(words.join(' '), unknown);
  } catch (_) {
    return const Recognition('', 0);
  }
}

/// Should this recognizer result be acted on at all?
///
/// [action] is what the parser made of it, or null if it made nothing. The
/// threshold depends on it: see [kSettingCommands].
bool recognitionIsUsable(Recognition r, {String? action}) {
  if (r.text.isEmpty) return false;
  if (action != null && kSettingCommands.contains(action)) {
    return r.unknownCount == 0;
  }
  return r.unknownRatio <= kMaxUnknownRatio;
}

class VoiceListener {
  final void Function(VoiceCommand command, String heard) onCommand;

  /// Heard, but the local parser made nothing of it. Optional second tier:
  /// main.dart forwards these to the laptop's agent router. Local parsing is
  /// never skipped to get here, so trained phrases keep routing on-device.
  final void Function(String heard)? onUnmatched;

  /// True while the app's own voice could still be reaching the microphone.
  /// Results that arrive then are dropped: the recognizer is grammar-
  /// constrained, so it force-matches our TTS back into trained phrases and
  /// the app ends up answering itself. Injected rather than read from Speaker
  /// so this class stays testable without a TTS plugin.
  /// Given the recognized text, is this our own TTS coming back through the
  /// microphone? Content-aware, not merely time-based — see
  /// `Speaker.couldBeEcho`.
  final bool Function(String heard)? echoing;

  VoiceListener({required this.onCommand, this.onUnmatched, this.echoing});

  /// Every non-empty transcript the recognizer produced, newest last, capped.
  /// The 2026-08-02 field walk could not be diagnosed because nothing recorded
  /// what was actually heard — only that 26 requests had been sent. Kept in
  /// memory only; the features page shows it.
  final List<String> transcripts = [];
  static const int _transcriptCap = 40;

  /// Transcripts dropped by the echo guard, counted so a suspiciously high
  /// number is visible rather than silently helpful.
  int echoDropped = 0;

  /// Results rejected because the recognizer could not place most of the
  /// audio (see [kMaxUnknownRatio]). Counted, not silent: a high number
  /// means the room is noisy, not that voice control is broken.
  int noiseDropped = 0;

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

  /// One recognizer result, split into what it placed and what it could not.
  ///
  /// The grammar carries an explicit `[unk]` token, which is how Vosk says "I
  /// heard sound here that is not in your phrases". [_clean] used to delete
  /// those markers and keep the remainder, so a result like
  /// `"[unk] [unk] clock mode"` — mostly unplaceable noise with two words that
  /// happened to land on a trained phrase — arrived indistinguishable from a
  /// user deliberately saying "clock mode". That is the "randomly says clock
  /// mode" the field walk reported. The markers are EVIDENCE, and they are now
  /// kept and weighed.
  Recognition _clean(String resultJson) => parseRecognizerResult(resultJson);

  void _handleResult(String resultJson) {
    final heard = _clean(resultJson);
    final text = heard.text;
    if (text.isEmpty) return;
    if (echoing?.call(text) ?? false) {
      // our own TTS coming back through the mic — not a request
      echoDropped++;
      return;
    }
    // Parse FIRST, because the noise floor depends on what was asked for: a
    // settings toggle must be heard cleanly, an action need not be. This is
    // the floor the GRAMMAR path never had — unmatched speech already faced a
    // plausibility check and a rate limit before reaching the router, but a
    // MATCHED command went straight to execution, and with a grammar-
    // constrained recognizer a match is not evidence that anyone spoke.
    final command = parseCommand(text);
    if (!recognitionIsUsable(heard, action: command?.action)) {
      noiseDropped++;
      return;
    }
    lastHeard = text;
    transcripts.add(text);
    if (transcripts.length > _transcriptCap) transcripts.removeAt(0);
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
        // No grammar here, so there are no `[unk]` markers to weigh — the open
        // recognizer transcribes whatever it hears and the text is all of it.
        final text = _clean(json).text;
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
