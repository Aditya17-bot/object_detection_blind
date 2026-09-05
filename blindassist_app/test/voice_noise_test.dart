// The noise floor on the GRAMMAR path, and why it is not one threshold.
//
// Vosk is grammar-constrained: it cannot report "I did not understand", only
// its best match over the trained phrases, for ANY audio — a passing
// conversation, a door closing, the app's own TTS. The grammar therefore
// carries an explicit `[unk]` token, which is how the recognizer says "there
// was sound here I could not place".
//
// Those markers used to be DELETED and the remainder kept, so
// "[unk] [unk] clock mode" arrived indistinguishable from a user deliberately
// saying "clock mode" — the app toggled clock mode at a door closing.
//
// The first fix over-corrected. A flat ratio rejects any ONE-WORD command that
// picks up a single stray token, and "read", "walk", "stop" and "repeat" are
// all one word — so the app went deaf to exactly the commands the user needed
// most ("it's not hearing me properly when I say read", 2026-09-05).
//
// The threshold is therefore per command, by the cost of getting it wrong.
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

    test('empty and malformed results are rejected, not thrown on', () {
      expect(recognitionIsUsable(parseRecognizerResult(result(''))), isFalse);
      expect(recognitionIsUsable(parseRecognizerResult('not json')), isFalse);
    });
  });

  group('actions are heard leniently', () {
    // The user must be able to invoke a capability. A false reject looks like
    // a broken app to someone who cannot see the screen; a false accept just
    // speaks a sentence they can ignore.

    test('a one-word command survives a single stray token', () {
      // the exact failure: "read" was going unheard
      for (final word in ['read', 'walk', 'stop', 'repeat', 'describe']) {
        final r = parseRecognizerResult(result('[unk] $word'));
        expect(r.text, word);
        expect(recognitionIsUsable(r, action: word), isTrue,
            reason: '"$word" must survive one unplaceable neighbour');
      }
    });

    test('find survives filler around it', () {
      final r = parseRecognizerResult(result('[unk] find the bottle [unk]'));
      expect(recognitionIsUsable(r, action: 'find'), isTrue);
    });

    test('but noise-dominated audio is still rejected', () {
      final r = parseRecognizerResult(result('[unk] [unk] [unk] read'));
      expect(r.text, 'read', reason: 'it still LOOKS like a command...');
      expect(recognitionIsUsable(r, action: 'read'), isFalse,
          reason: '...but three quarters of it was unplaceable');
    });

    test('pure noise is rejected', () {
      final r = parseRecognizerResult(result('[unk] [unk] [unk]'));
      expect(r.text, isEmpty);
      expect(recognitionIsUsable(r), isFalse);
    });
  });

  group('settings toggles demand a clean recognition', () {
    // Spurious activation silently changes how the app behaves, with nothing
    // a blind user could notice until the behaviour surprises them.

    test('the field failure: half-noise must not toggle clock mode', () {
      final r = parseRecognizerResult(result('[unk] [unk] clock mode'));
      expect(r.text, 'clock mode');
      expect(recognitionIsUsable(r, action: 'clock'), isFalse);
    });

    test('one stray token is enough to reject a toggle', () {
      final r = parseRecognizerResult(result('[unk] sonar on'));
      expect(recognitionIsUsable(r, action: 'sonar'), isFalse);
      // ...while the same shape is fine for an action
      expect(recognitionIsUsable(r, action: 'find'), isTrue);
    });

    test('a clean toggle still works', () {
      for (final t in ['clock', 'zones', 'sonar', 'mute']) {
        final r = parseRecognizerResult(result('$t mode'));
        expect(recognitionIsUsable(r, action: t), isTrue,
            reason: 'deliberate "$t" must not be blocked');
      }
    });
  });
}
