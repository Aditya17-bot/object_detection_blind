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
  // 'wardrobe' is not a COCO class and no model detects it: it exists so the
  // server's embedding naming head can replace YOLO's forced choice
  // ('refrigerator' at 0.84 for the user's white wardrobe) with the right word.
  'wardrobe',
  // 'laundry basket' is likewise namer-only. COCO's nearest words are
  // 'handbag' (not a target class, so invisible today) or 'suitcase' (warned,
  // wrong word). An obstacle because it is a waist-high object that lives on
  // the floor. User dimensions 2026-08-02: 0.85 m tall, 0.3 m wide.
  'laundry basket',
};

/// Small items a user searches for → Find Mode only, never obstacle warnings.
/// "toothbrush" is COCO class 79 (already in the model) — added so it can be a
/// Find / favorites-beacon target; small + often edge-clipped, so best-effort.
/// 'window' is likewise namer-only (YOLO calls one 'tv'). Deliberately a find
/// class, not an obstacle: a window is a landmark worth asking for, but
/// walking "into" one is not the hazard walk warnings exist for.
const Set<String> findClasses = {
  'bottle', 'cup', 'laptop', 'cell phone', 'book', 'toothbrush', 'window',
};

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
  // namer-only classes (no detector emits these; the server's index assigns
  // them, and RemoteDetector passes server names through verbatim)
  'wardrobe':     [0.40, 0.20, 0.08],
  'window':       [0.30, 0.12, 0.04],
  // taller than a suitcase but narrower, so a similar box area
  'laundry basket': [0.25, 0.10, 0.03],
  // small find-items
  'bottle':       [0.05, 0.015, 0.004],
  'cup':          [0.03, 0.010, 0.003],
  'cell phone':   [0.03, 0.010, 0.003],
  'book':         [0.05, 0.020, 0.006],
  'laptop':       [0.15, 0.060, 0.020],
  'toothbrush':   [0.03, 0.010, 0.003],
};
const List<double> _defaultThresholds = [0.35, 0.15, 0.05];

const List<String> proximityLevels = ['very close', 'close', 'medium', 'far'];

/// Rough monocular distance (meters) from a box's height via the pinhole model:
///   distance = realHeight * focal / boxHeightFraction
/// [cameraFocalNorm] is the vertical focal length as a fraction of frame
/// height (~1 / (2*tan(VFOV/2))); 0.85 suits a typical phone rear camera in
/// portrait. Single calibration knob — raise if meters read short, lower if
/// long. Coarse: only used for "about N meters" on medium/far objects.
const double cameraFocalNorm = 0.85;

/// Typical real vertical size (m) per class. Classes with an inconsistent or
/// usually edge-clipped extent (e.g. bed) are omitted → no meters, bucket used.
const Map<String, double> _realHeights = {
  'person': 1.7, 'chair': 0.9, 'couch': 0.8, 'dining table': 0.75,
  'bench': 0.85, 'toilet': 0.7, 'sink': 0.85, 'refrigerator': 1.7,
  'tv': 0.6, 'potted plant': 0.6, 'suitcase': 0.7, 'backpack': 0.5,
  'door': 2.0, 'dustbin': 0.6, 'wardrobe': 2.0, 'window': 1.2,
  'laundry basket': 0.85,
  'bottle': 0.25, 'cup': 0.1,
  'laptop': 0.20, 'book': 0.24, 'cell phone': 0.14, 'toothbrush': 0.19,
};

/// Rough distance in meters from a box's height (fraction of frame height).
/// null when the class has no known height, the box is degenerate, or the box
/// is edge-[clipped] — a clipped box has a truncated height the pinhole model
/// would read as "much farther" (dangerous: under-warns for the closest
/// objects), so we refuse to guess rather than mislead.
double? distanceMeters(String name, double heightFrac, {bool clipped = false}) {
  final real = _realHeights[name];
  if (real == null || heightFrac <= 0 || clipped) return null;
  return (real * cameraFocalNorm / heightFrac * 10).round() / 10.0;
}

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
  final double? distanceM; // rough meters (pinhole), null if not estimable

  /// True when the NAME is independently vouched for — a dedicated-model class
  /// (door/dustbin) or a committed rename from the embedding naming head. Such
  /// a name bypasses [nameConfidence], whose premise (that detector confidence
  /// predicts whether the WORD is right) is measurably false.
  final bool trustedName;

  /// With [centerX], tells whether two objects are NEAR each other, which is
  /// what lets the object memory say "keys near a table" instead of the much
  /// weaker "keys, with a table also in view".
  final double centerY;

  const ObjectInfo({
    required this.name,
    required this.confidence,
    required this.hZone,
    required this.vZone,
    required this.proximity,
    required this.area,
    required this.centerX,
    required this.phrase,
    this.distanceM,
    this.trustedName = false,
    this.centerY = 0.5,
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
/// so speaking bearings this way matches training people already have.
///
/// CORRECTED 2026-09-05 — mirror of position.py. The old mapping spread the
/// frame over 10-11-12-1-2, four hours = 120 degrees, across a camera that
/// sees ~65. Every bearing came out roughly DOUBLE the true angle: the right
/// frame edge sits at about +32 deg and was announced as "2 o'clock" (+60).
/// Clock mode is the default, so an O&M-trained traveller was being
/// systematically over-rotated.
///
/// The hour is now DERIVED from the field of view: one clock hour is 30
/// degrees, the frame spans [cameraFovDeg], 12 o'clock is dead ahead. At 65
/// deg that yields 11-12-1 and nothing wider — so clock bearings CANNOT be
/// finer than left/center/right at this FOV. The value is the VOCABULARY, not
/// extra angular resolution.
const double cameraFovDeg = 65.0;
const double _degreesPerHour = 30.0;

/// Horizontal position (0..1) -> clock hour, 12 = straight ahead.
int clockHour(double centerX) {
  final bearing = (centerX.clamp(0.0, 1.0) - 0.5) * cameraFovDeg;
  final hour = (bearing / _degreesPerHour).round();
  if (hour == 0) return 12;
  return hour > 0 ? hour : 12 + hour;
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
    double x2, double y2, double frameW, double frameH,
    {bool trustedName = false}) {
  final cx = (x1 + x2) / 2 / frameW;
  final cy = (y1 + y2) / 2 / frameH;
  final area = ((x2 - x1) * (y2 - y1)) / (frameW * frameH);
  final hZone = _zone(cx, _hZones);
  final vZone = _zone(cy, _vZones);
  // a box hugging the top or bottom edge is probably cut off → untrustworthy
  // height for the distance estimate
  final clipped = (y1 / frameH) <= 0.02 || (y2 / frameH) >= 0.98;
  return ObjectInfo(
    name: name,
    confidence: confidence,
    hZone: hZone,
    vZone: vZone,
    proximity: proximityBucket(name, area),
    area: area,
    centerX: cx,
    phrase: directionPhrase(hZone, vZone),
    distanceM: distanceMeters(name, (y2 - y1) / frameH, clipped: clipped),
    trustedName: trustedName,
    centerY: cy,
  );
}
