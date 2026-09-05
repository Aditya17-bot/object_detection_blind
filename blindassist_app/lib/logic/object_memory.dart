/// Long-term object memory: "where did I leave my keys?"
/// Direct port of `object_memory.py` — see that file for the full reasoning.
///
/// [GuidanceEngine] already remembers where each class was last seen, but on a
/// 30-second timer and a monotonic clock, because it answers a different
/// question: "it just left the frame, which way do I turn". A user asking about
/// their keys means hours ago, possibly before the app was last closed.
///
/// So this store is separate, deliberately: **wall-clock** time so a memory
/// survives the process that made it, a **long horizon**, and **context**
/// rather than a frame position — "at 11 o'clock" is meaningless an hour later
/// once the user has moved, but "near a table" still is.
///
/// **Staleness is spoken first, and that is a safety decision.** A remembered
/// location is a claim about the past that the user acts on in the present, and
/// things move. "Keys near a table" invites a wasted trip; "Keys, about two
/// hours ago, near a table" lets them judge it themselves.
///
/// Pure: no clock of its own, no I/O, no model. The caller supplies the time
/// and owns the file.
library;

import 'dart:math' as math;

import 'position.dart';

/// Two objects this close (as a fraction of the frame diagonal) count as being
/// together. Generous on purpose: without depth we cannot say "on", only
/// "near", and a near-miss is a far cheaper error than silence.
const double kNearDistance = 0.28;

/// How long a sighting is worth reporting at all.
const double kMemoryTtl = 24 * 3600.0;

/// Cap on distinct classes held, so a long session cannot grow without bound.
const int kMaxEntries = 200;

const int _maxNear = 2;
const int _maxContext = 3;

/// One remembered observation of a class.
class Sighting {
  final String name;
  final String hZone;
  final double centerX;
  final double centerY;
  final String proximity;

  /// Things it was touching or beside.
  final List<String> near;

  /// Other things in the room at the time.
  final List<String> context;

  /// Epoch seconds.
  final double at;

  const Sighting({
    required this.name,
    required this.hZone,
    required this.centerX,
    required this.centerY,
    required this.proximity,
    this.near = const [],
    this.context = const [],
    this.at = 0,
  });

  Map<String, dynamic> toJson() => {
        'name': name,
        'h_zone': hZone,
        'center_x': centerX,
        'center_y': centerY,
        'proximity': proximity,
        'near': near,
        'context': context,
        'at': at,
      };

  static Sighting? fromJson(dynamic raw) {
    if (raw is! Map) return null;
    final name = raw['name'];
    if (name is! String || name.isEmpty) return null;
    double num_(dynamic v, double fallback) =>
        v is num ? v.toDouble() : fallback;
    List<String> strs(dynamic v) => v is List
        ? v.whereType<String>().toList()
        : const <String>[];
    return Sighting(
      name: name,
      hZone: raw['h_zone'] is String ? raw['h_zone'] as String : 'center',
      centerX: num_(raw['center_x'], 0.5),
      centerY: num_(raw['center_y'], 0.5),
      proximity:
          raw['proximity'] is String ? raw['proximity'] as String : 'medium',
      near: strs(raw['near']),
      context: strs(raw['context']),
      at: num_(raw['at'], 0),
    );
  }
}

double _distance(num ax, num ay, num bx, num by) {
  final dx = ax - bx, dy = ay - by;
  return math.sqrt(dx * dx + dy * dy);
}

/// How long ago, spoken and deliberately vague — precision here would be false
/// confidence. What the user needs is whether it is fresh enough to trust.
String agoPhrase(double seconds) {
  final s = math.max(0, seconds.round());
  if (s <= 1) return 'just now';
  if (s < 60) return '$s seconds ago';
  if (s < 3600) {
    final m = s ~/ 60;
    return '$m minute${m > 1 ? 's' : ''} ago';
  }
  if (s < 86400) {
    final h = (s / 3600).round();
    return 'about $h hour${h > 1 ? 's' : ''} ago';
  }
  final d = s ~/ 86400;
  return d == 1 ? 'yesterday' : '$d days ago';
}

String _article(String name) =>
    'aeiou'.contains(name[0].toLowerCase()) ? 'an' : 'a';

