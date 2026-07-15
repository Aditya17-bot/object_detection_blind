/// BlindAssist — decision logic. Direct port of decision.py.
///
/// Pure logic: no camera, no model, no real clock. Takes the ObjectInfo list
/// for one frame plus a timestamp, and decides the ONE message worth speaking
/// right now — or nothing. The TTS layer only has to speak returned strings.
library;

import 'dart:math' as math;

import 'position.dart';

/// "very close" -> 3 ... "far" -> 0
final Map<String, int> _proxRank = {
  for (var i = 0; i < proximityLevels.length; i++)
    proximityLevels[proximityLevels.length - 1 - i]: i,
};

const Map<String, String> _sideWord = {
  'left': 'on left',
  'center': 'ahead',
  'right': 'on right',
};

/// What to say after a Find location: a rough "about N meters" for a medium/far
/// object when we have a TRUSTWORTHY metric estimate, otherwise the proximity
/// bucket. Meters require: a distance (known height, box not edge-clipped),
/// confidence >= nameConfidence (a misdetected class = wrong real-height =
/// confidently wrong meters), and medium/far range. Find-mode only — Walk
/// warnings stay short and bucket-based.
String _distanceOrBucket(ObjectInfo info) {
  final d = info.distanceM;
  if (d != null &&
      info.confidence >= nameConfidence &&
      (info.proximity == 'medium' || info.proximity == 'far')) {
    final m = math.max(1, d.round());
    return 'about $m meter${m != 1 ? 's' : ''}';
  }
  return info.proximity;
}

/// Below this confidence an obstacle warning says just "obstacle" instead of
/// the class name: COCO misnames lookalikes (dustbin->"toilet",
/// wardrobe->"refrigerator") and a wrong name costs the user's trust, while
/// the warning itself is still worth speaking. 0.8 chosen from clip probing:
/// known misnames scored 0.65-0.75, correct names >= 0.85.
const double nameConfidence = 0.8;

/// Classes from the DEDICATED custom model (door_dustbin_stairs), not COCO.
/// The nameConfidence gate exists only because COCO misnames lookalikes; these
/// have no lookalike to confuse, so their name is always trustworthy and must
/// bypass the gate — otherwise a real door at 0.5-0.79 conf is spoken as the
/// generic "obstacle" and the user thinks door detection failed.
const Set<String> trustedNameClasses = {'door', 'dustbin'};

String _cap(String text) => text[0].toUpperCase() + text.substring(1);

// ---------------------------------------------------------------------------
// Walk Mode
// ---------------------------------------------------------------------------

/// Is this detection worth warning about at all?
bool _relevantObstacle(ObjectInfo info) {
  if (!obstacleClasses.contains(info.name)) return false;
  if (info.proximity == 'far') return false;
  // medium-distance obstacles only matter when they are in the walking path
  if (info.proximity == 'medium' && info.hZone != 'center') return false;
  return true;
}

/// Sort key: closer wins, then more central, then bigger.
int _comparePriority(ObjectInfo a, ObjectInfo b) {
  final rank = _proxRank[a.proximity]!.compareTo(_proxRank[b.proximity]!);
  if (rank != 0) return rank;
  double centrality(ObjectInfo i) => 1 - 2 * (i.centerX - 0.5).abs();
  final c = centrality(a).compareTo(centrality(b));
  if (c != 0) return c;
  return a.area.compareTo(b.area);
}

/// The single obstacle Walk Mode should talk about, or null.
ObjectInfo? pickObstacle(List<ObjectInfo> infos) {
  ObjectInfo? best;
  for (final i in infos.where(_relevantObstacle)) {
    if (best == null || _comparePriority(i, best) > 0) best = i;
  }
  return best;
}

/// Which way to sidestep: the side with less obstacle mass on it.
String _freerSide(ObjectInfo chosen, List<ObjectInfo> infos) {
  var left = 0.0, right = 0.0;
  for (final i in infos) {
    if (identical(i, chosen) || !obstacleClasses.contains(i.name)) continue;
    if (i.centerX < 0.5) {
      left += i.area;
    } else {
      right += i.area;
    }
  }
  if (left != right) return left < right ? 'left' : 'right';
  // nothing else around: step away from the side the obstacle leans to
  return chosen.centerX >= 0.5 ? 'left' : 'right';
}

