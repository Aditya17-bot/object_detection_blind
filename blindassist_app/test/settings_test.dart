// Greeting logic. Pure, so it is tested without a clock, a device or the
// shared_preferences plugin — same rule the logic/ layer follows.
import 'package:blindassist/settings.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('timeOfDayGreeting', () {
    test('morning until noon', () {
      expect(timeOfDayGreeting(DateTime(2026, 7, 31, 0, 0)), 'Good morning');
      expect(timeOfDayGreeting(DateTime(2026, 7, 31, 11, 59)), 'Good morning');
    });
    test('afternoon from noon to five', () {
      expect(timeOfDayGreeting(DateTime(2026, 7, 31, 12, 0)), 'Good afternoon');
      expect(timeOfDayGreeting(DateTime(2026, 7, 31, 16, 59)), 'Good afternoon');
    });
    test('evening from five', () {
      expect(timeOfDayGreeting(DateTime(2026, 7, 31, 17, 0)), 'Good evening');
      expect(timeOfDayGreeting(DateTime(2026, 7, 31, 23, 59)), 'Good evening');
    });
  });

  group('greetingFor', () {
    test('includes the name', () {
      expect(greetingFor(DateTime(2026, 7, 31, 20), 'Aditya'),
          'Good evening, Aditya');
    });
    test('an empty or missing name degrades to the bare greeting', () {
      // never "Good morning, " with a dangling comma — it is spoken aloud
      expect(greetingFor(DateTime(2026, 7, 31, 9), ''), 'Good morning');
      expect(greetingFor(DateTime(2026, 7, 31, 9), '   '), 'Good morning');
      expect(greetingFor(DateTime(2026, 7, 31, 9), null), 'Good morning');
    });
    test('trims stray whitespace from a typed name', () {
      expect(greetingFor(DateTime(2026, 7, 31, 13), '  Aditya '),
          'Good afternoon, Aditya');
    });
  });
}