String _join(List<String> names) {
  if (names.isEmpty) return '';
  final parts = names.map((n) => '${_article(n)} $n').toList();
  if (parts.length == 1) return parts.first;
  return '${parts.sublist(0, parts.length - 1).join(', ')} and ${parts.last}';
}

/// The spoken answer to "where are my keys".
///
/// Age comes FIRST: the place is a claim about the past, and the age is what
/// tells the user how much to trust it. Buried at the end it arrives after they
/// have already decided to walk somewhere.
String recallSentence(Sighting? s, String name, double now) {
  if (s == null) return 'No memory of ${_article(name)} $name';
  final when = agoPhrase(now - s.at);
  final capped = name[0].toUpperCase() + name.substring(1);
  final String? where;
  if (s.near.isNotEmpty) {
    where = 'near ${_join(s.near)}';
  } else if (s.context.isNotEmpty) {
    where = 'with ${_join(s.context)} in view';
  } else {
    where = null;
  }
  return where == null ? '$capped, $when' : '$capped, $when, $where';
}

/// Where each class was last seen, with context, across sessions.
class ObjectMemory {
  ObjectMemory({
    this.ttl = kMemoryTtl,
    this.maxEntries = kMaxEntries,
    this.nearDistance = kNearDistance,
  });

  final double ttl;
  final int maxEntries;
  final double nearDistance;

  final Map<String, Sighting> _store = {};

  // -- writing ---------------------------------------------------------

  /// Record the most visible sighting of each class in this frame.
  void remember(List<ObjectInfo> infos, double at) {
    if (infos.isEmpty) return;
    final best = <String, ObjectInfo>{};
    for (final i in infos) {
      final cur = best[i.name];
      if (cur == null || i.area > cur.area) best[i.name] = i;
    }
    final present = best.values.toList()
      ..sort((a, b) => b.area.compareTo(a.area));

    best.forEach((name, info) {
      final near = <String>[];
      final context = <String>[];
      for (final o in present) {
        if (o.name == name) continue;
        final close =
            _distance(o.centerX, o.centerY, info.centerX, info.centerY) <=
                nearDistance;
        if (close && near.length < _maxNear) {
          near.add(o.name);
        } else if (!close && context.length < _maxContext) {
          context.add(o.name);
        }
      }
      _store[name] = Sighting(
        name: name,
        hZone: info.hZone,
        centerX: info.centerX,
        centerY: info.centerY,
        proximity: info.proximity,
        near: near,
        context: context,
        at: at,
      );
    });
    _evict(at);
  }

  void _evict(double at) {
    _store.removeWhere((_, s) => at - s.at > ttl);
    if (_store.length > maxEntries) {
      final oldest = _store.values.toList()
        ..sort((a, b) => a.at.compareTo(b.at));
      for (final s in oldest.take(_store.length - maxEntries)) {
        _store.remove(s.name);
      }
    }
  }

  // -- reading ---------------------------------------------------------

  /// The live sighting for [name], or null if absent or expired.
  Sighting? get(String name, double at) {
    final s = _store[name];
    if (s == null || at - s.at > ttl) return null;
    return s;
  }

  String recall(String name, double at) =>
      recallSentence(get(name, at), name, at);

  /// Classes currently remembered, most recent first.
  List<String> known(double at) {
    final live = _store.values.where((s) => at - s.at <= ttl).toList()
      ..sort((a, b) => b.at.compareTo(a.at));
    return live.map((s) => s.name).toList();
  }

  // -- persistence -----------------------------------------------------
  // The caller owns the file, so this stays pure and testable without a disk.

  Map<String, dynamic> toJson() => {
        'version': 1,
        'sightings': _store.values.map((s) => s.toJson()).toList(),
      };

  /// Replace the store from [toJson] output. Malformed entries are skipped
  /// rather than thrown on: a corrupt memory file must not stop the app.
  void loadJson(dynamic data, {double? at}) {
    if (data is! Map) return;
    final raw = data['sightings'];
    if (raw is! List) return;
    for (final entry in raw) {
      final s = Sighting.fromJson(entry);
      if (s != null) _store[s.name] = s;
    }
    if (at != null) _evict(at);
  }
}