/// Spoken warning for the chosen obstacle. Short on purpose; vertical zone is
/// irrelevant for walking, so only left/ahead/right (or the clock bearing when
/// useClock) is spoken.
String walkMessage(ObjectInfo info,
    [List<ObjectInfo> allInfos = const [], bool useClock = false]) {
  final name = (trustedNameClasses.contains(info.name) ||
          info.confidence >= nameConfidence)
      ? info.name
      : 'obstacle';
  final side = useClock ? clockPhrase(info.centerX) : _sideWord[info.hZone]!;
  if (info.proximity == 'very close') {
    final String dodge;
    if (info.hZone == 'center') {
      dodge = _freerSide(info, allInfos);
    } else { // obstacle on a side: step to the other side
      dodge = info.hZone == 'left' ? 'right' : 'left';
    }
    return _cap('$name very close $side, move slightly $dodge');
  }
  // Walk stays short + bucket-based (no meters): the actionable token is the
  // direction, and metric range would only lengthen a continuous warning.
  return _cap('$name $side, ${info.proximity}');
}

// ---------------------------------------------------------------------------
// Find Mode
// ---------------------------------------------------------------------------

/// Best visible match for the asked-for class: biggest box wins.
ObjectInfo? findTarget(List<ObjectInfo> infos, String target) {
  ObjectInfo? best;
  for (final i in infos.where((i) => i.name == target)) {
    if (best == null || i.area > best.area) best = i;
  }
  return best;
}

String findMessage(ObjectInfo? info, String target, [bool useClock = false]) {
  if (info == null) return _cap('$target not visible');
  final where = useClock ? clockPhrase(info.centerX) : info.phrase;
  return _cap('${info.name} $where, ${_distanceOrBucket(info)}');
}

// ---------------------------------------------------------------------------
// Clear-path finder (innovation feature: "which way is open?")
// ---------------------------------------------------------------------------
// On demand (voice "clear path" / "which way"), report the emptiest of the
// three walking directions. Sums the box area of every near obstacle per
// horizontal third; the third with the least obstacle mass wins, straight
// ahead preferred on a tie. Coarse and cheap — reuses the ObjectInfo list.

const Map<String, String> _pathWord = {
  'center': 'Path clear ahead',
  'left': 'Clearest on your left',
  'right': 'Clearest on your right',
};

/// Spoken guidance toward the most open direction, or "Stop" if none is.
///
/// Each third is scored by its CLOSEST obstacle (proximity rank), not summed
/// box area — a nearby small hazard must outweigh a far bulky one. Doors are
/// excluded (a doorway is the thing to walk THROUGH), far obstacles ignored.
/// If even the emptiest third has a close/very-close obstacle we refuse to
/// call it clear and say to stop. Known limit: ObjectInfo carries only the box
/// center, so a wide object straddling thirds is scored in its center third.
String clearPath(List<ObjectInfo> infos) {
  final ranks = {'left': -1, 'center': -1, 'right': -1}; // -1 = nothing near
  for (final i in infos) {
    if (!obstacleClasses.contains(i.name) || i.name == 'door') continue;
    if (i.proximity == 'far') continue;
    final r = _proxRank[i.proximity]!;
    if (r > ranks[i.hZone]!) ranks[i.hZone] = r;
  }
  // emptiest third wins; center-first so ties resolve to "ahead"
  var best = 'center';
  for (final z in ['center', 'left', 'right']) {
    if (ranks[z]! < ranks[best]!) best = z;
  }
  if (ranks[best]! >= _proxRank['close']!) return 'Stop, no clear path';
  return _pathWord[best]!;
}

// ---------------------------------------------------------------------------
// Object memory (innovation feature: recall where a thing was last seen)
// ---------------------------------------------------------------------------
// A blind user often loses track of an object the moment it leaves the frame.
// The engine remembers the last sighting of every class and can answer "where
// is my cup?" — or volunteer "last seen on your right" the instant a Find
// target drops out of view. Coarse on purpose (zone + how-long-ago, never
// metric); a memory older than memoryTtl is treated as stale and forgotten.

const Map<String, String> _memWord = {
  'left': 'on your left',
  'center': 'ahead',
  'right': 'on your right',
};

String _agoPhrase(double seconds) {
  final s = seconds.round();
  if (s <= 1) return 'a moment ago';
  if (s < 60) return '$s seconds ago';
  final m = s ~/ 60;
  return '$m minute${m > 1 ? 's' : ''} ago';
}

/// Spoken memory of a class, or that there is none. [info] is the last
/// ObjectInfo seen for [name] (null if never/expired).
String recallMessage(ObjectInfo? info, double secondsAgo, String name,
    [bool useClock = false]) {
  if (info == null) {
    final article = 'aeiou'.contains(name[0]) ? 'an' : 'a';
    return _cap('no memory of $article $name');
  }
  final where = useClock ? clockPhrase(info.centerX) : _memWord[info.hZone]!;
  return _cap('$name last seen $where, ${_agoPhrase(secondsAgo)}');
}

// ---------------------------------------------------------------------------
// Scene summary (innovation feature: on-demand "describe")
// ---------------------------------------------------------------------------

