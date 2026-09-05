// Mirror of test_speech_policy.py. Every case here is a thing that actually
// happened on the 2026-08-02 field walk or a rule stated in the module doc.
import 'package:flutter_test/flutter_test.dart';

import 'package:blindassist/logic/speech_policy.dart';

void main() {
  group('focus', () {
    late SpeechPolicy p;
    setUp(() => p = SpeechPolicy(focusSeconds: 6.0));

    test('nothing is gated when no task holds focus', () {
      for (final a in {...kSteering, ...kInformational}) {
        expect(p.allowCommand(a, 0), isTrue, reason: a);
      }
      for (final pri in [kRoutine, kConfirm, kResponse, kSafety]) {
        expect(p.allowSpeech(pri, 'anything', 0), isTrue);
      }
    });

    test('the reported bug: an unrequested read-out during a find', () {
      // user: "find the bottle" -> app: "Nothing on your right"
      //
      // UNREQUESTED is the whole point: this is the dialogue layer guessing at
      // audio nobody addressed to the app. The same command asked for out loud
      // must still run -- see the test below.
      p.begin('find:bottle', 0);
      expect(p.allowCommand('check', 1, solicited: false), isFalse);
      expect(p.allowSpeech(kResponse, 'check', 1, solicited: false), isFalse);
    });

    test('a command the user actually said is never dropped', () {
      // The 2026-09-05 field bug. Focus exists to stop routine guidance and
      // the dialogue layer's guesses from treading on a task in progress. It
      // was never meant to stop the user, and when it did the app silently
      // ignored them:
      //
      //   policy: dropped "describe" (focus=photo, solicited=true)
      //   policy: dropped "check"    (focus=describe, solicited=true)
      //
      // To someone who cannot see the screen that is indistinguishable from
      // not being heard at all.
      for (final holder in ['photo', 'describe', 'read', 'find:bottle']) {
        final q = SpeechPolicy();
        q.begin(holder, 0);
        for (final asked in [
          'describe', 'check', 'count', 'recall', 'read',
          'photo', 'path', 'walk', 'stop', 'find'
        ]) {
          expect(q.allowCommand(asked, 1), isTrue,
              reason: '"$asked" must run while "$holder" holds focus');
        }
      }
    });

    test('and its answer may be spoken', () {
      // Letting the capability run but refusing to speak its result would
      // leave the user with silence and no way to tell why.
      final q = SpeechPolicy();
      q.begin('photo', 0);
      expect(q.allowSpeech(kResponse, 'describe', 1), isTrue);
      expect(q.allowSpeech(kConfirm, 'walk', 1), isTrue);
      // ...but routine chatter is still gated, which is what focus is FOR
      expect(q.allowSpeech(kRoutine, 'walk', 1), isFalse);
    });

    test('routine walk chatter waits for the task the user asked for', () {
      p.begin('describe', 0, seconds: 6.0);
      expect(p.allowSpeech(kRoutine, 'walk', 1), isFalse);
    });

    test('safety is never gated', () {
      p.begin('read', 0);
      expect(p.allowSpeech(kSafety, 'walk', 1), isTrue);
      expect(p.allowSpeech(kSafety, 'link', 1, solicited: false), isTrue);
    });

    test('the focused task may keep talking', () {
      p.begin('find:bottle', 0);
      expect(p.allowSpeech(kResponse, 'find:bottle', 1), isTrue);
      expect(p.allowCommand('find', 1), isTrue);
    });

    test('a user may always steer out of a task', () {
      p.begin('find:bottle', 0);
      for (final a in ['walk', 'stop', 'mute', 'sonar', 'repeat', 'ask']) {
        expect(p.allowCommand(a, 1, solicited: true), isTrue, reason: a);
      }
    });

    test('but a GUESSED steering command does not interrupt', () {
      p.begin('find:bottle', 0);
      for (final a in ['walk', 'stop', 'mute']) {
        expect(p.allowCommand(a, 1, solicited: false), isFalse, reason: a);
      }
    });

    test('a deliberate request takes the channel over', () {
      p.begin('find:bottle', 0);
      expect(p.allowSpeech(kResponse, 'describe', 1, solicited: true), isTrue);
    });

    test('focus expires so a missed release is not permanent silence', () {
      p.begin('describe', 0, seconds: 6.0);
      expect(p.allowSpeech(kRoutine, 'walk', 5.9), isFalse);
      expect(p.allowSpeech(kRoutine, 'walk', 6.1), isTrue);
    });

    test('an open-ended hold is still capped', () {
      final q = SpeechPolicy(maxHoldSeconds: 90.0);
      q.begin('find:bottle', 0); // seconds null -> open ended
      expect(q.focused(89), isTrue);
      expect(q.focused(91), isFalse);
    });

    test('an explicit span longer than the cap is clamped', () {
      final q = SpeechPolicy(maxHoldSeconds: 90.0);
      q.begin('read', 0, seconds: 1000);
      expect(q.focused(91), isFalse);
    });

    test('extend covers the time a sentence takes to say', () {
      // the find bug: the engine auto-returns to walk the instant it
      // announces the target, so the channel went free before the user had
      // heard the answer and the next warning cut it off mid-word
      p.begin('find:bottle', 0, seconds: 0.1);
      p.extend('find:bottle', 0, 3.0);
      expect(p.allowSpeech(kRoutine, 'walk', 2), isFalse);
      expect(p.allowSpeech(kRoutine, 'walk', 3.5), isTrue);
    });

    test('extend never shortens an existing hold', () {
      p.begin('find:bottle', 0); // open ended, 90 s
      p.extend('find:bottle', 0, 3.0);
      expect(p.focused(50), isTrue);
    });

    test('a finished task cannot extend its successor hold', () {
      p.begin('describe', 0, seconds: 6.0);
      p.begin('find:bottle', 1, seconds: 2.0);
      p.extend('describe', 1, 60.0); // late, wrong tag: no-op
      expect(p.focused(4), isFalse);
    });

    test('end releases the channel', () {
      p.begin('find:bottle', 0);
      p.end('find:bottle', 1);
      expect(p.allowCommand('check', 1), isTrue);
      expect(p.activeTag(1), isNull);
    });

    test('a late release cannot cancel the task that replaced it', () {
      p.begin('describe', 0, seconds: 6.0);
      p.begin('find:bottle', 1);
      p.end('describe', 2);
      expect(p.activeTag(2), 'find:bottle');
    });

    test('two finds for different objects are different tasks', () {
      p.begin('find:bottle', 0);
      p.end('find:cup', 1);
      expect(p.activeTag(1), 'find:bottle');
    });

    test('the action matches its tag even with an argument', () {
      p.begin('find:bottle', 0);
      expect(p.allowCommand('find', 1, solicited: false), isTrue);
    });

    test('activeTag is null once focus has expired', () {
      p.begin('describe', 0, seconds: 2.0);
      expect(p.activeTag(1), 'describe');
      expect(p.activeTag(3), isNull);
    });
  });

  group('isPlausibleRequest', () {
    const classes = ['bottle', 'door', 'chair', 'dustbin'];
    bool ok(String? t) => isPlausibleRequest(t, classWords: classes);

    test('real paraphrases pass', () {
      for (final t in [
        'show me the door',
        'is the bottle near me',
        'how far is the chair',
        'anything on my left',
      ]) {
        expect(ok(t), isTrue, reason: t);
      }
    });

    test('glue word soup is rejected', () {
      for (final t in ['the is my on', 'a to the', 'on my the it']) {
        expect(ok(t), isFalse, reason: t);
      }
    });

    test('a single token is never a request', () {
      expect(ok('bottle'), isFalse);
      expect(ok('find'), isFalse);
    });

    test('empty and null are rejected', () {
      expect(ok(''), isFalse);
      expect(ok(null), isFalse);
    });

    test('class names are injected, not imported', () {
      expect(isPlausibleRequest('the wardrobe there'), isFalse);
      expect(isPlausibleRequest('the wardrobe there', classWords: ['wardrobe']),
          isTrue);
    });

    test('case is ignored on both sides', () {
      expect(isPlausibleRequest('Find The BOTTLE', classWords: ['Bottle']),
          isTrue);
    });
  });

  group('parity with the Python policy', () {
    test('the command categories match speech_policy.py exactly', () {
      // The two tables are hand-mirrored; a divergence would mean the phone
      // and the laptop disagree about what may interrupt what.
      expect(kSteering, {
        'walk', 'find', 'stop', 'mute', 'sonar', 'clock', 'zones', 'repeat',
        'ask',
      });
      expect(kInformational, {
        'describe', 'check', 'path', 'count', 'recall', 'read', 'photo',
      });
    });

    test('priorities are ordered', () {
      expect(kSafety > kResponse, isTrue);
      expect(kResponse > kConfirm, isTrue);
      expect(kConfirm > kRoutine, isTrue);
    });
  });
}
