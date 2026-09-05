// Mirror of test_position.py — same cases, same expected values, so the
// Dart port is proven equivalent to the Python original.
import 'package:flutter_test/flutter_test.dart';

import 'package:blindassist/logic/position.dart';

const w = 1280.0, h = 720.0; // pretend frame size; logic must not care

/// Pixel box of given normalized size centered at normalized (cx, cy).
List<double> boxAt(double cx, double cy, [double bw = 0.1, double bh = 0.1]) =>
    [w * (cx - bw / 2), h * (cy - bh / 2), w * (cx + bw / 2), h * (cy + bh / 2)];

void checkZone(double cx, double cy, String hZone, String vZone) {
  final b = boxAt(cx, cy);
  final info = analyzeBox('chair', 0.9, b[0], b[1], b[2], b[3], w, h);
  expect([info.hZone, info.vZone], [hZone, vZone]);
}

void main() {
  group('zones', () {
    test('left', () => checkZone(0.10, 0.5, 'left', 'middle'));
    test('dead center', () => checkZone(0.50, 0.5, 'center', 'middle'));
    test('right', () => checkZone(0.90, 0.5, 'right', 'middle'));
    test('top right', () => checkZone(0.85, 0.15, 'right', 'top'));
    test('bottom left', () => checkZone(0.15, 0.90, 'left', 'bottom'));
    test('boundary at first third', () {
      checkZone(0.33, 0.5, 'left', 'middle');
      checkZone(0.34, 0.5, 'center', 'middle');
    });
  });

  group('phrases', () {
    test('middle row drops vertical', () {
      expect(directionPhrase('left', 'middle'), 'left');
      expect(directionPhrase('center', 'middle'), 'center ahead');
    });
    test('vertical mentioned when notable', () {
      expect(directionPhrase('right', 'top'), 'top right');
      expect(directionPhrase('center', 'bottom'), 'bottom center');
    });
  });

  group('proximity', () {
    test('person buckets', () {
      expect(proximityBucket('person', 0.50), 'very close');
      expect(proximityBucket('person', 0.20), 'close');
      expect(proximityBucket('person', 0.08), 'medium');
      expect(proximityBucket('person', 0.01), 'far');
    });
    test('bottle uses smaller thresholds', () {
      // 2% of the frame is a FAR person but a CLOSE bottle
      expect(proximityBucket('person', 0.02), 'far');
      expect(proximityBucket('bottle', 0.02), 'close');
    });
    test('unknown class falls back', () {
      expect(proximityBucket('dog', 0.40), 'very close');
    });
  });

  group('custom model classes', () {
    test('door/dustbin are obstacles with thresholds', () {
      for (final name in ['door', 'dustbin']) {
        expect(obstacleClasses, contains(name));
      }
    });
    test('stairs skipped until retrained', () {
      expect(targetClasses, isNot(contains('stairs')));
    });
    test('door proximity sane', () {
      expect(proximityBucket('door', 0.50), 'very close');
      expect(proximityBucket('door', 0.02), 'far');
    });
  });

  group('analyzeBox', () {
    test('full pipeline one box', () {
      // big centered person: half the frame wide/tall => area 0.25 => close
      final b = boxAt(0.5, 0.5, 0.5, 0.5);
      final info = analyzeBox('person', 0.88, b[0], b[1], b[2], b[3], w, h);
      expect(info.phrase, 'center ahead');
      expect(info.proximity, 'close');
      expect(info.area, closeTo(0.25, 0.001));
      expect(info.centerX, closeTo(0.5, 0.001));
    });
    test('scale invariance', () {
      // same normalized box must give identical results at any resolution
      final a = analyzeBox('chair', 0.9, 64, 36, 192, 108, 640, 360);
      final b = analyzeBox('chair', 0.9, 128, 72, 384, 216, 1280, 720);
      expect([a.hZone, a.vZone, a.proximity], [b.hZone, b.vZone, b.proximity]);
    });
  });

  group('distance meters', () {
    test('pinhole estimate', () {
      // 1.7 m person filling half the frame height: 1.7 * 0.85 / 0.5 ~= 2.9 m
      expect(distanceMeters('person', 0.5), closeTo(2.9, 0.1));
    });
    test('smaller box is further', () {
      expect(distanceMeters('person', 0.1)!,
          greaterThan(distanceMeters('person', 0.5)!));
    });
    test('unknown class has no distance', () {
      expect(distanceMeters('dog', 0.5), isNull);
    });
    test('degenerate box', () {
      expect(distanceMeters('person', 0.0), isNull);
    });
    test('analyzeBox populates distance', () {
      final b = boxAt(0.5, 0.5, 0.1, 0.5);
      final info = analyzeBox('person', 0.9, b[0], b[1], b[2], b[3], w, h);
      expect(info.distanceM, isNotNull);
    });
  });

  // The bearing must match the camera's real geometry. Until 2026-09-05 the
  // frame was spread over 10-11-12-1-2 — four hours, 120 degrees — across a
  // camera that sees ~65, so every bearing came out about DOUBLE the true
  // angle. Clock mode is the default, so an O&M-trained traveller was being
  // systematically over-rotated. Mirror of test_position.TestClockHour.
  group('clock hour', () {
    test('center is twelve', () => expect(clockHour(0.5), 12));
    test('frame edges stay within the field of view', () {
      // half the FOV is ~32.5 deg: one clock hour (30 deg), not two
      expect(clockHour(0.0), 11);
      expect(clockHour(1.0), 1);
    });
    test('bands in order', () {
      expect([0.0, 0.3, 0.5, 0.7, 1.0].map(clockHour).toList(),
          [11, 12, 12, 12, 1]);
    });
    test('hour matches the bearing it claims', () {
      for (final cx in [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]) {
        final bearing = (cx - 0.5) * cameraFovDeg;
        final hour = clockHour(cx);
        final signed = hour >= 10 ? hour - 12 : hour; // 11 -> -1, 1 -> +1
        expect((signed * 30.0 - bearing).abs(), lessThanOrEqualTo(15.0),
            reason: "centerX $cx: spoke $hour oclock for $bearing deg");
      }
    });
    test('phrase', () {
      expect(clockPhrase(0.95), "at 1 o'clock");
      expect(clockPhrase(0.05), "at 11 o'clock");
    });
  });
}
