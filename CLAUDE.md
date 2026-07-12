# BlindAssist — Object Guidance App for Visually Impaired Users

## What this project is

A student project: a camera-based assistive app that detects common indoor
objects, estimates their rough direction in the frame, and speaks short guidance
messages. It is NOT a full navigation system — no depth in meters, no 3D
mapping, no face recognition.

Target classes (expanded 2026-07-09 after real-room testing showed the original
5 were too narrow; defined in `position.py`, single source of truth):
- **OBSTACLE_CLASSES** (Walk Mode warns): person, chair, couch, bed,
  dining table, bench, toilet, sink, refrigerator, tv, potted plant,
  suitcase, backpack
- **FIND_CLASSES** (Find Mode only, never obstacle warnings): bottle, cup,
  laptop, cell phone, book
- **Doors are NOT in COCO** — user asked about other models / self-training.
  Options discussed but NOTHING downloaded/trained yet — user explicitly wants
  to be asked before any model download or training. See "Door detection" below.

Pipeline: **Camera feed → Object detection (YOLOv8n) → Position analysis →
Decision logic → Voice output (TTS)**

## FINAL PRODUCT REQUIREMENT (user decision 2026-07-11 — a MUST)

After the user delivers the door/stairs/dustbin model, this becomes an
**Android app**. Non-negotiables the user stated:
- Android app is a must (not just the web UI on a phone).
- **Minimal interface** — users are blind, they can't see the screen.
- **Voice input controls everything** — users can't type; speech + sonar
  are the outputs. The current web UI is fine as the dev/demo tool.
Implication for design work now: keep ALL logic in the pure-Python modules
(position/decision/voice parsing) so the port swaps only camera/TTS/STT
layers. Full plan in **`ANDROID_PLAN.md`** (2026-07-11): Flutter +
TFLite-exported yolov8n + custom model, vosk_flutter (same speech model),
flutter_tts, phases A0-A6. Not started yet.

## Two modes

- **Walk Mode**: continuous obstacle awareness. Announces only the single most
  relevant object per moment, e.g. "Obstacle ahead", "Chair on right",
  "Obstacle left, move slightly right". Priority: large/center obstacles first.
- **Find Mode**: user asks for one object class (e.g. "bottle"); app announces
  its rough location ("Bottle top right") or "Target not visible". If multiple
  matches, pick the closest/most visible one.

## Key design decisions

- **Position**: frame divided into a 3×3 grid (left/center/right × top/middle/bottom)
  using the bounding-box center point.
- **Proximity**: approximated from bounding-box area relative to frame area —
  categories: very close / close / medium / far. Deliberately NOT metric distance.
- **Speech**: intentionally short phrases; never read out every detection.
  Avoid repeating the same announcement every frame (needs cooldown/debounce logic).

## Chosen innovation features (user picked 2026-07-09)

1. **Sonar audio mode** — with earphones, obstacles produce stereo-panned beeps
   (left/right matches direction) that tick faster and rise in pitch as the
   obstacle gets closer. Parking-sensor-for-walking. Speech still used for names.
2. **Voice commands** — offline speech recognition (Vosk) for "find bottle",
   "walk mode", "describe" etc. Hands-free operation.
3. **Smart scene summary** — on-demand spoken overview that groups and counts:
   "A table ahead with two chairs, a person on your right."
4. **Clock-face directions** (added 2026-07-12) — speak bearings the O&M way
   ("bottle at 2 o'clock"); frame width maps to 10-11-12-1-2 o'clock, 12 ahead.
   Toggle (default off): Clock button / voice "clock mode" / "zone mode".
5. **Object memory** (added 2026-07-12 — user reversed the earlier "not
   selected" call) — engine remembers each class's last sighting (zone +
   how-long-ago, stale after 30 s). Auto: Find "not visible" becomes "last seen
   on your left"; on-demand: voice "where is my cup". Full write-up in
   **`INNOVATION_CLOCK_MEMORY.md`**.

