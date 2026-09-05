// Mirror of test_object_memory.py.
//
// The staleness behaviour matters most. A remembered location is a claim about
// the past that the user acts on in the present, and things move; if the age is
// not prominent the memory sends someone on a wasted trip with full confidence.
import 'package:flutter_test/flutter_test.dart';
import 'package:blindassist/logic/object_memory.dart';
import 'package:blindassist/logic/position.dart';

const double hour = 3600.0;

ObjectInfo info(String name,
        {double cx = 0.5,
        double cy = 0.5,
        double area = 0.05,
        String hZone = 'center'}) =>
    ObjectInfo(
      name: name,
      confidence: 0.9,
      hZone: hZone,
      vZone: 'middle',
      proximity: 'medium',
      area: area,
      centerX: cx,
      phrase: hZone,
      centerY: cy,
    );

void main() {
  group('agoPhrase', () {
    test('scales from seconds to days', () {
      expect(agoPhrase(0), 'just now');
      expect(agoPhrase(20), '20 seconds ago');
      expect(agoPhrase(60), '1 minute ago');
      expect(agoPhrase(600), '10 minutes ago');
      expect(agoPhrase(2 * hour), 'about 2 hours ago');
      expect(agoPhrase(26 * hour), 'yesterday');
      expect(agoPhrase(72 * hour), '3 days ago');
    });

    test('never negative', () => expect(agoPhrase(-5), 'just now'));

    test('hours are vague on purpose', () {
      // precision would be false confidence: the user needs to know whether it
      // is fresh enough to trust, not the exact minute
      expect(agoPhrase(3 * hour + 400), contains('about'));
    });
  });

  group('remember', () {
    test('stores the biggest sighting of each class', () {
      final m = ObjectMemory();
      m.remember([info('bottle', area: 0.01, cx: 0.2),
                  info('bottle', area: 0.05, cx: 0.8)], 1000);
      expect(m.get('bottle', 1000)!.centerX, closeTo(0.8, 1e-9));
    });

    test('records what the object was near', () {
      // "near a table" is what makes a memory actionable an hour later
      final m = ObjectMemory();
      m.remember([
        info('cell phone', cx: 0.50, cy: 0.50, area: 0.01),
        info('dining table', cx: 0.55, cy: 0.55, area: 0.30),
      ], 1000);
      expect(m.get('cell phone', 1000)!.near, contains('dining table'));
    });

    test('distant objects are context, not near', () {
      final m = ObjectMemory();
      m.remember([
        info('cell phone', cx: 0.1, cy: 0.1, area: 0.01),
        info('bed', cx: 0.9, cy: 0.9, area: 0.4),
      ], 1000);
      final s = m.get('cell phone', 1000)!;
      expect(s.near, isEmpty);
      expect(s.context, contains('bed'));
    });

    test('an object is never near itself', () {
      final m = ObjectMemory();
      m.remember([info('chair', cx: 0.5, area: 0.1),
                  info('chair', cx: 0.52, area: 0.2)], 1000);
      final s = m.get('chair', 1000)!;
      expect(s.near, isNot(contains('chair')));
      expect(s.context, isNot(contains('chair')));
    });

    test('an empty frame changes nothing', () {
      final m = ObjectMemory();
      m.remember([info('bottle')], 1000);
      m.remember([], 2000);
      expect(m.get('bottle', 2000), isNotNull);
    });
  });

  group('expiry', () {
    test('remembers for hours, not seconds', () {
      // the engine's own 30-second memory answers a different question
      final m = ObjectMemory();
      m.remember([info('cell phone')], 0);
      expect(m.get('cell phone', 6 * hour), isNotNull);
    });

    test('expires past the ttl', () {
      final m = ObjectMemory(ttl: hour);
      m.remember([info('cell phone')], 0);
      expect(m.get('cell phone', 2 * hour), isNull);
    });

    test('capacity is bounded and drops the oldest', () {
      final m = ObjectMemory(maxEntries: 3);
      var n = 0;
      for (final name in ['a', 'b', 'c', 'd', 'e']) {
        m.remember([info(name)], 1000 + (n++).toDouble());
      }
      expect(m.known(1010).length, lessThanOrEqualTo(3));
      expect(m.known(1010), contains('e'));
      expect(m.known(1010), isNot(contains('a')));
    });
  });

  group('recallSentence', () {
    test('age is spoken before the place', () {
      // the place is a claim about the past; the age is what tells the user how
      // much to trust it
      const s = Sighting(
          name: 'cell phone',
          hZone: 'left',
          centerX: 0.2,
          centerY: 0.5,
          proximity: 'medium',
          near: ['dining table'],
          at: 0);
      final out = recallSentence(s, 'cell phone', 2 * hour);
      expect(out.indexOf('hours ago'), lessThan(out.indexOf('dining table')));
    });

    test('the worked example', () {
      const s = Sighting(
          name: 'cell phone',
          hZone: 'left',
          centerX: 0.2,
          centerY: 0.5,
          proximity: 'medium',
          near: ['dining table'],
          context: ['bed'],
          at: 0);
      expect(recallSentence(s, 'cell phone', 2 * hour),
          'Cell phone, about 2 hours ago, near a dining table');
    });

    test('falls back to room context when nothing was near', () {
      const s = Sighting(
          name: 'bottle',
          hZone: 'left',
          centerX: 0.2,
          centerY: 0.5,
          proximity: 'medium',
          context: ['bed', 'chair'],
          at: 0);
      final out = recallSentence(s, 'bottle', 60);
      expect(out, contains('in view'));
      expect(out, contains('bed'));
    });

    test('says only the age when there is no context', () {
      const s = Sighting(
          name: 'bottle',
          hZone: 'left',
          centerX: 0.2,
          centerY: 0.5,
          proximity: 'medium',
          at: 0);
      expect(recallSentence(s, 'bottle', 60), 'Bottle, 1 minute ago');
    });

    test('no memory', () {
      expect(recallSentence(null, 'bottle', 0), 'No memory of a bottle');
      expect(recallSentence(null, 'umbrella', 0), 'No memory of an umbrella');
    });
  });

  group('persistence', () {
    test('round trip', () {
      final m = ObjectMemory();
      m.remember([
        info('cell phone', cx: 0.3, cy: 0.4),
        info('dining table', cx: 0.32, cy: 0.42, area: 0.3),
      ], 1000);
      final restored = ObjectMemory()..loadJson(m.toJson());
      expect(restored.get('cell phone', 1000)!.toJson(),
          m.get('cell phone', 1000)!.toJson());
    });

    test('survives a restart with the clock intact', () {
      // wall-clock timestamps are the whole reason this is separate from the
      // engine's monotonic memory
      final m = ObjectMemory();
      m.remember([info('cell phone')], 1700000000);
      final restored = ObjectMemory()..loadJson(m.toJson());
      expect(restored.recall('cell phone', 1700000000 + 2 * hour),
          contains('about 2 hours ago'));
    });

    test('a corrupt file does not stop the app', () {
      final m = ObjectMemory();
      m.loadJson({'sightings': [{'nonsense': true}, null, 5]});
      m.loadJson('not a map');
      m.loadJson({});
      expect(m.known(0), isEmpty);
    });

    test('expired entries are dropped on load', () {
      final m = ObjectMemory(ttl: hour);
      m.remember([info('bottle')], 0);
      final restored = ObjectMemory(ttl: hour)
        ..loadJson(m.toJson(), at: 5 * hour);
      expect(restored.known(5 * hour), isEmpty);
    });
  });
}
