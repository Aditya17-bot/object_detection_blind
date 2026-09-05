// Telling our own voice apart from the user talking over it.
//
// The phone's speaker reaches the phone's own microphone, and the recognizer
// is grammar-constrained, so it force-matches our TTS back into trained
// phrases: "Bottle on your right" came back as a directional query and the app
// answered its own voice.
//
// The first guard was purely TIME-based: ignore the microphone while speaking,
// plus a 900 ms tail. That is safe and far too blunt. In walk mode the app
// talks every few seconds, so the microphone was deaf for most of the session
// — precisely when a user most wants to interrupt. The user reported it as
// "it's not hearing me properly when I say read, find" (2026-09-05).
//
// Mirror of test_speech_policy's echo tests.
import 'package:flutter_test/flutter_test.dart';
import 'package:blindassist/logic/speech_policy.dart';

void main() {
  group('echo discrimination', () {
    const guidance = "Door at 11 o'clock, close";

    test('our own guidance coming back IS rejected', () {
      // the recognizer force-matches our word "door" into a command
      expect(isProbablyEcho('door', guidance), isTrue);
      expect(isProbablyEcho('close', guidance), isTrue);
      expect(isProbablyEcho('door close', guidance), isTrue);
    });

    test('the user interrupting is NOT rejected', () {
      // words we never say in guidance
      expect(isProbablyEcho('read', guidance), isFalse,
          reason: 'the app must stay interruptible while it is talking');
      expect(isProbablyEcho('find door', guidance), isFalse,
          reason: '"find" was not in what we said, so a human said it');
      expect(isProbablyEcho('walk mode', guidance), isFalse);
      expect(isProbablyEcho('stop', guidance), isFalse);
      expect(isProbablyEcho('take a picture', guidance), isFalse);
    });

    test('a find announcement does not deafen us to the next request', () {
      const said = 'Bottle on your right, close';
      expect(isProbablyEcho('bottle', said), isTrue, reason: 'that was us');
      expect(isProbablyEcho('find bottle', said), isFalse,
          reason: 'that was them');
      expect(isProbablyEcho('describe', said), isFalse);
    });

    test('every single-word command survives a typical announcement', () {
      for (final w in ['read', 'walk', 'stop', 'repeat', 'describe', 'photo']) {
        expect(isProbablyEcho(w, guidance), isFalse,
            reason: '"$w" must be heard while the app is speaking');
      }
    });

    test('empty text is treated as echo, not as a request', () {
      expect(isProbablyEcho('', guidance), isTrue);
      expect(isProbablyEcho('   ', guidance), isTrue);
    });

    test('nothing spoken means nothing can be echo', () {
      expect(isProbablyEcho('read', ''), isFalse);
    });
  });
}
