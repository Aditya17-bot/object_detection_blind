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
    test('medium is silent even dead ahead', () {
      // 2026-07-31: walk mode used to announce a medium obstacle in the
      // centre. Field feedback was that continuous naming became noise, so the
      // line moved to walkMinProximity ('close'). The full inventory is still
      // available on demand through describe() / checkDirection().
      expect(pickObstacle([info('chair', hZone: 'left', proximity: 'medium')]),
          isNull);
      expect(pickObstacle([info('chair', proximity: 'medium')]), isNull);
    });
    test('close and very close still announced', () {
      final close = info('chair', hZone: 'left');
      expect(pickObstacle([close]), same(close));
      final vc = info('chair', hZone: 'right', proximity: 'very close');
      expect(pickObstacle([vc]), same(vc));
    });
    test('find classes never obstacles', () {
      expect(pickObstacle([info('bottle', proximity: 'very close')]), isNull);
    });
  });

  group('walkMessage', () {
    // hand-built infos have distanceM=null, so the proximity BUCKET is
    // appended ("close"); real analyzeBox infos say "about N meters" for
    // medium/far — see the distance messages group.
    test('side and center wording', () {
      expect(walkMessage(info('chair', hZone: 'right')), 'Chair on right, close');
      expect(walkMessage(info('person')), 'Person ahead, close');
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
          'Obstacle on right, close');
      expect(walkMessage(info('refrigerator', hZone: 'left', conf: 0.75)),
          'Obstacle on left, close');
      final vc =
          info('refrigerator', hZone: 'left', proximity: 'very close', conf: 0.62);
      expect(walkMessage(vc), 'Obstacle very close on left, move slightly right');
    });
    test('confident detection keeps its name', () {
      expect(walkMessage(info('chair', hZone: 'right', conf: 0.85)),
          'Chair on right, close');
    });
    test('custom-model classes named below threshold', () {
      // door/dustbin come from the DEDICATED model (no COCO lookalike), so
      // they keep their name even at 0.5 conf — never spoken as "obstacle".
      expect(walkMessage(info('door', conf: 0.5)), 'Door ahead, close');
      expect(walkMessage(info('dustbin', hZone: 'left', conf: 0.55)),
          'Dustbin on left, close');
    });
  });

  group('engine walk mode', () {
    // these pin the anti-spam LOGIC, so they force zone wording (useClock:
    // false) and use hand-built infos (distanceM null -> bucket "close").
    test('persistence blocks one-frame flicker', () {
      final e = GuidanceEngine(useClock: false);
      final chair = info('chair', hZone: 'right');
      expect(e.update([chair], 0.0), isNull); // 1st frame: wait
      expect(e.update([chair], 0.1), 'Chair on right, close');
    });
    test('flicker then gone stays silent', () {
      final e = GuidanceEngine(useClock: false);
      expect(e.update([info('tv', hZone: 'left')], 0.0), isNull);
      expect(e.update([], 0.1), isNull); // misdetection gone
    });
    test('only top priority spoken', () {
      final e = GuidanceEngine(useClock: false);
      final scene = [info('person'), info('chair', hZone: 'right')];
      e.update(scene, 0.0);
      expect(e.update(scene, 0.1), 'Person ahead, close');
    });
    test('repeat cooldown', () {
      final e = GuidanceEngine(useClock: false);
      final chair = info('chair', hZone: 'right');
      e.update([chair], 0.0);
      expect(e.update([chair], 0.1), 'Chair on right, close');
      expect(e.update([chair], 1.0), isNull); // too soon to repeat
      expect(e.update([chair], 3.5), 'Chair on right, close');
    });
    test('min gap between different messages', () {
      final e = GuidanceEngine(useClock: false);
      final chair = info('chair', hZone: 'right');
      final person = info('person');
      e.update([chair], 0.0);
      expect(e.update([chair], 0.1), 'Chair on right, close');
      // person walks in: higher priority, but 0.3s after last message
      expect(e.update([chair, person], 0.2), isNull);
      expect(e.update([chair, person], 0.3), isNull);
      expect(e.update([chair, person], 1.7), 'Person ahead, close');
    });
    test('escalation bypasses cooldown', () {
      final e = GuidanceEngine(useClock: false);
      final chair = info('chair', hZone: 'right', proximity: 'close');
      e.update([chair], 0.0);
      expect(e.update([chair], 0.1), 'Chair on right, close');
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
    test('found message on the very first sighting', () {
      // Find is EAGER: the user asked, so one solid detection is enough.
      // Requiring two consecutive frames cost four of six sightings at the
      // phone's real 2 FPS (measured 2026-09-05) - the app stayed silent with
      // the object on screen.
      final e = GuidanceEngine(mode: 'find', target: 'bottle', useClock: false);
      final bottle = info('bottle',
          hZone: 'right', vZone: 'top', proximity: 'close', area: 0.02);
      expect(e.update([bottle], 0.0), 'Bottle top right, close');
    });
    test('a flickering target is never called absent', () {
      // The regression the user reported: "I see the person on screen but it
      // just keeps saying it is still looking". A detector that drops the
      // object on alternate frames must not produce "not visible" - saying
      // that about something in frame is the expensive error, and a blind
      // user cannot check the screen to find out.
      final e = GuidanceEngine(mode: 'find', target: 'person', useClock: false);
      final person =
          info('person', hZone: 'center', proximity: 'medium', area: 0.02);
      final said = <String>[];
      for (var n = 0; n < 20; n++) {
        final msg = e.update(n % 2 == 0 ? [person] : [], n * 0.5);
        if (msg != null) said.add(msg);
        if (e.mode != 'find') break; // announced and completed
      }
      expect(said, isNotEmpty, reason: 'a visible target must be announced');
      final joined = said.join(' ').toLowerCase();
      expect(joined, isNot(contains('not visible')));
      expect(joined, isNot(contains('still looking')));
    });
    test('absence is measured in seconds not frames', () {
      final e = GuidanceEngine(mode: 'find', target: 'bottle');
      expect(e.update([], 0.0), isNull);
      expect(e.update([], 0.1), isNull, reason: '0.1 s is not absence');
      expect(e.update([], 2.0), isNull, reason: 'still inside the grace');
      expect(e.update([], 2.6), 'Bottle not visible');
    });
    test('not visible said once then periodic reminder', () {
      final e = GuidanceEngine(mode: 'find', target: 'bottle');
      expect(e.update([], 0.0), isNull); // absence grace
      expect(e.update([], 2.6), 'Bottle not visible');
      expect(e.update([], 5.0), isNull); // not repeated...
      // ...but after reminderInterval the engine says it is still trying
      expect(e.update([], 12.7), 'Still looking for bottle');
      expect(e.update([], 15.0), isNull); // next one waits too
      expect(e.update([], 22.8), 'Still looking for bottle');
    });
    test('reminder keeps firing until target found', () {
      final e = GuidanceEngine(mode: 'find', target: 'bottle', useClock: false);
      e.update([], 0.0);
      expect(e.update([], 2.6), 'Bottle not visible');
      expect(e.update([], 5.0), isNull);
      expect(e.update([], 12.7), 'Still looking for bottle');
      final bottle =
          info('bottle', hZone: 'left', proximity: 'medium', area: 0.005);
      expect(e.update([bottle], 15.0), 'Bottle left, medium');
    });
    test('found completes search', () {
      // user decision 2026-07-16: announcing the position once IS the find
      // result - the engine must drop back to walk mode, not keep repeating
      final e = GuidanceEngine(mode: 'find', target: 'bottle', useClock: false);
      final bottle =
          info('bottle', hZone: 'left', proximity: 'medium', area: 0.005);
      expect(e.update([bottle], 0.0), 'Bottle left, medium');
      expect(e.mode, 'walk');
      // bottle is a FIND class -> silent in walk mode, no more repeats
      expect(e.update([bottle], 5.0), isNull);
      expect(e.update([bottle], 10.0), isNull);
    });
    test('new search after completion', () {
      final e = GuidanceEngine(mode: 'find', target: 'bottle', useClock: false);
      final bottle =
          info('bottle', hZone: 'left', proximity: 'medium', area: 0.005);
      expect(e.update([bottle], 0.0), 'Bottle left, medium');
      // asking again starts a fresh search that reports again
      e.setMode('find', 'bottle');
      expect(e.update([bottle], 5.0), 'Bottle left, medium');
      expect(e.mode, 'walk');
    });
    test('a single misdetection still never warns in walk mode', () {
      // Decaying the streak must not make walk mode trigger-happy: one stray
      // frame still never reaches the walk persistence of 2.
      final e = GuidanceEngine(useClock: false);
      final chair =
          info('chair', hZone: 'center', proximity: 'close', area: 0.2);
      expect(e.update([chair], 0.0), isNull);
      for (var n = 1; n < 8; n++) {
        expect(e.update([], n * 0.5), isNull,
            reason: 'a one-frame ghost must decay away silently');
      }
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
    // info() maps left->0.15, center->0.5, right->0.85. At the corrected
    // 65-degree field of view those are -22.8, 0.0 and +22.8 degrees, i.e.
    // 11, 12 and 1 o'clock. The old expectations (10 / 12 / 2) came from a
    // mapping that spread 120 degrees across a 65-degree camera and so
    // roughly doubled every bearing — see position_test 'clock hour'.
    test('find message clock', () {
      final bottle = info('bottle',
          hZone: 'right', vZone: 'top', proximity: 'close', area: 0.02);
      expect(findMessage(bottle, 'bottle', true), "Bottle at 1 o'clock, close");
    });
    test('walk message clock', () {
      final chair = info('chair', hZone: 'left', proximity: 'close');
      expect(walkMessage(chair, const [], true), "Chair at 11 o'clock, close");
    });
    test('walk message clock center ahead', () {
      final person = info('person', proximity: 'close');
      expect(walkMessage(person, const [], true), "Person at 12 o'clock, close");
    });
    test('clock is the default', () {
      // user decision 2026-07-14: clock bearings are the default wording
      final e = GuidanceEngine(mode: 'walk');
      final chair = info('chair', hZone: 'right', proximity: 'close');
      e.update([chair], 0.0);
      expect(e.update([chair], 0.1), "Chair at 1 o'clock, close");
    });
    test('engine toggle switches wording', () {
      final e = GuidanceEngine(mode: 'walk', useClock: false);
      final chair = info('chair', hZone: 'right', proximity: 'close');
      e.update([chair], 0.0);
      expect(e.update([chair], 0.1), 'Chair on right, close');
      e.setClock(true);
      expect(e.update([chair], 2.0), "Chair at 1 o'clock, close");
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
          "Cup last seen at 11 o'clock, a moment ago");
    });
    test('recall no memory', () {
      expect(recallMessage(null, 0, 'apple'), 'No memory of an apple');
    });
    test('engine recall after object leaves', () {
      final e = GuidanceEngine(mode: 'walk', useClock: false);
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

  group('distance messages', () {
    // real analyzeBox infos carry a metric estimate; medium/far speak meters.
    ObjectInfo personAt(double heightFrac, {double width = 0.1}) => analyzeBox(
        'person', 0.9, 0.5 - width / 2, 0.5 - heightFrac / 2, 0.5 + width / 2,
        0.5 + heightFrac / 2, 1, 1);

    test('far person speaks meters', () {
      final p = personAt(0.2); // small box -> far
      expect(p.proximity, 'far');
      expect(findMessage(p, 'person'), contains('meter'));
    });
    test('near person keeps bucket', () {
      final p = personAt(0.9, width: 0.6); // big box -> close/very close
      expect(['close', 'very close'], contains(p.proximity));
      expect(findMessage(p, 'person'), isNot(contains('meter')));
    });
    test('meters value is reasonable', () {
      expect(findMessage(personAt(0.2), 'person'),
          matches(RegExp(r'about \d+ meters')));
    });
    test('meters are find-mode only, not walk', () {
      final p = personAt(0.2);
      expect(walkMessage(p), isNot(contains('meter')));
      expect(walkMessage(p), contains('far'));
    });
    test('clipped box suppresses meters', () {
      // person box jammed against the bottom edge -> height untrustworthy
      final p = analyzeBox('person', 0.9, 0.45, 0.6, 0.55, 1.0, 1, 1);
      expect(p.distanceM, isNull);
      expect(findMessage(p, 'person'), isNot(contains('meter')));
    });
    test('low confidence suppresses meters', () {
      final p = personAt(0.2);
      final low = ObjectInfo(
        name: p.name,
        confidence: 0.7,
        hZone: p.hZone,
        vZone: p.vZone,
        proximity: p.proximity,
        area: p.area,
        centerX: p.centerX,
        phrase: p.phrase,
        distanceM: p.distanceM,
      );
      expect(findMessage(low, 'person'), isNot(contains('meter')));
    });
  });

  group('clear path', () {
    test('open ahead when obstacles on sides', () {
      final scene = [
        info('chair', hZone: 'left', proximity: 'close', area: 0.2),
        info('chair', hZone: 'right', proximity: 'close', area: 0.2),
      ];
      expect(clearPath(scene), 'Path clear ahead');
    });
    test('steers away from center block', () {
      final scene = [
        info('person', proximity: 'very close', area: 0.4),
        info('chair', hZone: 'right', proximity: 'close', area: 0.1),
      ];
      expect(clearPath(scene), 'Clearest on your left');
    });
    test('far obstacles ignored', () {
      expect(clearPath([info('person', proximity: 'far', area: 0.01)]),
          'Path clear ahead');
    });
    test('near small hazard beats far bulk', () {
      // small CLOSE stool ahead avoided for bulky but only-MEDIUM side couches
      final scene = [
        info('chair', proximity: 'close', area: 0.05),
        info('couch', hZone: 'left', proximity: 'medium', area: 0.4),
        info('couch', hZone: 'right', proximity: 'medium', area: 0.4),
      ];
      expect(clearPath(scene), 'Clearest on your left');
    });
    test('all blocked says stop', () {
      final scene = [
        info('chair', hZone: 'left', proximity: 'close', area: 0.1),
        info('person', proximity: 'close', area: 0.1),
        info('chair', hZone: 'right', proximity: 'close', area: 0.1),
      ];
      expect(clearPath(scene), 'Stop, no clear path');
    });
    test('door is not an obstacle for path', () {
      expect(clearPath([info('door', proximity: 'close', area: 0.3)]),
          'Path clear ahead');
    });
    test('empty scene is ahead', () {
      expect(clearPath([]), 'Path clear ahead');
    });
    test('engine path stamps clock', () {
      final e = GuidanceEngine(mode: 'walk');
      final scene = [
        info('chair', hZone: 'left', proximity: 'close', area: 0.2),
        info('person', proximity: 'very close', area: 0.4),
      ];
      expect(e.path(scene, 0.0), 'Clearest on your right');
    });
  });

  group('toothbrush findable', () {
    test('toothbrush is a find class', () {
      expect(findClasses, contains('toothbrush'));
      expect(targetClasses, contains('toothbrush'));
    });
  });

  group('count', () {
    test('none', () => expect(countMessage([], 'chair'), 'No chairs'));
    test('one', () => expect(countMessage([info('chair')], 'chair'), '1 chair'));
    test('many counts only target', () {
      final scene = [
        info('chair', hZone: 'left'),
        info('chair', hZone: 'right'),
        info('person'),
      ];
      expect(countMessage(scene, 'chair'), '2 chairs');
    });
    test('person plural', () {
      expect(countMessage([info('person'), info('person')], 'person'),
          '2 people');
    });
    test('engine count stamps clock', () {
      final e = GuidanceEngine();
      expect(e.count([info('chair'), info('chair')], 'chair', 0.0), '2 chairs');
    });
  });

  group('checkDirection', () {
    test('empty direction says nothing there', () {
      final scene = [info('chair', hZone: 'right')];
      expect(checkDirection(scene, 'left'), 'Nothing on your left');
      expect(checkDirection(scene, 'ahead'), 'Nothing ahead');
    });
    test('reports what is there with its bucket', () {
      expect(checkDirection([info('chair', hZone: 'left')], 'left'),
          'A chair close on your left');
    });
    test('ahead maps to the center zone', () {
      expect(checkDirection([info('door', proximity: 'medium')], 'ahead'),
          'A door medium ahead');
    });
    test('closest first and capped at two', () {
      final scene = [
        info('chair', hZone: 'right', proximity: 'far', area: 0.4),
        info('person', hZone: 'right', proximity: 'very close'),
        info('bottle', hZone: 'right', proximity: 'medium'),
      ];
      final msg = checkDirection(scene, 'right');
      expect(msg, 'A person very close on your right, and a bottle medium');
      expect(msg, isNot(contains('chair')));
    });
    test('find classes are reported too', () {
      expect(checkDirection([info('cup', hZone: 'left')], 'left'),
          'A cup close on your left');
    });
    test('untrusted name becomes obstacle', () {
      expect(checkDirection([info('toilet', hZone: 'left', conf: 0.65)], 'left'),
          'An obstacle close on your left');
    });
    test('unknown direction returns null', () {
      expect(checkDirection([info('chair')], 'behind'), isNull);
    });
    test('engine check stamps the clock and passes null through', () {
      final e = GuidanceEngine();
      expect(e.check([info('chair', hZone: 'left')], 'left', 0.0),
          'A chair close on your left');
      expect(e.check([info('chair')], 'behind', 1.0), isNull);
    });
  });

  group('stateSummary', () {
    test('groups what is visible and reports engine state', () {
      final e = GuidanceEngine();
      final state = e.stateSummary(
          [info('chair', hZone: 'left'), info('chair', hZone: 'left')], 0.0);
      expect(state['mode'], 'walk');
      final visible = state['visible'] as List;
      expect(visible.length, 1);
      expect(visible.first['name'], 'chair');
      expect(visible.first['count'], 2);
      expect(visible.first['zone'], 'left');
      // no leaked internals: the router reads facts, not object handles
      expect(visible.first.containsKey('_area'), isFalse);
    });
  });
}
