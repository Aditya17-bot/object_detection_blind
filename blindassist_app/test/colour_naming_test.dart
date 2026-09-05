// Mirror of test_colour_naming.py.
//
// The abstention cases matter most: a user matching a shirt to trousers acts on
// the answer and cannot check it, so a confidently wrong colour is worse than
// "I can't tell".
import 'package:flutter_test/flutter_test.dart';
import 'package:blindassist/logic/colour_naming.dart';

void main() {
  group('rgbToHsv', () {
    test('primaries', () {
      for (final c in [
        ([255, 0, 0], 0.0),
        ([0, 255, 0], 120.0),
        ([0, 0, 255], 240.0),
      ]) {
        final rgb = c.$1;
        final (h, s, v) = rgbToHsv(rgb[0], rgb[1], rgb[2]);
        expect(h, closeTo(c.$2, 0.001));
        expect(s, closeTo(1.0, 0.001));
        expect(v, closeTo(1.0, 0.001));
      }
    });

    test('grey has no hue and no saturation', () {
      final (_, s, v) = rgbToHsv(128, 128, 128);
      expect(s, closeTo(0.0, 1e-9));
      expect(v, closeTo(128 / 255, 0.001));
    });
  });

  group('nameColour', () {
    test('saturated hues', () {
      final cases = {
        [230, 30, 30]: 'red',
        [240, 150, 20]: 'orange',
        [240, 230, 40]: 'yellow',
        [40, 190, 60]: 'green',
        [40, 200, 200]: 'turquoise',
        [40, 70, 220]: 'blue',
        [140, 50, 200]: 'purple',
        [230, 60, 170]: 'pink',
      };
      cases.forEach((rgb, want) {
        expect(nameColour(rgb[0], rgb[1], rgb[2]), want, reason: '$rgb');
      });
    });

    test('greys by brightness', () {
      expect(nameColour(20, 20, 22), 'black');
      expect(nameColour(90, 90, 92), 'dark grey');
      expect(nameColour(160, 160, 162), 'grey');
      expect(nameColour(240, 240, 240), 'white');
    });

    test('brown is not reported as orange', () {
      // "orange trousers" and "brown trousers" are a different garment
      expect(nameColour(110, 70, 30), 'brown');
      expect(nameColour(90, 60, 25), 'brown');
    });

    test('dark and light qualifiers', () {
      expect(nameColour(20, 30, 70), 'dark blue');
      expect(nameColour(170, 190, 250), 'light blue');
    });

    test('abstains when too dark to judge', () {
      // an unlit patch and a black jumper look identical to a sensor
      expect(nameColour(6, 6, 6), isNull);
      expect(nameColour(0, 0, 0), isNull);
    });

    test('abstains on a blown highlight', () {
      expect(nameColour(253, 253, 254), isNull);
    });

    test('a dark but readable patch is still named', () {
      expect(nameColour(25, 25, 26), 'black');
    });
  });

  group('messages', () {
    test('capitalised for speech', () {
      expect(colourMessage(40, 70, 220), 'Blue');
      expect(colourMessage(20, 30, 70), 'Dark blue');
    });

    test('abstention says what to do about it', () {
      final msg = colourMessage(3, 3, 3);
      expect(msg, contains("can't tell"));
      expect(msg.toLowerCase(), contains('light'));
    });
  });

  group('lightMessage', () {
    test('bands', () {
      expect(lightMessage(0.02), "It's dark here");
      expect(lightMessage(0.15), "It's dim here");
      expect(lightMessage(0.40), "It's bright here");
      expect(lightMessage(0.90), "It's very bright here");
    });

    test('never claims to know about a switch', () {
      // the camera cannot tell a bulb from a window
      for (final l in [0.0, 0.1, 0.3, 0.5, 0.8, 1.0]) {
        final msg = lightMessage(l).toLowerCase();
        expect(msg, isNot(contains('light is on')));
        expect(msg, isNot(contains('light is off')));
        expect(msg, isNot(contains('switch')));
      }
    });
  });
}
