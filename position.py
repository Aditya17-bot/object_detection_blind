"""BlindAssist — Phase 2: position analysis.

Pure logic, no camera and no model: takes bounding boxes as plain numbers,
returns direction labels and proximity buckets. Keeping this free of OpenCV/
YOLO imports means it can be unit-tested instantly and reused on mobile later.

Coordinates are normalized 0..1 relative to frame size, x right, y down.
"""

from dataclasses import dataclass

# Large things a blind user can bump into → Walk Mode warns about these.
# door/dustbin come from the user's custom-trained model
# (door_dustbin_stairs.pt, Colab 2026-07-11), not COCO. The model's third
# class "stairs" is deliberately NOT listed: 0.072 recall + high-confidence
# false positives on walls/ceilings (user decision 2026-07-11: skip stairs
# until retrained — re-enable by adding it here and in _AREA_THRESHOLDS).
OBSTACLE_CLASSES = {
    "person", "chair", "couch", "bed", "dining table", "bench",
    "toilet", "sink", "refrigerator", "tv", "potted plant",
    "suitcase", "backpack",
    "door", "dustbin",
}
# Small items a user searches for → Find Mode only, never obstacle warnings.
# "toothbrush" is COCO class 79 (already in the model) — added so it can be a
# Find / favorites-beacon target; small + often edge-clipped, so detection is
# best-effort.
FIND_CLASSES = {"bottle", "cup", "laptop", "cell phone", "book", "toothbrush"}

TARGET_CLASSES = OBSTACLE_CLASSES | FIND_CLASSES

# Frame thirds for the 3x3 grid.
_H_ZONES = ("left", "center", "right")        # x: 0-1/3, 1/3-2/3, 2/3-1
_V_ZONES = ("top", "middle", "bottom")        # y: same thirds

# Proximity from box area as a fraction of frame area. A "close" bottle is a
# far smaller box than a "close" person, so thresholds are per class:
# (very_close, close, medium) — below the last value means "far".
_AREA_THRESHOLDS = {
    # big furniture / people
    "person":       (0.35, 0.15, 0.05),
    "chair":        (0.30, 0.12, 0.04),
    "bench":        (0.30, 0.12, 0.04),
    "couch":        (0.45, 0.20, 0.08),
    "bed":          (0.45, 0.20, 0.08),
    "dining table": (0.45, 0.20, 0.08),
    "refrigerator": (0.40, 0.20, 0.08),
    "toilet":       (0.30, 0.12, 0.04),
    "sink":         (0.25, 0.10, 0.03),
    "tv":           (0.30, 0.12, 0.04),
    # mid-size obstacles
    "suitcase":     (0.25, 0.10, 0.03),
    "backpack":     (0.20, 0.08, 0.025),
    "potted plant": (0.20, 0.08, 0.025),
    # custom-model classes (door fills the frame like furniture;
    # dustbin is suitcase-sized)
    "door":         (0.40, 0.20, 0.08),
    "dustbin":      (0.25, 0.10, 0.03),
    # small find-items
    "bottle":       (0.05, 0.015, 0.004),
    "cup":          (0.03, 0.010, 0.003),
    "cell phone":   (0.03, 0.010, 0.003),
    "book":         (0.05, 0.020, 0.006),
    "laptop":       (0.15, 0.060, 0.020),
    "toothbrush":   (0.03, 0.010, 0.003),
}
_DEFAULT_THRESHOLDS = (0.35, 0.15, 0.05)

PROXIMITY_LEVELS = ("very close", "close", "medium", "far")

# Rough monocular distance (meters) from a box's height via the pinhole model:
#   distance = real_height * FOCAL / box_height_fraction
# FOCAL is the vertical focal length expressed as a fraction of the frame
# height (~1 / (2 * tan(VFOV/2))); 0.85 suits a typical phone rear camera in
# portrait. It is the single calibration knob — raise it if meters read
# consistently short, lower it if long. Deliberately coarse: only used to say
# "about N meters" for medium/far objects; near objects keep the area buckets.
CAMERA_FOCAL_NORM = 0.85

