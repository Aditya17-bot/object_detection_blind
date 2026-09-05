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
const String _kLocaleKey = 'tts_locale';
const String _kMemoryKey = 'object_memory';

/// Spoken-accent choices, as BCP-47 locales the Android TTS engine understands.
///
/// This is a LOCALE list rather than a list of specific voice names on purpose:
/// which voices are installed differs per phone and per Google TTS version, so
/// a hardcoded voice name would silently fall back to the default on any device
/// that lacks it. The app asks the engine for the locale and lets it choose its
/// best matching voice, then offers whatever concrete voices it does have.
const Map<String, String> kAccents = {
  'en-IN': 'Indian English',
  'en-GB': 'British English',
  'en-US': 'American English',
  'en-AU': 'Australian English',
  'en-IE': 'Irish English',
  'en-ZA': 'South African English',
};

/// British English by default (user choice, 2026-09-05, after hearing them all
/// side by side on the device). Overridden by whatever the user last picked in
/// the features page; this only decides what a fresh install speaks with.
const String kDefaultLocale = 'en-GB';

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

  /// BCP-47 locale for the spoken voice. See [kAccents].
  static String ttsLocale = kDefaultLocale;

  static Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final stored = prefs.getString(_kNameKey);
      if (stored != null && stored.trim().isNotEmpty) {
        userName = stored.trim();
      }
      final loc = prefs.getString(_kLocaleKey);
      if (loc != null && loc.trim().isNotEmpty) {
        ttsLocale = loc.trim();
      }
    } catch (_) {
      // keep the default; startup is not worth failing over a preference
    }
  }

  /// The object memory, as the JSON string `ObjectMemory.toJson` produces.
  ///
  /// SharedPreferences rather than a file: the store is capped at a couple of
  /// hundred small records, so it is tens of kilobytes at worst, and this keeps
  /// it in the same place as every other persisted setting with no new
  /// dependency. A failed read returns null and the app starts with an empty
  /// memory, which is the correct degradation — an unreadable memory must
  /// never stop the camera coming up.
  static Future<String?> loadMemoryJson() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_kMemoryKey);
    } catch (_) {
      return null;
    }
  }

  static Future<void> saveMemoryJson(String json) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kMemoryKey, json);
    } catch (_) {}
  }

  static Future<void> setTtsLocale(String locale) async {
    ttsLocale = locale;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kLocaleKey, locale);
    } catch (_) {}
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
