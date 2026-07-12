// Mirror of test_decision.py — same cases, same expected strings, so the
// Dart port is proven equivalent to the Python original.
import 'package:flutter_test/flutter_test.dart';

import 'package:blindassist/logic/decision.dart';
import 'package:blindassist/logic/position.dart';

const _centerX = {'left': 0.15, 'center': 0.5, 'right': 0.85};

/// Hand-built ObjectInfo, as if analyzeBox had produced it.
ObjectInfo info(String name,
    {String hZone = 'center',
    String vZone = 'middle',
    String proximity = 'close',
    double area = 0.2,
    double? centerX,
    double conf = 0.9}) {
  return ObjectInfo(
    name: name,
    confidence: conf,
    hZone: hZone,
    vZone: vZone,
    proximity: proximity,
    area: area,
    centerX: centerX ?? _centerX[hZone]!,
    phrase: directionPhrase(hZone, vZone),
  );
}

void main() {
  group('pickObstacle', () {
    test('closer beats more central', () {
      final vcSide = info('chair', hZone: 'right', proximity: 'very close');
      final closeCenter = info('person', proximity: 'close');
      expect(pickObstacle([closeCenter, vcSide]), same(vcSide));
    });
    test('same proximity center wins', () {
      final side = info('chair', hZone: 'left');
      final center = info('person');
      expect(pickObstacle([side, center]), same(center));
    });
    test('far never announced', () {
      expect(pickObstacle([info('chair', proximity: 'far')]), isNull);
    });
    test('medium only matters in center', () {
      expect(pickObstacle([info('chair', hZone: 'left', proximity: 'medium')]),
          isNull);
      final center = info('chair', proximity: 'medium');
      expect(pickObstacle([center]), same(center));
    });
    test('find classes never obstacles', () {
      expect(pickObstacle([info('bottle', proximity: 'very close')]), isNull);
    });
  });

  group('walkMessage', () {
    test('side and center wording', () {
      expect(walkMessage(info('chair', hZone: 'right')), 'Chair on right');
      expect(walkMessage(info('person')), 'Person ahead');
    });
    test('very close side says dodge other way', () {
      expect(walkMessage(info('chair', hZone: 'left', proximity: 'very close')),
          'Chair very close on left, move slightly right');
    });
    test('very close center dodges to freer side', () {
      final person = info('person', proximity: 'very close');
      final chairRight = info('chair', hZone: 'right');
      expect(walkMessage(person, [person, chairRight]),
          'Person very close ahead, move slightly left');
    });
    test('low confidence becomes generic obstacle', () {
      expect(walkMessage(info('toilet', hZone: 'right', conf: 0.65)),
          'Obstacle on right');
      expect(walkMessage(info('refrigerator', hZone: 'left', conf: 0.75)),
          'Obstacle on left');
      final vc =
          info('refrigerator', hZone: 'left', proximity: 'very close', conf: 0.62);
      expect(walkMessage(vc), 'Obstacle very close on left, move slightly right');
    });
    test('confident detection keeps its name', () {
      expect(walkMessage(info('chair', hZone: 'right', conf: 0.85)),
          'Chair on right');
    });
  });

  group('engine walk mode', () {
    test('persistence blocks one-frame flicker', () {
      final e = GuidanceEngine();
      final chair = info('chair', hZone: 'right');
      expect(e.update([chair], 0.0), isNull); // 1st frame: wait
      expect(e.update([chair], 0.1), 'Chair on right');
    });
    test('flicker then gone stays silent', () {
      final e = GuidanceEngine();
      expect(e.update([info('tv', hZone: 'left')], 0.0), isNull);
      expect(e.update([], 0.1), isNull); // misdetection gone
    });
    test('only top priority spoken', () {
      final e = GuidanceEngine();
      final scene = [info('person'), info('chair', hZone: 'right')];
      e.update(scene, 0.0);
      expect(e.update(scene, 0.1), 'Person ahead');
    });
    test('repeat cooldown', () {
      final e = GuidanceEngine();
      final chair = info('chair', hZone: 'right');
      e.update([chair], 0.0);
      expect(e.update([chair], 0.1), 'Chair on right');
      expect(e.update([chair], 1.0), isNull); // too soon to repeat
      expect(e.update([chair], 3.5), 'Chair on right');
    });
    test('min gap between different messages', () {
      final e = GuidanceEngine();
      final chair = info('chair', hZone: 'right');
      final person = info('person');
      e.update([chair], 0.0);
      expect(e.update([chair], 0.1), 'Chair on right');
      // person walks in: higher priority, but 0.3s after last message
      expect(e.update([chair, person], 0.2), isNull);
      expect(e.update([chair, person], 0.3), isNull);
      expect(e.update([chair, person], 1.7), 'Person ahead');
    });
    test('escalation bypasses cooldown', () {
      final e = GuidanceEngine();
      final chair = info('chair', hZone: 'right', proximity: 'close');
      e.update([chair], 0.0);
      expect(e.update([chair], 0.1), 'Chair on right');
      final closer = info('chair', hZone: 'right', proximity: 'very close');
      expect(e.update([closer], 0.3),
          'Chair very close on right, move slightly left');
    });
  });

  group('engine find mode', () {
    test('biggest match wins', () {
      final small = info('bottle', hZone: 'left', area: 0.01);
      final big = info('bottle', hZone: 'right', area: 0.04);
      expect(findTarget([small, big], 'bottle'), same(big));
    });
    test('found message', () {
      final e = GuidanceEngine(mode: 'find', target: 'bottle');
      final bottle = info('bottle',
          hZone: 'right', vZone: 'top', proximity: 'close', area: 0.02);
      e.update([bottle], 0.0);
      expect(e.update([bottle], 0.1), 'Bottle top right, close');
    });
    test('not visible said once then periodic reminder', () {
      final e = GuidanceEngine(mode: 'find', target: 'bottle');
      expect(e.update([], 0.0), isNull); // absence persistence
      expect(e.update([], 0.1), 'Bottle not visible');
      expect(e.update([], 5.0), isNull); // not repeated...
      // ...but after reminderInterval the engine says it is still trying
      expect(e.update([], 10.2), 'Still looking for bottle');
      expect(e.update([], 15.0), isNull); // next one waits too
      expect(e.update([], 20.3), 'Still looking for bottle');
    });
    test('reminder resets when target found', () {
      final e = GuidanceEngine(mode: 'find', target: 'bottle');
      e.update([], 0.0);
      expect(e.update([], 0.1), 'Bottle not visible');
      final bottle =
          info('bottle', hZone: 'left', proximity: 'medium', area: 0.005);
      e.update([bottle], 5.0);
      expect(e.update([bottle], 5.1), 'Bottle left, medium');
      // gone again -> fresh "not visible" first (now enriched by object
      // memory since the bottle was just seen), reminder only later
      e.update([], 8.0);
      expect(e.update([], 8.1), 'Bottle not visible, last seen on your left');
      expect(e.update([], 12.0), isNull);
      expect(e.update([], 18.2), 'Still looking for bottle');
    });
    test('reappearing target reported again', () {
      final e = GuidanceEngine(mode: 'find', target: 'bottle');
      e.update([], 0.0);
      expect(e.update([], 0.1), 'Bottle not visible');
      final bottle =
          info('bottle', hZone: 'left', proximity: 'medium', area: 0.005);
      e.update([bottle], 5.0);
      expect(e.update([bottle], 5.1), 'Bottle left, medium');
      // gone again -> "not visible" is armed again (enriched by memory)
      e.update([], 10.0);
      expect(e.update([], 10.1), 'Bottle not visible, last seen on your left');
    });
    test('find mode requires target', () {
      expect(() => GuidanceEngine(mode: 'find'), throwsArgumentError);
    });
  });

  group('scene summary', () {
    test('empty', () {
      expect(summarizeScene([]), 'Nothing detected');
    });
    test('groups counts and orders center first', () {
      final scene = [
        info('chair', hZone: 'left', area: 0.10),
        info('chair', hZone: 'left', area: 0.12),
        info('dining table', area: 0.30),
        info('person', hZone: 'right', area: 0.20),
      ];
      expect(summarizeScene(scene),
          'A dining table ahead, 2 chairs on your left, a person on your right');
    });
    test('person plural', () {
      final scene = [info('person', hZone: 'right'), info('person', hZone: 'right')];
      expect(summarizeScene(scene), '2 people on your right');
    });
  });

  group('findMessage', () {
    test('not visible wording', () {
      expect(findMessage(null, 'cell phone'), 'Cell phone not visible');
    });
  });

  group('clock bearings', () {
    // info() maps left->0.15, center->0.5, right->0.85 => 10, 12, 2 o'clock
    test('find message clock', () {
      final bottle = info('bottle',
          hZone: 'right', vZone: 'top', proximity: 'close', area: 0.02);
      expect(findMessage(bottle, 'bottle', true), "Bottle at 2 o'clock, close");
    });
    test('walk message clock', () {
      final chair = info('chair', hZone: 'left', proximity: 'close');
      expect(walkMessage(chair, const [], true), "Chair at 10 o'clock");
    });
    test('walk message clock center ahead', () {
      final person = info('person', proximity: 'close');
      expect(walkMessage(person, const [], true), "Person at 12 o'clock");
    });
    test('engine toggle switches wording', () {
      final e = GuidanceEngine(mode: 'walk');
      final chair = info('chair', hZone: 'right', proximity: 'close');
      e.update([chair], 0.0);
      expect(e.update([chair], 0.1), 'Chair on right');
      e.setClock(true);
      expect(e.update([chair], 2.0), "Chair at 2 o'clock");
    });
  });

  group('object memory', () {
    test('recall message zone', () {
      final cup = info('cup', hZone: 'right', proximity: 'close', area: 0.02);
      expect(recallMessage(cup, 5, 'cup'),
          'Cup last seen on your right, 5 seconds ago');
    });
    test('recall message clock', () {
      final cup = info('cup', hZone: 'left', proximity: 'close', area: 0.02);
      expect(recallMessage(cup, 1, 'cup', true),
          "Cup last seen at 10 o'clock, a moment ago");
    });
    test('recall no memory', () {
      expect(recallMessage(null, 0, 'apple'), 'No memory of an apple');
    });
    test('engine recall after object leaves', () {
      final e = GuidanceEngine(mode: 'walk');
      final cup = info('cup', hZone: 'right', proximity: 'close', area: 0.02);
      e.update([cup], 0.0);
      e.update([], 3.0);
      expect(e.recall('cup', 3.0),
          'Cup last seen on your right, 3 seconds ago');
    });
    test('engine recall expires', () {
      final e = GuidanceEngine(mode: 'walk', memoryTtl: 10.0);
      e.update([info('cup', hZone: 'left', area: 0.02)], 0.0);
      expect(e.recall('cup', 100.0), 'No memory of a cup');
    });
    test('engine recall unseen class', () {
      final e = GuidanceEngine(mode: 'walk');
      expect(e.recall('laptop', 1.0), 'No memory of a laptop');
    });
  });
}
