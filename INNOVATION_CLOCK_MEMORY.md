# Innovation features: Clock-face directions + Object memory

Added 2026-07-12. Two new guidance features, both implemented in the pure-logic
layer and mirrored identically in the Python prototype and the Flutter/Dart
port, so behaviour (and every spoken string) is proven equal on both by unit
tests.

## Why these two

The common assistive apps (Seeing AI, Google Lookout, Envision) already do
object detection + spoken labels + scene description. To bring genuine novelty
these two features target things those apps skip:

1. **Clock-face directions** — speak bearings the way Orientation & Mobility
   (O&M) instructors *already train* blind travelers: "your cup is at 2
   o'clock". Consumer apps say "on the right"; almost none use the clock
   convention the user has been taught in mobility lessons.
2. **Object memory** — remember where a thing was last seen so the app can lead
   the user back to it, instead of a dead-end "not visible". A sighted person
   glances back; a blind user cannot — the app holds that memory for them.

Both are deliberately **coarse** (zone / clock hour + vague "how long ago",
never metric distance), consistent with the project's no-fake-precision rule.

## 1. Clock-face directions

- `position.py` / `position.dart`: `clock_hour(center_x)` maps the horizontal
  position 0..1 to a clock hour in `{10, 11, 12, 1, 2}` (12 = straight ahead).
  A forward phone camera sees ~60-70°, so the visible frame width honestly maps
  to 10 through 2 o'clock — finer resolution than the 3 left/center/right zones.
  `clock_phrase(center_x)` → `"at 2 o'clock"`.
- Rendering is a toggle, off by default (existing zone wording unchanged):
  - Walk: `walk_message(info, all_infos, use_clock=True)` → "Chair at 10
    o'clock", "Person very close at 12 o'clock, move slightly left".
  - Find: `find_message(info, target, use_clock=True)` → "Bottle at 2 o'clock,
    close".
- `GuidanceEngine` holds `use_clock`; `set_clock(on)` flips it live.
- Controls: **Clock** button in the app UI, or voice "clock mode" / "zone mode".

## 2. Object memory

- `GuidanceEngine` keeps `_memory: {class_name -> (last ObjectInfo, time_seen)}`,
  updated every frame with the most-visible sighting of each class (runs in both
  walk and find mode).
- `recall(name, now)` → "Cup last seen on your right, 5 seconds ago" (or clock
  bearing when clock mode is on), or "No memory of a cup" when nothing was seen
  or the sighting is stale. Memories older than `memory_ttl` (default 30 s) are
  treated as gone, so it never recalls ancient info.
- Two ways it surfaces:
  - **Automatic** in Find mode: the instant the target drops out of view, the
    first "not visible" becomes "Bottle not visible, last seen on your left" —
    turning a dead end into a lead to follow. (If the target was never seen, it
    stays plain "not visible".)
  - **On demand**: voice "where is my cup" → spoken recall, in any mode.
- `recall_message(info, seconds_ago, name, use_clock)` is the pure formatter;
  `_ago_phrase()` gives "a moment ago" / "N seconds ago" / "N minutes ago".

## Voice grammar additions (`voice.py` / `voice_commands.dart`)

New grammar-constrained phrases (keeps Vosk accuracy high):
- `"clock mode"` → `("clock", None)`, `"zone mode"` → `("zones", None)`
- `"where is <object>"` / `"where is the <object>"` → `("recall", <coco class>)`,
  with the same synonym mapping as find ("where is my phone" → cell phone).

## App UI (`blindassist_app/lib/main.dart`)

- Bottom control row is now touch-complete so testing never depends on the mic:
  **Walk · Find… · Clock · Mute**. Active state shown on the button
  (`WALK ✓`, `FIND bottle ✓`, `Clock ✓`).
- **Find…** opens a large-tile picker (bottle, cup, cell phone, laptop, book,
  door, dustbin, chair, person).
- Gestures kept: tap = describe, double-tap = sonar, long-press = repeat last.
- Voice actions wired: clock/zones toggle, recall speaks the memory.

## Tests

All pure logic, no camera/mic needed. Mirrored 1:1 across both languages:
- Python: **78** tests pass (`test_position`, `test_decision`, `test_voice`,
  `test_speech`, `test_webapp`).
- Dart: **67** tests pass (`flutter test`); `flutter analyze` clean.
- New coverage: clock hour bands + phrases, clock rendering in walk/find, the
  engine clock toggle, `recall` (zone + clock + no-memory + expiry + unseen),
  and the enriched Find "last seen" message. Two prior find-mode tests were
  updated because "not visible" is now correctly enriched by memory when the
  target had just been seen.

## Not committed to git (regenerate locally)

Large derived/download artifacts stay out of the repo (see `.gitignore`), same
policy as the base weights and the Vosk model:
- `*.onnx`, `*_saved_model/`, `calibration_*.npy` — export-pipeline outputs.
- `blindassist_app/assets/models/*.tflite` + the bundled Vosk zip — regenerate
  from the export scripts / `.pt` model before building the app.
