/// BlindAssist — position analysis. Direct port of position.py.
///
/// Pure logic, no camera and no model: takes bounding boxes as plain numbers,
/// returns direction labels and proximity buckets. Kept import-free so it is
/// unit-testable instantly, exactly like the Python original.
///
/// Coordinates are normalized 0..1 relative to frame size, x right, y down.
library;

/// Large things a blind user can bump into → Walk Mode warns about these.
/// door/dustbin come from the custom-trained model (not COCO). "stairs" is
/// deliberately NOT listed: 0.072 recall + high-confidence false positives
/// on walls/ceilings (user decision 2026-07-11).
const Set<String> obstacleClasses = {
  'person', 'chair', 'couch', 'bed', 'dining table', 'bench',
  'toilet', 'sink', 'refrigerator', 'tv', 'potted plant',
  'suitcase', 'backpack',
  'door', 'dustbin',
};

/// Small items a user searches for → Find Mode only, never obstacle warnings.
const Set<String> findClasses = {'bottle', 'cup', 'laptop', 'cell phone', 'book'};

final Set<String> targetClasses = {...obstacleClasses, ...findClasses};

const List<String> _hZones = ['left', 'center', 'right']; // x: thirds
const List<String> _vZones = ['top', 'middle', 'bottom']; // y: thirds

/// Proximity from box area as a fraction of frame area, per class:
/// [veryClose, close, medium] — below the last value means "far".
const Map<String, List<double>> _areaThresholds = {
  // big furniture / people
  'person':       [0.35, 0.15, 0.05],
  'chair':        [0.30, 0.12, 0.04],
  'bench':        [0.30, 0.12, 0.04],
  'couch':        [0.45, 0.20, 0.08],
  'bed':          [0.45, 0.20, 0.08],
  'dining table': [0.45, 0.20, 0.08],
  'refrigerator': [0.40, 0.20, 0.08],
  'toilet':       [0.30, 0.12, 0.04],
  'sink':         [0.25, 0.10, 0.03],
  'tv':           [0.30, 0.12, 0.04],
  // mid-size obstacles
  'suitcase':     [0.25, 0.10, 0.03],
  'backpack':     [0.20, 0.08, 0.025],
  'potted plant': [0.20, 0.08, 0.025],
  // custom-model classes
  'door':         [0.40, 0.20, 0.08],
  'dustbin':      [0.25, 0.10, 0.03],
  // small find-items
  'bottle':       [0.05, 0.015, 0.004],
  'cup':          [0.03, 0.010, 0.003],
  'cell phone':   [0.03, 0.010, 0.003],
  'book':         [0.05, 0.020, 0.006],
  'laptop':       [0.15, 0.060, 0.020],
};
const List<double> _defaultThresholds = [0.35, 0.15, 0.05];

const List<String> proximityLevels = ['very close', 'close', 'medium', 'far'];

/// Everything the decision logic needs about one detection.
class ObjectInfo {
  final String name;
  final double confidence;
  final String hZone;     // left / center / right
  final String vZone;     // top / middle / bottom
  final String proximity; // very close / close / medium / far
  final double area;      // box area as fraction of frame (0..1)
  final double centerX;   // 0..1, drives sonar panning
  final String phrase;    // human-friendly location, e.g. "top right"

  const ObjectInfo({
    required this.name,
    required this.confidence,
    required this.hZone,
    required this.vZone,
    required this.proximity,
    required this.area,
    required this.centerX,
    required this.phrase,
  });
}

String _zone(double value, List<String> zones) {
  if (value < 1 / 3) return zones[0];
  if (value < 2 / 3) return zones[1];
  return zones[2];
}

/// Short spoken location. Vertical is mentioned only when notable —
/// "chair middle left" is noise; "bottle top right" is useful.
String directionPhrase(String hZone, String vZone) {
  if (vZone == 'middle') {
    return hZone == 'center' ? 'center ahead' : hZone;
  }
  if (hZone == 'center') return '$vZone center';
  return '$vZone $hZone';
}

/// Clock-face bearing. Orientation & Mobility instructors teach blind
/// travelers to locate things by clock position ("your cup is at 2 o'clock"),
/// so speaking bearings this way matches training people already have. A
/// forward phone camera sees ~60-70 degrees, so the frame width maps to 10
/// through 2 o'clock, 12 straight ahead. Derived from centerX on demand.
const List<int> _clockHours = [10, 11, 12, 1, 2];

/// Horizontal position (0..1) -> clock hour in {10, 11, 12, 1, 2}.
int clockHour(double centerX) {
  final idx = (centerX * _clockHours.length).floor();
  return _clockHours[idx.clamp(0, _clockHours.length - 1)];
}

/// Spoken bearing, e.g. "at 2 o'clock".
String clockPhrase(double centerX) => "at ${clockHour(centerX)} o'clock";

String proximityBucket(String name, double area) {
  final t = _areaThresholds[name] ?? _defaultThresholds;
  if (area >= t[0]) return 'very close';
  if (area >= t[1]) return 'close';
  if (area >= t[2]) return 'medium';
  return 'far';
}

/// Convert one detection box (pixel coords) into an [ObjectInfo].
ObjectInfo analyzeBox(String name, double confidence, double x1, double y1,
    double x2, double y2, double frameW, double frameH) {
  final cx = (x1 + x2) / 2 / frameW;
  final cy = (y1 + y2) / 2 / frameH;
  final area = ((x2 - x1) * (y2 - y1)) / (frameW * frameH);
  final hZone = _zone(cx, _hZones);
  final vZone = _zone(cy, _vZones);
  return ObjectInfo(
    name: name,
    confidence: confidence,
    hZone: hZone,
    vZone: vZone,
    proximity: proximityBucket(name, area),
    area: area,
    centerX: cx,
    phrase: directionPhrase(hZone, vZone),
  );
}
