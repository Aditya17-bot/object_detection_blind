// Switching the continuous walk warnings off as a whole (2026-09-09), plus
// the tap counting that gives the camera view a third gesture.
//
// Mirror of the Python GuidanceSwitchTest; the tap half has no Python
// equivalent because the desktop UI has no such gesture.
import 'package:flutter_test/flutter_test.dart';

import 'package:blindassist/logic/multi_tap.dart';
import 'package:blindassist/logic/speech_policy.dart';
import 'package:blindassist/logic/voice_commands.dart';

void main() {
  group('guidance parsing', () {
    test('the spoken forms', () {
      for (final c in [
        ('guidance off', 'off'),
        ('guidance on', 'on'),
        ('quiet mode', 'off'),
        ('pause guidance', 'off'),
        ('resume guidance', 'on'),
      ]) {
        final parsed = parseCommand(c.$1);
        expect(parsed?.action, 'guidance', reason: c.$1);
        expect(parsed?.target, c.$2, reason: c.$1);
      }
      expect(parseCommand('guidance')?.target, isNull);
    });

    test('"stop walk mode" switches it off, it does not cut a sentence', () {
      for (final text in ['stop walk mode', 'stop the guidance', 'stop walking']) {
        final parsed = parseCommand(text);
        expect(parsed?.action, 'guidance', reason: text);
        expect(parsed?.target, 'off', reason: text);
      }
    });

    test('bare stop is untouched — it is how a long read is cut off', () {
      expect(parseCommand('stop')?.action, 'stop');
      expect(parseCommand('stop it')?.action, 'stop');
    });

    test('it steals nothing', () {
      expect(parseCommand('walk mode')?.action, 'walk');
      expect(parseCommand('find the door')?.target, 'door');
      expect(parseCommand('mute')?.action, 'mute');
      expect(parseCommand('sonar off')?.target, 'off');
      expect(parseCommand('describe')?.action, 'describe');
    });

    test('it steers, so a command the user spoke is never gated', () {
      // the switch has to work while a read-out holds the channel: it is one
      // of the things a user reaches for BECAUSE the app is talking
      expect(kSteering.contains('guidance'), isTrue);
      final policy = SpeechPolicy();
      policy.begin('read', 0, seconds: 30);
      expect(policy.allowCommand('guidance', 1), isTrue);
    });
  });

  group('multi-tap', () {
    test('counts a burst, then starts over after the window', () {
      final taps = MultiTap(window: 0.45);
      expect(taps.tap(0.0), 1);
      expect(taps.tap(0.2), 2);
      expect(taps.tap(0.4), 3);
      expect(taps.tap(1.5), 1); // new burst
    });

    test('settles only after the window has passed', () {
      final taps = MultiTap(window: 0.45);
      taps.tap(0.0);
      expect(taps.settled(0.3), isFalse);
      expect(taps.settled(0.5), isTrue);
    });

    test('one describes, two toggle sonar, three switch guidance', () {
      expect(tapAction(1), 'describe');
      expect(tapAction(2), 'sonar');
      expect(tapAction(3), 'guidance');
      // a fumbled fourth tap must not fall through to something else
      expect(tapAction(4), 'guidance');
      expect(tapAction(0), isNull);
    });

    test('reset clears the burst', () {
      final taps = MultiTap();
      taps.tap(0.0);
      taps.tap(0.1);
      taps.reset();
      expect(taps.count, 0);
      expect(taps.tap(0.2), 1);
    });
  });
}
