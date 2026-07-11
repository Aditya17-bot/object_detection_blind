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
FIND_CLASSES = {"bottle", "cup", "laptop", "cell phone", "book"}

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
}
_DEFAULT_THRESHOLDS = (0.35, 0.15, 0.05)

PROXIMITY_LEVELS = ("very close", "close", "medium", "far")


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
    return ObjectInfo(
        name=name,
        confidence=confidence,
        h_zone=h_zone,
        v_zone=v_zone,
        proximity=proximity_bucket(name, area),
        area=area,
        center_x=cx,
        phrase=direction_phrase(h_zone, v_zone),
    )