const Map<String, int> _zoneOrder = {'center': 0, 'left': 1, 'right': 2};
const Map<String, String> _zoneWord = {
  'center': 'ahead',
  'left': 'on your left',
  'right': 'on your right',
};
const Map<String, String> _plurals = {'person': 'people'};

String _plural(String name) {
  final irregular = _plurals[name];
  if (irregular != null) return irregular;
  if (name.endsWith('s') || name.endsWith('sh') ||
      name.endsWith('ch') || name.endsWith('x')) {
    return '${name}es';
  }
  return '${name}s';
}

String _article(String name) => 'aeiou'.contains(name[0]) ? 'an' : 'a';

/// Spoken count of one class currently visible (voice: "how many chairs").
String countMessage(List<ObjectInfo> infos, String target) {
  final n = infos.where((i) => i.name == target).length;
  if (n == 0) return _cap('no ${_plural(target)}');
  if (n == 1) return _cap('1 $target');
  return _cap('$n ${_plural(target)}');
}

/// One sentence grouping everything visible, center first:
/// "A dining table ahead, 2 chairs on your left, a person on your right".
String summarizeScene(List<ObjectInfo> infos) {
  // (name, hZone) -> [count, biggest area]
  final groups = <String, List<num>>{};
  final keyName = <String, String>{}, keyZone = <String, String>{};
  for (final i in infos) {
    final key = '${i.name} ${i.hZone}';
    keyName[key] = i.name;
    keyZone[key] = i.hZone;
    final entry = groups.putIfAbsent(key, () => [0, 0.0]);
    entry[0] = (entry[0] as int) + 1;
    if (i.area > (entry[1] as double)) entry[1] = i.area;
  }
  if (groups.isEmpty) return 'Nothing detected';
  final ordered = groups.keys.toList()
    ..sort((a, b) {
      final z = _zoneOrder[keyZone[a]]!.compareTo(_zoneOrder[keyZone[b]]!);
      if (z != 0) return z;
      return (groups[b]![1] as double).compareTo(groups[a]![1] as double);
    });
  final parts = <String>[];
  for (final key in ordered) {
    final name = keyName[key]!, zone = keyZone[key]!;
    final count = groups[key]![0] as int;
    final what = count == 1 ? '${_article(name)} $name' : '$count ${_plural(name)}';
    parts.add('$what ${_zoneWord[zone]}');
  }
  return _cap(parts.join(', '));
}

// ---------------------------------------------------------------------------
// Stateful engine: what to say NOW (called once per frame)
// ---------------------------------------------------------------------------

/// Per-frame decision maker with anti-spam rules.
///
/// update(infos, now) -> message string to speak, or null. `now` is any
/// monotonic clock in seconds, so behaviour is identical and testable
/// everywhere.
class GuidanceEngine {
  final double repeatCooldown; // s before repeating same message
  final double minGap;         // s between any two messages
  final int persistence;       // frames a class must persist
  final double reminderInterval; // s between "still looking" reminders
  final double memoryTtl;      // s before a sighting goes stale

  bool useClock;               // clock bearings vs left/center/right

  Map<String, int> _streaks = {};
  final Map<String, (ObjectInfo, double)> _memory = {}; // name -> (info, time)
  String? _lastMsg;
  double? _lastTime;
  String? _lastObstacleName; // of last walk warning
  int? _lastObstacleRank;
  int _absent = 0;           // find mode: consecutive frames w/o target
  bool _saidNotVisible = false;
  double? _notVisibleTime;   // when "not visible"/reminder last said

  late String mode;
  String? target;

  GuidanceEngine({
    this.mode = 'walk',
    this.target,
    this.repeatCooldown = 3.0,
    this.minGap = 1.5,
    this.persistence = 2,
    this.reminderInterval = 10.0,
    this.memoryTtl = 30.0,
    this.useClock = true,
  }) {
    setMode(mode, target);
  }

  /// Toggle clock-face bearings (voice: "clock mode" / "zone mode").
  void setClock(bool on) => useClock = on;

  /// Switch walk/find (voice-command hook). Resets per-mode state but keeps
  /// the clock so minGap still applies across switches.
  void setMode(String newMode, [String? newTarget]) {
    if (newMode != 'walk' && newMode != 'find') {
      throw ArgumentError('unknown mode $newMode');
    }
    if (newMode == 'find' && (newTarget == null || newTarget.isEmpty)) {
      throw ArgumentError('find mode needs a target class');
    }
    mode = newMode;
    target = newTarget;
    _lastMsg = null;
    _lastObstacleName = null;
    _lastObstacleRank = null;
    _absent = 0;
    _saidNotVisible = false;
    _notVisibleTime = null;
  }

  // -- helpers --------------------------------------------------------------

