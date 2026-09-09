// Switching the continuous walk warnings off, switching the microphone off,
// and the find timeout that bounds a mis-heard search (all 2026-09-09).
//
// Mirror of the Python GuidanceSwitchTest / MicrophoneSwitchTest /
// FindTimeoutTest.
import 'package:flutter_test/flutter_test.dart';

import 'package:blindassist/logic/decision.dart';
import 'package:blindassist/logic/position.dart';
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

  group('microphone switch', () {
    test('the spoken forms', () {
      for (final c in [
        ('microphone off', 'off'),
        ('microphone on', 'on'),
        ('stop listening', 'off'),
        ('start listening', 'on'),
      ]) {
        final parsed = parseCommand(c.$1);
        expect(parsed?.action, 'listen', reason: c.$1);
        expect(parsed?.target, c.$2, reason: c.$1);
      }
      // A bare form turns the microphone ON, it never toggles: switching it
      // off is the one change with no spoken way back, so it has to be asked
      // for by name. Ambient noise force-matching the single word "listening"
      // is what left the app deaf on the 2026-09-09 walk.
      for (final bare in ['listen', 'listening', 'microphone']) {
        expect(parseCommand(bare)?.action, 'listen', reason: bare);
        expect(parseCommand(bare)?.target, 'on', reason: bare);
      }
    });

    test('"stop listening" is not read as a bare stop', () {
      expect(parseCommand('stop listening')?.action, 'listen');
      expect(parseCommand('stop')?.action, 'stop');
    });

    test('it steals nothing', () {
      expect(parseCommand('stop walk mode')?.action, 'guidance');
      expect(parseCommand('find the door')?.target, 'door');
      expect(parseCommand('mute')?.action, 'mute');
    });
  });

  group('find timeout', () {
    test('a search that sees nothing gives up and returns to walk', () {
      // room noise reached the grammar as "find the refrigerator" on
      // 2026-09-09 and the app reminded the user about it every 10 s
      final engine = GuidanceEngine(findTimeout: 40);
      engine.setMode('find', 'refrigerator');
      final said = <String>[];
      for (var t = 0.0; t < 45; t += 0.5) {
        final msg = engine.update(const [], t);
        if (msg != null) said.add(msg);
      }
      expect(said, contains('Stopped looking for refrigerator'));
      expect(engine.mode, 'walk');
    });

    test('a search that has seen its target never expires', () {
      final engine = GuidanceEngine(findTimeout: 10);
      final seen = [_chair()];
      engine.setMode('find', 'chair');
      engine.update(seen, 0.0); // announced, auto-returns to walk
      engine.setMode('find', 'chair');
      engine.update(seen, 1.0);
      final said = <String>[];
      for (var t = 2.0; t < 40; t += 0.5) {
        final msg = engine.update(const [], t);
        if (msg != null) said.add(msg);
      }
      expect(said.where((m) => m.startsWith('Stopped')), isEmpty);
    });
  });

}

ObjectInfo _chair() => analyzeBox('chair', 0.9, 0.4, 0.4, 0.6, 0.9, 1, 1);