# Typical real vertical size (m) per class. Classes whose vertical extent is
# inconsistent or usually edge-clipped (e.g. bed) are omitted → no meters, the
# proximity bucket is spoken instead.
_REAL_HEIGHTS = {
    "person": 1.7, "chair": 0.9, "couch": 0.8, "dining table": 0.75,
    "bench": 0.85, "toilet": 0.7, "sink": 0.85, "refrigerator": 1.7,
    "tv": 0.6, "potted plant": 0.6, "suitcase": 0.7, "backpack": 0.5,
    "door": 2.0, "dustbin": 0.6, "bottle": 0.25, "cup": 0.1,
    "laptop": 0.20, "book": 0.24, "cell phone": 0.14, "toothbrush": 0.19,
}


def distance_meters(name, height_frac, clipped=False):
    """Rough distance in meters from a box's height (fraction of frame height).
    None when the class has no known height, the box is degenerate, or the box
    is edge-CLIPPED — a clipped box has a truncated height, which the pinhole
    model would read as "much farther" (dangerous: it under-warns for the
    closest objects), so we refuse to guess rather than mislead."""
    real = _REAL_HEIGHTS.get(name)
    if real is None or height_frac <= 0 or clipped:
        return None
    return round(real * CAMERA_FOCAL_NORM / height_frac, 1)


@dataclass
class ObjectInfo:
    """Everything the decision logic (Phase 3) needs about one detection."""
    name: str
    confidence: float
    h_zone: str          # left / center / right
    v_zone: str          # top / middle / bottom
    proximity: str       # very close / close / medium / far
    area: float          # box area as fraction of frame (0..1)
    center_x: float      # 0..1, for sonar panning later
    phrase: str          # human-friendly location, e.g. "top right"
    distance_m: float = None  # rough meters (pinhole), None if not estimable


def _zone(value, zones):
    if value < 1 / 3:
        return zones[0]
    if value < 2 / 3:
        return zones[1]
    return zones[2]


def direction_phrase(h_zone, v_zone):
    """Short spoken location. Vertical is mentioned only when notable —
    'chair middle left' is noise; 'bottle top right' is useful."""
    if v_zone == "middle":
        return "center ahead" if h_zone == "center" else h_zone
    if h_zone == "center":
        return f"{v_zone} center"
    return f"{v_zone} {h_zone}"


# Clock-face bearing. Orientation & Mobility instructors teach blind travelers
# to locate things by clock position ("your cup is at 2 o'clock"), so speaking
# bearings this way matches training people already have. A forward phone camera
# sees roughly a 60-70 degree cone, so the visible frame width maps to 10
# through 2 o'clock, 12 straight ahead — finer than the 3 left/center/right
# zones. Derived from center_x on demand; not stored on ObjectInfo.
_CLOCK_HOURS = (10, 11, 12, 1, 2)


def clock_hour(center_x):
    """Horizontal position (0..1) -> clock hour in {10, 11, 12, 1, 2}."""
    idx = min(int(center_x * len(_CLOCK_HOURS)), len(_CLOCK_HOURS) - 1)
    return _CLOCK_HOURS[idx]


def clock_phrase(center_x):
    """Spoken bearing, e.g. 'at 2 o'clock'."""
    return f"at {clock_hour(center_x)} o'clock"


def proximity_bucket(name, area):
    very_close, close, medium = _AREA_THRESHOLDS.get(name, _DEFAULT_THRESHOLDS)
    if area >= very_close:
        return "very close"
    if area >= close:
        return "close"
    if area >= medium:
        return "medium"
    return "far"


def analyze_box(name, confidence, x1, y1, x2, y2, frame_w, frame_h):
    """Convert one detection box (pixel coords) into an ObjectInfo."""
    cx = (x1 + x2) / 2 / frame_w
    cy = (y1 + y2) / 2 / frame_h
    area = ((x2 - x1) * (y2 - y1)) / (frame_w * frame_h)
    h_zone = _zone(cx, _H_ZONES)
    v_zone = _zone(cy, _V_ZONES)
    # a box hugging the top or bottom edge is probably cut off → its height is
    # untrustworthy for the distance estimate
    clipped = (y1 / frame_h) <= 0.02 or (y2 / frame_h) >= 0.98
    return ObjectInfo(
        name=name,
        confidence=confidence,
        h_zone=h_zone,
        v_zone=v_zone,
        proximity=proximity_bucket(name, area),
        area=area,
        center_x=cx,
        phrase=direction_phrase(h_zone, v_zone),
        distance_m=distance_meters(name, (y2 - y1) / frame_h, clipped),
    )
