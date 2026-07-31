// BlindAssist — user settings. Currently one thing: who the user is, so the
// app can greet them by name at launch.
//
// The greeting is not decoration. A blind user cannot see a splash screen, so
// the first thing they hear IS the app's "it started" signal — and a personal
// greeting is a clearer confirmation than a generic chime that it is THEIR
// configured app that came up, not a fresh install with no settings.
//
// greetingFor() is pure and takes the time, so the whole thing is unit-tested
// without a clock, a device or a plugin — the same rule the logic/ layer follows.
library;

import 'package:shared_preferences/shared_preferences.dart';

/// Default until the user sets their own in the features page.
const String kDefaultUserName = 'Aditya';

const String _kNameKey = 'user_name';

/// "Good morning" / "Good afternoon" / "Good evening" for [now].
/// Boundaries: <12 morning, <17 afternoon, else evening.
String timeOfDayGreeting(DateTime now) {
  if (now.hour < 12) return 'Good morning';
  if (now.hour < 17) return 'Good afternoon';
  return 'Good evening';
}

/// The full spoken launch greeting: "Good evening, Aditya".
/// An empty name degrades to the bare greeting rather than a dangling comma.
String greetingFor(DateTime now, String? name) {
  final greeting = timeOfDayGreeting(now);
  final who = (name ?? '').trim();
  return who.isEmpty ? greeting : '$greeting, $who';
}

/// Persisted settings. Reads are cached in [userName] so the UI and the
/// speaker can use it synchronously; a failed load simply leaves the default
/// (a missing preference must never block startup — the camera matters more).
class AppSettings {
  static String userName = kDefaultUserName;

  static Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final stored = prefs.getString(_kNameKey);
      if (stored != null && stored.trim().isNotEmpty) {
        userName = stored.trim();
      }
    } catch (_) {
      // keep the default; startup is not worth failing over a preference
    }
  }

  static Future<void> setUserName(String name) async {
    userName = name.trim().isEmpty ? kDefaultUserName : name.trim();
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kNameKey, userName);
    } catch (_) {}
  }

  /// The greeting to speak now.
  static String greeting() => greetingFor(DateTime.now(), userName);
}
