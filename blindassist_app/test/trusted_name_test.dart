// A name vouched for by the naming head must be SPOKEN, not swallowed.
//
// The nameConfidence gate replaces a class name with the generic word
// "obstacle" below 0.8. Its stated basis is falsified (EVALUATION.md 6.2:
// a dustbin misnamed "toilet" peaks at 0.94 while a correct "chair" sits at
// 0.92 — overlapping bands), so it must not override the one signal that IS
// calibrated: an embedding rename that beat every competing label by
// MIN_MARGIN. Before this, the server identified a wardrobe correctly and the
// phone announced "Obstacle on left, close".
//
// Mirror of test_decision.TestTrustedName.
import 'package:flutter_test/flutter_test.dart';
import 'package:blindassist/logic/decision.dart';
import 'package:blindassist/logic/position.dart';

ObjectInfo wardrobe(double conf, bool trusted) => ObjectInfo(
      name: 'wardrobe',
      confidence: conf,
      hZone: 'left',
      vZone: 'middle',
      proximity: 'close',
      area: 0.2,
      centerX: 0.15,
      phrase: 'left',
      trustedName: trusted,
    );

void main() {
  group('trusted name', () {
    test('untrusted low confidence says obstacle', () {
      final msg = walkMessage(wardrobe(0.72, false)).toLowerCase();
      expect(msg, contains('obstacle'));
      expect(msg, isNot(contains('wardrobe')));
    });

    test('trusted low confidence says the name', () {
      final msg = walkMessage(wardrobe(0.72, true)).toLowerCase();
      expect(msg, contains('wardrobe'));
      expect(msg, isNot(contains('obstacle')));
    });

    test('trust does not depend on confidence at all', () {
      for (final conf in [0.30, 0.55, 0.72, 0.99]) {
        expect(walkMessage(wardrobe(conf, true)).toLowerCase(),
            contains('wardrobe'),
            reason: 'the flag, not the number, decides the word');
      }
    });

    test('high confidence still speaks without the flag', () {
      expect(walkMessage(wardrobe(0.95, false)).toLowerCase(),
          contains('wardrobe'));
    });

    test('default is untrusted', () {
      // a caller that forgets the flag gets the old, safe behaviour
      final info = analyzeBox('wardrobe', 0.72, 0, 0, 100, 100, 1000, 1000);
      expect(info.trustedName, isFalse);
    });

    test('analyzeBox carries the flag through', () {
      final info = analyzeBox('wardrobe', 0.72, 0, 0, 100, 100, 1000, 1000,
          trustedName: true);
      expect(info.trustedName, isTrue);
      expect(walkMessage(info).toLowerCase(), contains('wardrobe'));
    });
  });
}