Both #4 and #5 live in the pure-logic layer and are mirrored 1:1 in Python and
the Dart port (Python 78 tests / Dart 67 tests, all passing).

## Tech stack

- Python prototype (desktop first, webcam as camera stand-in)
- OpenCV for camera capture and frame handling
- Ultralytics YOLOv8 **Small** (`yolov8s.pt`, pre-trained on COCO — all target
  classes are COCO classes; "table" maps to COCO "dining table").
  Decision 2026-07-09 after n-vs-s comparison (`compare_models.py`): user found
  nano's detections unconvincing; yolov8s @ conf 0.6 gave person 0.86–0.93 with
  no false positives, ~139 ms/frame (~7 FPS) on this machine vs nano's ~78 ms.
  `--model yolov8n.pt` flag remains as a speed fallback.
  Known limits explained to user: COCO = 80 classes only (no watch, no hand);
  perfume bottle ≠ COCO "bottle". Dim-room webcam noise lowers confidence —
  lighting matters for the test protocol.
- pyttsx3 for offline TTS (note: pyttsx3 blocks — run speech in a separate thread)
- Future (out of scope for prototype): Flutter/Android port, voice command input

## Project status / plan

- [x] Concept & spec written (see conversation history / project description)
- [x] Phase 1: webcam + YOLOv8n detection loop with drawn boxes (`phase1_detect.py`).
      Verified 2026-07-09: bus.jpg sample → 3 persons @ 0.83–0.87; live webcam
      headless test → person detected @ ~0.86, ~3.3 FPS avg incl. model warmup.
      Deps installed in `venv/` (python 3.9). Test images land in `test_output/`.
- [x] Phase 2: position analysis (3×3 grid) + proximity buckets. Done 2026-07-09.
      `position.py` = pure logic (no cv2/YOLO imports — reusable + unit-testable):
      `analyze_box()` → ObjectInfo(name, conf, h_zone, v_zone, proximity, area,
      center_x for future sonar panning, spoken phrase). Per-class area
      thresholds in `_AREA_THRESHOLDS`. Phrase rule: vertical zone spoken only
      when not "middle" ("left", "center ahead", "top right").
      `test_position.py` = 13 unit tests, all passing (`python -m unittest`).
      `phase2_detect.py` = live demo w/ grid overlay + proximity-colored boxes;
      verified on bus.jpg (4 persons, correct zones) and live webcam.
- [x] Class expansion (2026-07-09): OBSTACLE_CLASSES / FIND_CLASSES split added
      to position.py with per-class area thresholds for all 18 classes;
      phase1_detect.py now imports TARGET_CLASSES from position.py.
      All 13 unit tests still pass.