  bool _clearToSpeak(String msg, double now, {bool urgent = false}) {
    if (_lastTime == null || urgent) return true;
    final elapsed = now - _lastTime!;
    if (elapsed < minGap) return false;
    if (msg == _lastMsg && elapsed < repeatCooldown) return false;
    return true;
  }

  String _speak(String msg, double now) {
    _lastMsg = msg;
    _lastTime = now;
    return msg;
  }

  // -- per-frame update -------------------------------------------------

  /// Store the most visible sighting of each class this frame, so object
  /// memory survives after things leave the frame.
  void _remember(List<ObjectInfo> infos, double now) {
    final best = <String, ObjectInfo>{};
    for (final i in infos) {
      final prev = best[i.name];
      if (prev == null || i.area > prev.area) best[i.name] = i;
    }
    best.forEach((name, info) => _memory[name] = (info, now));
  }

  /// Object-memory query: where [name] was last seen. Works in any mode
  /// (voice: "where is my cup?"). Stale memories (> memoryTtl) are gone.
  String recall(String name, double now) {
    final entry = _memory[name];
    if (entry == null || now - entry.$2 > memoryTtl) {
      return recallMessage(null, 0, name, useClock);
    }
    return recallMessage(entry.$1, now - entry.$2, name, useClock);
  }

  String? update(List<ObjectInfo> infos, double now) {
    // persistence is tracked per class name (not per zone) so an object keeps
    // its streak while the user walks and it drifts across zones; one-frame
    // misdetections never reach `persistence` and stay silent.
    final next = <String, int>{};
    for (final i in infos) {
      next[i.name] = (_streaks[i.name] ?? 0) + 1;
    }
    _streaks = next;
    _remember(infos, now);
    return mode == 'walk' ? _updateWalk(infos, now) : _updateFind(infos, now);
  }

  String? _updateWalk(List<ObjectInfo> infos, double now) {
    final obstacle = pickObstacle(infos);
    if (obstacle == null) {
      _lastObstacleName = null;
      _lastObstacleRank = null;
      return null;
    }
    if ((_streaks[obstacle.name] ?? 0) < persistence) return null;
    final rank = _proxRank[obstacle.proximity]!;
    // the same obstacle got closer since last warned -> safety overrides
    // every cooldown
    final urgent = _lastObstacleName == obstacle.name &&
        _lastObstacleRank != null &&
        rank > _lastObstacleRank!;
    final msg = walkMessage(obstacle, infos, useClock);
    if (!_clearToSpeak(msg, now, urgent: urgent)) return null;
    _lastObstacleName = obstacle.name;
    _lastObstacleRank = rank;
    return _speak(msg, now);
  }

  String? _updateFind(List<ObjectInfo> infos, double now) {
    final match = findTarget(infos, target!);
    if (match == null) {
      _absent += 1;
      if (_absent < persistence) return null; // flicker, not really gone
      if (_saidNotVisible) {
        // target still missing: remind periodically so long silence never
        // reads as "the app stopped working" (a blind user cannot glance
        // at the screen to check)
        if (now - _notVisibleTime! < reminderInterval) return null;
        final msg = _cap('still looking for $target');
        if (!_clearToSpeak(msg, now)) return null;
        _notVisibleTime = now;
        return _speak(msg, now);
      }
      // object memory: the instant the target drops out, say where it was —
      // turns a dead-end "not visible" into a lead to follow.
      final String msg;
      final entry = _memory[target!];
      if (entry != null && now - entry.$2 <= memoryTtl) {
        final info = entry.$1;
        final where = useClock ? clockPhrase(info.centerX) : _memWord[info.hZone]!;
        msg = _cap('$target not visible, last seen $where');
      } else {
        msg = findMessage(null, target!);
      }
      if (!_clearToSpeak(msg, now)) return null;
      _saidNotVisible = true;
      _notVisibleTime = now;
      return _speak(msg, now);
    }
    _absent = 0;
    if ((_streaks[target!] ?? 0) < persistence) return null;
    _saidNotVisible = false;
    final msg = findMessage(match, target!, useClock);
    if (!_clearToSpeak(msg, now)) return null;
    return _speak(msg, now);
  }

  /// On-demand scene summary; stamps the clock so the next walk/find message
  /// still respects minGap.
  String describe(List<ObjectInfo> infos, double now) =>
      _speak(summarizeScene(infos), now);

  /// On-demand clear-path guidance; stamps the clock like describe().
  String path(List<ObjectInfo> infos, double now) =>
      _speak(clearPath(infos), now);

  /// On-demand count of one class ("how many chairs"); stamps the clock.
  String count(List<ObjectInfo> infos, String target, double now) =>
      _speak(countMessage(infos, target), now);
}
