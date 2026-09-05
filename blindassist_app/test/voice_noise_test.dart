// The noise floor on the GRAMMAR path.
//
// Vosk is grammar-constrained: it cannot report "I did not understand", only
// its best match over the trained phrases, for ANY audio — a passing
// conversation, a door closing, the app's own TTS. The grammar therefore
// carries an explicit `[unk]` token, which is how the recognizer says "there
// was sound here I could not place".
//
// Those markers used to be DELETED and the remainder kept, so
// "[unk] [unk] clock mode" arrived indistinguishable from a user deliberately
// saying "clock mode" — and the app toggled clock mode at a door closing.
// That is the "randomly says clock mode" from the 2026-09-05 field walk.
import 'package:flutter_test/flutter_test.dart';
import 'package:blindassist/voice_listener.dart';

String result(String text) => '{"text": "$text"}';

void main() {
  group('recognizer result parsing', () {
    test('clean speech has no unplaceable tokens', () {
      final r = parseRecognizerResult(result('find the bottle'));
      expect(r.text, 'find the bottle');
      expect(r.unknownCount, 0);
      expect(r.unknownRatio, 0.0);
      expect(recognitionIsUsable(r), isTrue);
    });

    test('[unk] markers are stripped from the text but counted', () {
      final r = parseRecognizerResult(result('[unk] find the bottle'));
      expect(r.text, 'find the bottle', reason: 'markers must not be spoken');
      expect(r.unknownCount, 1);
    });

    test('one filler word does not reject a real request', () {
      final r = parseRecognizerResult(result('find the bottle [unk]'));
      expect(recognitionIsUsable(r), isTrue,
          reason: 'real speech carries filler the grammar cannot place');
    });

    test('mostly-unplaceable audio is rejected even when it parses', () {
      // the exact shape that toggled clock mode on the field walk
      final r = parseRecognizerResult(result('[unk] [unk] clock mode'));
      expect(r.text, 'clock mode',
          reason: 'it still LOOKS like a valid command...');
      expect(recognitionIsUsable(r), isFalse,
          reason: '...but the recognizer placed only half of what it heard');
    });

    test('pure noise is rejected', () {
      final r = parseRecognizerResult(result('[unk] [unk] [unk]'));
      expect(r.text, isEmpty);
      expect(recognitionIsUsable(r), isFalse);
    });

    test('empty and malformed results are rejected, not thrown on', () {
      expect(recognitionIsUsable(parseRecognizerResult(result(''))), isFalse);
      expect(recognitionIsUsable(parseRecognizerResult('not json')), isFalse);
    });

    test('the threshold is a ratio, so long utterances tolerate more noise', () {
      final long = parseRecognizerResult(
          result('find the bottle on the table [unk] [unk]'));
      final short = parseRecognizerResult(result('walk [unk] [unk]'));
      expect(recognitionIsUsable(long), isTrue);
      expect(recognitionIsUsable(short), isFalse);
    });
  });
}