- [x] Phase 3: decision logic. Done 2026-07-11. `decision.py` = pure logic
      (no cv2/YOLO, injected clock — same philosophy as position.py):
      • Walk Mode: `pick_obstacle()` — relevance filter (far never announced;
        medium only when in the center walking path), priority = proximity
        rank, then centrality, then area. `walk_message()` spec wording:
        "Chair on right", "Person ahead", very close adds sidestep advice
        toward the freer side ("...move slightly left").
      • Find Mode: `find_target()` biggest match wins; "Bottle top right,
        close" / "Bottle not visible" (said once, re-armed when it reappears).
      • `summarize_scene()` = smart scene summary feature ("A dining table
        ahead, 2 chairs on your left, a person on your right").
      • `GuidanceEngine.update(infos, now)` → one message or None. Anti-spam:
        2-frame persistence (kills one-frame misdetections), 3 s repeat
        cooldown, 1.5 s min gap, escalation override (same obstacle got
        closer → speaks immediately). `set_mode()` ready for voice commands.
      `test_decision.py` = 23 unit tests (36 total, all passing).
      `phase3_detect.py` = demo; recorded clips use video-time (frame/fps) so
      cooldowns are reproducible; logs announcements to `test_output/*.log` +
      saves an annotated frame per announcement; `d` key = describe scene.
      Verified on all 4 clips (see "Phase 3 recorded-video results" below).
- [x] Phase 4: TTS output. Done 2026-07-11. `speech.py` = `Speaker` class:
      pyttsx3 on its own daemon thread (engine created ON the worker thread —
      pyttsx3 is not thread-safe), `say()` never blocks the camera loop, and
      only the LATEST pending message is kept (a new announcement REPLACES a
      waiting one — stale guidance is never spoken). Engine factory is
      injectable → `test_speech.py` = 4 unit tests with a fake engine, no
      sound (40 tests total, all passing). Real pyttsx3 smoke-tested aloud.
      `phase4_assist.py` = the full assistant (camera → YOLO → position →
      decision → speech), same flags as phase3 plus `--rate` and `--mute`;
      `d` key speaks the scene summary. Verified end-to-end on the couch
      clip: spoken "Couch ahead" ×3 (3 s repeat cooldown, real-time clock) →
      "Couch very close ahead, move slightly right" (escalation).
      NOTE: phase4 uses real time even for clips (speech is real-time);
      phase3 --headless remains the reproducible video-time test harness.
- [x] Phase 5: testing & evaluation — MOSTLY DONE 2026-07-11, full report in
      **`EVALUATION.md`** (headline: direction accuracy 100% of reviewed
      announcement keyframes, 0 phantom announcements, 5.8 FPS / 172 ms
      avg on this laptop, 40/40 unit tests). User filmed 3 requested eval
      clips (in `test_output/`): eval_a = walk toward/between obstacles
      (star result: flanking medium chairs stay silent, center wardrobe
      announced + escalates), eval_b = find dark thermos (missed in dim
      light 07-09, found fine in good light), eval_c = cluttered desk
      (walk mode correctly silent; find picks real bottle from clutter;
      scene summary mixed — notebook→"laptop", window→"tv").
      Wrong-name pattern confirmed: dustbin→toilet, wardrobe→refrigerator,
      desk→chair — warnings always behaviorally correct though.
      STILL OPEN for phase 5: live protocol test with phone stream
      (needs user, ~15 min; user asked 2026-07-11 whether the same room
      works — yes, nothing is trained on it; one extra room is a bonus).
      Generic-"obstacle" naming IMPLEMENTED 2026-07-11 (user request):
      walk warnings below `decision.NAME_CONFIDENCE` say "obstacle"
      instead of the class name. Probe finding: known misnames scored
      0.65-0.75, correct names ≥0.85 (dustbin-toilet 0.65-0.72,
      wardrobe-refrigerator 0.72-0.75). Threshold was 0.7 (user's first
      pick), then decision.py was set to 0.8 on 2026-07-11 morning (edit
      matches the probe recommendation); tests/docs aligned to 0.8 the
      same day.
- [x] Frontend: web UI DONE 2026-07-11 — `webapp.py` (Flask) + `templates/`
      + `static/`. Live MJPEG annotated video, Walk/Find controls + target
      picker, describe button, mute + voice-rate slider, live announcement
      feed (aria-live for screen readers), status pills (source/model/FPS).
      Includes **sonar audio mode** (innovation feature #1) implemented in
      the BROWSER with WebAudio: stereo pan from ObjectInfo.center_x,
      tick rate + pitch rise with proximity (medium 700ms/494Hz → very
      close 160ms/880Hz), earphones recommended. No new Python audio dep.
      `test_webapp.py` = 8 route/validation tests against a fake engine.
      Run: `python webapp.py [--source ...]` → http://127.0.0.1:5000.
      Clips loop forever in the web UI (demo behavior; phase3 --headless
      stays the reproducible eval harness).
- [x] Voice commands (innovation feature #2) DONE 2026-07-11, user approved
      the model download the same day. `voice.py`: `parse_command()` = pure
      logic ("please find the bottle" → ("find","bottle"), synonyms
      phone/fridge/sofa/table/plant/bag mapped to COCO names) +
      `VoiceListener` (mic → Vosk offline STT on a daemon thread,
      GRAMMAR-CONSTRAINED to our phrases for accuracy; mic/model failures
      land in .error, never crash). Model: `vosk-model-small-en-us-0.15/`
      (~40 MB, in project root, synced to Drive). Wired into webapp.py:
      spoken confirmation ("Finding bottle"), voice status pill in the UI,
      `--no-voice` flag. Sonar now tracks the FIND TARGET in find mode
      (beeps lead the user to the object; far target still ticks at level
      1). `test_voice.py` = 8 parser tests → 58 tests total, all passing.
      Verified live 2026-07-11: webcam + voice active at 6.3 FPS.
- [x] Phone testing support (2026-07-11, user found laptop testing awkward):
      `--host 0.0.0.0` (prints the LAN URL for the phone; needs the Windows
      firewall Allow prompt on first run) + "Speak on this device" toggle
      (V key) — browser speechSynthesis speaks announcements on the PHONE,
      with speechSynthesis.cancel() before each so stale guidance is never
      spoken (same rule as speech.py). Setup: IP Webcam as --source, phone
      browser opens laptop:5000, laptop voice muted. Verified via LAN-IP
      curl; NOT yet walked with a real phone (that's the user's live
      protocol test). Full mobile app port (Flutter) remains future work —
      out of prototype scope, web UI on the phone covers the demo.

## Testing approach (agreed)

1. **Model sanity tests** — run YOLOv8n on static test images of the 5 target
   classes; verify labels and boxes visually.
2. **Unit tests (no camera needed)** — position-analysis and decision-logic
   functions take plain bounding-box data, so test them with synthetic boxes:
   e.g. box centered at (0.1, 0.5) of frame → must return "left".
3. **Recorded-video tests** — process short pre-recorded walkthrough clips so
   results are reproducible; log announcements per frame and review.
4. **Live protocol tests** — place objects at known positions (left/center/right,
   near/far), walk toward them, check spoken output correctness and timing.
5. **Metrics to report**: direction accuracy (%), detection confidence threshold
   chosen (start ~0.5), FPS on the dev machine, announcement latency, and
   false/missed announcement counts from the video tests.

## Phone-camera testing (agreed 2026-07-09)

Testing with a laptop webcam is awkward — user tests with their phone as the
camera instead, laptop still does detection + speech:
- **Live**: "IP Webcam" Android app → phone on same Wi-Fi → server gives
  `http://<phone-ip>:8080`; run scripts with `--source http://<ip>:8080/video`.
  All stream scripts must accept http/https/rtsp URLs (phase2 fixed for this;
  phase1 already passed the raw string through).
- **Repeatable**: record walkthrough clips on the phone, run `--source clip.mp4`.
  DONE 2026-07-10: 4 WhatsApp clips in `test_output/` (bedroom walkthrough,
  couch, dustbin, dark room w/ suitcase+chair). Phase 2 pipeline run on all
  (results in "Recorded-video test results" below).
- Stream verified working 2026-07-09 (bottles detected in user's bedroom at
  1080p; suggested user drop app resolution to 720p). NOTE: the hotspot IP
  (was `http://10.150.139.58:8080`) changes between hotspot sessions — always
  ask for the current URL shown in the IP Webcam app; a dead IP gives
  "Connection to tcp://... failed" from cv2.
- Real-room findings: Dettol bottle detected as bottle (good generalization);
  black thermos flask missed (dark-on-dark + frame edge cutoff); bed/suitcase
  seen by model but were filtered before class expansion → led to the expanded
  class list above.

## Recorded-video test results (2026-07-10, yolov8s @ conf 0.6)

Phase 2 run on the 4 clips in `test_output/`; annotated keyframes saved as
`test_output/clipN_frameXXXX.jpg`. **All zone + proximity labels visually
correct** — remaining errors are model classification, not position logic:
- Bedroom clip: bed/chair/suitcase/bottle/laptop all detected w/ correct zones.
  One misdetection: wall calendar labeled "laptop".
- Couch clip: couch "center ahead, close" — correct. Doors in frame ignored
  (expected, not COCO).
- Dustbin clip: blue dustbin consistently detected as **"toilet"** — dustbin is
  not a COCO class. Position/proximity still right, and "toilet" is in
  OBSTACLE_CLASSES so Walk Mode would still warn (wrong name, right behavior).
  Candidate for the same future fine-tune as doors (user confirmed 2026-07-10:
  fine-tuning deferred until after core phases).
- Dark/blurry clip: maroon suitcase misread as "cell phone, very close";
  upside-down chair on table missed entirely. Confirms lighting/motion-blur
  limits already noted — worth a sentence in the report.

## Phase 3 recorded-video results (2026-07-11, walk mode unless noted)

Announcement logs in `test_output/phase3_*.log`, one annotated jpg saved per
announcement. Behavior correct on all 4 clips — sparse, one-at-a-time,
sensible messages (e.g. bedroom clip: 8 announcements across 471 frames):
- Bedroom: bed tracked around the room, "Bed very close ahead, move slightly
  right" etc.; chair/bottle/laptop present but correctly outranked by the bed.
- Bedroom find-mode (`--target bottle`): "not visible" once → location updates
  as camera moves ("Bottle top right, close" → "left, medium") → "not
  visible" once when it exits. Exactly per spec.
- Couch: "Couch ahead" → escalates "very close, move slightly right".
- Dustbin: "Toilet ahead" (known COCO name limit; warning itself correct).
- Dark clip: big dark cupboard read as "refrigerator very close on left" —
  wrong name, correct warning (same story as dustbin; fine for prototype).

## Door detection (open question — ASK USER before downloading/training anything)

Doors are not a COCO class. Options laid out for the user:
1. Skip for prototype, list as future work (original spec already does).
2. Fine-tune YOLOv8s on a public door dataset (e.g. Roboflow door datasets) —
   free Colab GPU, student-feasible, great report material. Recommended path
   if they want it, AFTER phases 3–5 are done.
3. Second pre-trained model covering doors (e.g. Open Images-based) — quality
   varies, adds a second inference pass. Not recommended.
User said "let me know before training or getting it" — treat any dataset/model
download or training run as requiring explicit user approval first.

INTEGRATED 2026-07-11: user trained `door_dustbin_stairs.pt` on Colab
(classes {0: door, 1: dustbin, 2: stairs}, 6.2 MB nano) and it is now wired
in: position.py has the 3 classes in OBSTACLE_CLASSES + thresholds;
webapp.py auto-loads the file when present (`--extra-model`, conf
`--extra-conf` 0.5) and merges both models' detections before position
analysis. 60 tests pass. Clip validation: DOORS excellent (couch clip:
open doorway boxed correctly, best conf 0.91, 55 hits/52 frames; sample
frames test_output/custom_*.jpg). DUSTBIN weak on the old blue-dustbin
clip (3 frames, max 0.58) but user reports GREAT live results — old clip
was the outlier, dustbin stays enabled. STAIRS SKIPPED (user decision
2026-07-11): training recall was 0.072 with high precision, and live
probing showed high-conf (0.68-0.91) false positives on the user's
wall/ceiling — removed from OBSTACLE_CLASSES/_AREA_THRESHOLDS (comment in
position.py explains how to re-enable after retraining with
room-background negatives). Voice commands CONFIRMED WORKING live by the
user this session ("find door" etc.) — the earlier walk-test failure did
not recur; root cause never pinned down (suspect: speaking while TTS was
talking / distance from mic). Find-mode UX gap FIXED 2026-07-12: after
"not visible", GuidanceEngine now says "Still looking for X" every
`reminder_interval` (default 10 s) until the target reappears — so long
silence never reads as "the app died". Implemented identically in
decision.py AND the Dart port (decision.dart); tests updated in both
(64 Python / 52 Dart tests, all passing).

## Android app status (2026-07-12 — phases A0-A5 CODED, see ANDROID_PLAN.md)

`blindassist_app/` (Flutter) exists and is feature-complete in code:
- A0 done: yolov8n + door_dustbin_stairs exported to TFLite (fp32, in
  `blindassist_app/assets/models/` along with the Vosk model zip).
- A1-A5 done in code: `lib/detector.dart` (both TFLite models, YUV420
  rotation-aware preprocessing, per-class NMS, same conf thresholds as
  webapp.py), `lib/logic/` = direct ports of position/decision/voice
  parsing, `lib/speaker.dart` (flutter_tts, stop-before-speak),
  `lib/sonar.dart`, `lib/voice_listener.dart` (vosk_flutter, same
  grammar). Ports covered by 52 Dart tests (mirrors of the Python ones).
- A6 partial: gestures in main.dart (tap=describe, double-tap=sonar
  toggle, long-press=repeat last); TalkBack semantics + volume-key mute
  still open.
- A6 UI (2026-07-12): touch-complete control row so testing needs no mic —
  Walk / Find… / Clock / Mute, active state on the button; Find… opens a
  big-tile target picker.
- Innovation features #4 (clock-face directions) + #5 (object memory) added
  2026-07-12 in both Python and Dart — see `INNOVATION_CLOCK_MEMORY.md`.
  Dart tests now 67 (was 52).
- Gradle compat fix in `android/build.gradle.kts`: injects the missing
  `namespace` into old plugins (vosk_flutter 0.3.48 predates AGP 8) via
  reflection — don't remove it or release builds break.
- Phone (Galaxy S20 FE, RZCR906FDTD) authorized over USB 2026-07-12;
  `flutter install` not yet run. On-device FPS check + field test still open.

## Environment notes

- Windows 11, PowerShell. Deps (`ultralytics`, `opencv-python`, `pyttsx3`,
  `flask`) installed in `venv/` (python 3.9). NOTE: the local venv vanished
  sometime before 2026-07-11 (likely OneDrive free-up-space) and was rebuilt
  from scratch 2026-07-11 — if imports fail again, recreate with
  `py -3.9 -m venv venv` + pip install the four deps.
- Repo: dedicated git repo in this folder, remote
  `github.com/Aditya17-bot/object_detection_blind` (branch `main`). Large
  model/export binaries are gitignored (see `.gitignore`) — regenerate locally.

## Storage / Google Drive sync (2026-07-10)

- OneDrive is out of space. Working copy stays LOCAL at
  `C:\Users\rober\OneDrive\Desktop\object_detection_blind` (fast, runnable) —
  OneDrive simply can't upload new files, nothing is lost locally.
- Backup lives in Google Drive: user uploaded a snapshot via browser 2026-07-09
  (includes a stale useless venv — user should delete that folder inside the
  Drive copy once, at drive.google.com, to free ~26k files).
- Google Drive for Desktop was already installed; we started it 2026-07-10,
  `G:` mounts as "Google Drive", account already signed in. First indexing is
  slow — `G:\My Drive\object_detection_blind` may take a while to appear.
- **Pipeline**: run `.\sync_to_drive.ps1` to mirror the project to
  `G:\My Drive\object_detection_blind` (robocopy /MIR, excludes venv,
  __pycache__, .git). Run it after each work session.
- Fine-tune plan for door + dustbin written up for the user's friend in
  `finetune_handoff.md` (Option A: separate small model; nothing downloaded
  or trained yet — still requires user go-ahead, after phases 3-5).
