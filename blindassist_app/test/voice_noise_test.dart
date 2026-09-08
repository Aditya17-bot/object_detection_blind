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
import 'package:blindassist/logic/voice_commands.dart';
import 'package:blindassist/voice_listener.dart';
import 'package:blindassist/logic/agent_actions.dart';

String result(String text) => '{"text": "$text"}';

void main() {
  _oneRequestFloor();
  _multiObjectFloor();
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

// From the 2026-09-07 field log. Every utterance here was produced by the
// recognizer from sound the user did not intend as a command, and every one
// arrived with ZERO [unk] tokens — words forced onto the grammar are not
// unplaceable, so the unknown-ratio floor cannot see them. One of them
// ("cupboard find dustbin") started a search for an object nobody named, which
// is the "why does it randomly find something" report.
void _multiObjectFloor() {
  group('two object names in one utterance is noise', () {
    test('field noise is rejected', () {
      for (final text in [
        'cupboard find toilet',
        'find suitcase toilets',
        'mobile photo person on anything on my left dining the',
      ]) {
        expect(namesMultipleObjects(text), isTrue, reason: text);
        // and the floor itself rejects it, with no unplaceable tokens at all
        expect(recognitionIsUsable(Recognition(text, 0)), isFalse,
            reason: text);
      }
    });

    test('real requests survive', () {
      for (final text in [
        'find the door',
        'find the cell phone',
        'how many chairs',
        'find the door on my left',
        'where is the cup',
        'take a photo of the chair',
        'what colour is this',
        'is there anything in front of me',
      ]) {
        expect(namesMultipleObjects(text), isFalse, reason: text);
        expect(recognitionIsUsable(Recognition(text, 0)), isTrue, reason: text);
      }
    });

    test('whole words only', () {
      // "how many chairs" contains "man" and "cupboard" contains "cup", so a
      // naive contains() rejects ordinary single-object requests as noise.
      expect(namedClasses('how many chairs'), {'chair'});
      expect(namedClasses('cupboard'), isNot(contains('cup')));
    });

    test('find takes the first object named', () {
      expect(parseCommand('find suitcase toilets')?.target, 'suitcase');
      expect(parseCommand('find bottle chair')?.target, 'bottle');
      // length still breaks ties at the same position
      expect(parseCommand('find the cell phone')?.target, 'cell phone');
    });
  });
}

// The second half of the 2026-09-07 log, after the multi-object floor landed.
// Every utterance below was still accepted and RAN something the user had not
// asked for. All of it is grammar-forced noise with zero unplaceable tokens:
// the recognizer is certain about every word.
void _oneRequestFloor() {
  group('one request names one thing and asks for one capability', () {
    test('field noise is rejected', () {
      for (final text in [
        'describe light left',
        'the clock summary',
        'the clock mans light left',
        'the many where of me is there read walk',
        'cupboard find toilet',
        'do laptops ahead laptop on my left bottle on here right',
        'scene mobile is toilet window',
        'clock many toilet door toilet summarize',
      ]) {
        expect(looksLikeOneRequest(text), isFalse, reason: text);
        expect(recognitionIsUsable(Recognition(text, 0)), isFalse,
            reason: text);
      }
    });

    test('real requests survive', () {
      for (final text in [
        'find the door', 'how many chairs', 'what is on my left',
        'is there anything in front of me', 'take a photo', 'read text',
        'summarise this', 'what colour is this', 'is the light on',
        'clear path', 'walk mode', 'say again', 'sonar off',
        'what can you do', 'where is the cup', 'find the door on my left',
        'mute it', 'on summarize',
      ]) {
        expect(looksLikeOneRequest(text), isTrue, reason: text);
        expect(recognitionIsUsable(Recognition(text, 0)), isTrue, reason: text);
      }
    });

    test('the dictation trigger may carry a request', () {
      // "assistant find the door" is a trigger PLUS a request by design, so
      // the trigger must not count as a second capability.
      expect(looksLikeOneRequest('assistant find the door'), isTrue);
      expect(parseCommand('assistant find the door')?.target, 'door');
    });

    test('a direction is not a second capability', () {
      expect(namedCapabilities('find the door on my left'), {'find'});
    });
  });

  group('setting deliberateness', () {
    // A setting must have been ASKED for, not merely present in the noise.
    //
    // The grammar is closed, so ambient speech does not fail to match - it
    // matches the nearest trained phrase and is CERTAIN about it. Replaying
    // the 2026-09-07 walk audio through the shipped grammar, the room produced
    // 'is mute womans': no unknown tokens, one capability, three words, and it
    // muted the app. Muting is the worst case because a blind user has no way
    // to see that it happened; the previous field walk lost every command
    // after one for exactly that reason.
    const fieldNoise = [
      'is mute womans', // observed, 2026-09-07 walk audio
      'the sonar bottle',
      'clock the many',
      'wardrobe zone plant',
    ];
    const real = [
      'mute', 'mute it', 'please mute', 'voice on', 'sound on', 'speak',
      'sonar on', 'sonar off', 'turn off sonar', 'turn the sonar on',
      'clock mode', 'zone mode',
    ];

    test('field noise cannot flip a setting', () {
      for (final text in fieldNoise) {
        final parsed = parseCommand(text);
        if (parsed == null || !kSettingActions.contains(parsed.action)) {
          continue; // already rejected earlier in the chain
        }
        expect(settingIsDeliberate(parsed.action, text), isFalse,
            reason: '$text would flip ${parsed.action}');
      }
    });

    test('real phrasings still work', () {
      for (final text in real) {
        final parsed = parseCommand(text);
        expect(parsed, isNotNull, reason: text);
        expect(settingIsDeliberate(parsed!.action, text), isTrue, reason: text);
      }
    });

    test('every grammar phrase for a setting survives', () {
      for (final phrase in agentGrammarPhrases()) {
        final parsed = parseCommand(phrase);
        if (parsed != null && kSettingActions.contains(parsed.action)) {
          expect(settingIsDeliberate(parsed.action, phrase), isTrue,
              reason: phrase);
        }
      }
    });

    test('non settings are untouched', () {
      // everything else answers out loud, so the user hears a false accept
      // immediately and can correct it; a false REJECT is the costly error
      for (final text in [
        'read', 'read the text', 'describe', 'find the bottle',
        'how many chairs', 'is there anything in front of me',
      ]) {
        final parsed = parseCommand(text);
        expect(parsed, isNotNull, reason: text);
        expect(settingIsDeliberate(parsed!.action, text), isTrue, reason: text);
      }
    });

    test('the recognizer gate rejects a setting hidden in noise', () {
      const heard = Recognition('is mute womans', 0);
      expect(recognitionIsUsable(heard, action: 'mute'), isFalse);
      expect(recognitionIsUsable(const Recognition('mute it', 0),
          action: 'mute'), isTrue);
    });
  });
}
