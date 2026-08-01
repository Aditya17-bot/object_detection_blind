# BlindAssist — Object Guidance App for Visually Impaired Users

## What this project is

A student project: a camera-based assistive app that detects common indoor
objects, estimates their rough direction in the frame, and speaks short guidance
messages. It is NOT a full navigation system — no depth in meters, no 3D
mapping, no face recognition.

Target classes (expanded 2026-07-09 after real-room testing showed the original
5 were too narrow): read **OBSTACLE_CLASSES** (Walk Mode warns) and
**FIND_CLASSES** (Find Mode only, never obstacle warnings) in `position.py` —
single source of truth.
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

## Recorded-video test results (phases 2 and 3)

Moved to `EVALUATION.md` — "Appendix: earlier clip logs (phases 2-3)"
(clip-by-clip zone/proximity and announcement results, 2026-07-10/11;
headline: all zone+proximity labels correct, remaining errors are COCO
naming, e.g. dustbin→"toilet" — wrong name, right warning).

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
- A0 done: yolov8n + door_dustbin_stairs exported to TFLite (fp16, in
  `blindassist_app/assets/models/` along with the Vosk model zip).
  DETECTION FIX 2026-07-13 (user report: "nothing much detected" on device):
  root cause = yolov8n.tflite was exported at 416 px AND detector.dart used
  stretch resize instead of ultralytics-style letterbox — together they cost
  ~0.2 confidence, so the 0.6 threshold filtered nearly everything. Fixed:
  re-exported yolov8n at 640 fp16 (`wsl_export_run.sh`, now imgsz=640;
  custom model was already 640) and detector.dart now letterboxes (gray 114
  pad) and un-letterboxes the output boxes. Validated on the 2026-07-13
  WhatsApp clip: TFLite letterbox pipeline now matches ultralytics yolov8n
  frame-for-frame (chair 0.88, bed 0.75/0.69); a Python port of _fillInput
  (YUV int math, rotation 0 and 90) reproduces ultralytics boxes to 3
  decimals. Remaining gap vs yolov8s is model capability (one far bed at
  0.36), not a bug — revisit model size only if on-device results still
  disappoint.
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

## Final-checklist pass (2026-07-14 — user "final checklist"; all mirrored
## Python + Dart, 100 Python / 89 Dart tests passing)

A batch of UX/latency changes, each REVIEWED by a critique subagent before
landing — several were redesigned in response (notes below). Full technical
write-up + patent material in **`PATENT_RESEARCH.md`** (maintained ongoing).

- **Clock mode is now the DEFAULT** (`GuidanceEngine use_clock=True`, was
  False). User decision 2026-07-14, overrides the earlier "default off".
  CAVEAT (from review): the mapping is a *camera-frame* clock — frame width
  spans 10-11-12-1-2 o'clock over the ~60 deg view, so "2 o'clock" = right
  frame edge (~30 deg), NOT the literal O&M clock where 3 o'clock = 90 deg.
  Relabel or remap if a trained user over-rotates.
- **Walk warnings now speak proximity** ("Chair on right, close"). Walk was
  previously silent on proximity except "very close". Bucket only, never
  meters (keeps continuous warnings short — the actionable token is
  direction).
- **Rough distance in METERS** (reverses the old "deliberately NOT metric"
  note, at user request). Monocular pinhole in `position.py`:
  `distance = real_height * CAMERA_FOCAL_NORM(0.85) / box_height_fraction`,
  per-class `_REAL_HEIGHTS`. Spoken as "about N meters" ONLY in Find mode,
  and ONLY when trustworthy — three safety guards added after review:
  (1) suppressed when the box is edge-clipped (top<=0.02 or bottom>=0.98 of
  frame — a clipped box reads falsely FAR, which would under-warn for the
  nearest objects); (2) suppressed when confidence < NAME_CONFIDENCE (a
  misdetected class picks the wrong real-height); (3) medium/far only (up
  close the estimate is worst and the bucket already means "here"). Focal
  const is the single calibration knob. NOT metric-grade — ~±30-40% at 5 m.
- **Clear-path finder** (innovation feature #6) — voice "which way" / "clear
  path", `clear_path()` in decision.py. Scores each of left/center/right by
  its CLOSEST obstacle's proximity rank (NOT summed box area — a near small
  hazard must beat a far bulky one), excludes `door` (a doorway is to walk
  THROUGH), ignores far; says "Stop, no clear path" when even the emptiest
  third has a close obstacle. Known limit: ObjectInfo carries only box
  center, so a wide straddling object is scored in its center third only
  (add box extent later).
- **Haptic direction** (main.dart) — single vibrator, SIDE encoded by PULSE
  COUNT (1=left, 2=ahead, 3=right; counting taps beats judging amplitude,
  which the S20 FE can't resolve). Fires ONLY on a zone change (no
  time-throttled re-buzz). Upgrade path: `vibration` package for richer
  patterns. Sonar still carries continuous stereo L/R.
- **`toothbrush` enabled as a Find class** (COCO #79, no training) — a demo
  of the general "personal small object" case; real favorites/beacon feature
  is still TODO (see below).
- **Latency work** (detector.dart, targets user's "1 second max"):
  • GPU delegate (`GpuDelegateV2`) now created INSIDE the worker isolate
    (GL context is thread-bound → must be built on the isolate that runs
    inference), with try/catch → CPU threads=1 fallback. The old
    create-on-main-run-on-worker-by-address pattern is gone.
  • First-frame WARMUP inference in each `_WModel` (mobile TFLite's first
    run pays graph-opt + delegate-init, often 1-2 s).
  • De-dupe: the 640px YUV->RGB letterbox was computed TWICE per frame (both
    models, identical output). Now computed once for COCO and reused for the
    custom model when sizes match (~2x preprocessing cut).
  UNVERIFIED ON DEVICE: whether the GPU delegate `.so` ships with
  tflite_flutter 0.12.1 (may silently fall back to CPU). Proof = the
  `BlindAssist TIMING`/`GPU delegate active`/`warmup` logcat lines, NOT the
  print alone. If GPU no-ops, wire NNAPI or bundle the GPU lib.
- **Count query** ("how many chairs") — voice `("count", <class>)` +
  `count_message()` in decision.py/dart; speaks "2 chairs" / "1 chair" /
  "No chairs". Engine `count()` stamps the clock like `describe()`.
- **OCR text reader** DONE 2026-07-14 (user request). `blindassist_app/lib/
  ocr.dart` = `OcrReader` (Google ML Kit on-device Latin text recognition,
  offline). Voice "read" / "read text" + a **Read** control button →
  `_readText()` in main.dart: pauses the image stream, `takePicture()`,
  OCRs the still, speaks the text (or "No text found"), resumes the stream.
  Dep added: `google_mlkit_text_recognition ^0.15.0` (resolved 0.15.1).
- **Favorites beacon DROPPED** 2026-07-14 (user: "doesn't look nice") —
  fully reverted, not in the codebase. Camera-only beacon (pin classes,
  sonar+voice guide when in view) remains a possible future feature; true
  "navigate to where I left it out of view" needs ARCore/SLAM.
- **Implementation-review fixes** (from a critique subagent) applied to
  detector.dart + main.dart: (a) native interpreter + GPU-delegate handles
  are now freed on `Detector.close()` via a `dispose` message to the worker
  (isolate death alone doesn't run the C-API destructors); (b) worker-init
  failure now sends `init-failed` → surfaced as an app error instead of
  silently detecting nothing forever (which looked identical to an empty
  room); (c) haptic pulse trains no longer interleave when the tracked
  object identity thrashes between two objects (`_pulsing` guard +
  `unawaited`). The reviewer CONFIRMED as correct: the input-reuse dedupe,
  the 3 s watchdog, the clip-guard math, the clear_path tie-break, and the
  distance gating.
- Test counts after this batch: **107 Python / 96 Dart**, all passing.

## Remote-inference pivot + finish-up phases (2026-07-15)

On-device TFLite on the S20 FE measured **~2.5 s/inference for BOTH GPU and
NNAPI delegates** (yolov8 head ops partition badly; every frame pays
CPU<->GPU copies) — unusable against the 1 s guidance budget. User decision:
**remote-primary architecture** — the app POSTs each frame's raw YUV420
planes to `infer_server.py` on the laptop (yolov8s + door model, ~140 ms/
frame), keeps sonar/haptics/voice/OCR native. `config.kUseRemote=false`
still selects the on-device path (NNAPI backend coded, unverified).

Finish-up phases (each committed separately, all reviewed against a
zero-added-latency rule by a critique subagent — its 12 findings are in the
F2/F4 commit messages):
- **F1** `74bdb1f`: pivot committed; http pinned ^0.13.6 (vosk_flutter
  conflict); TRUSTED_NAME_CLASSES {door, dustbin} bypass the NAME_CONFIDENCE
  gate (dedicated-model classes have no COCO lookalike — a 0.5-0.79 door
  must never be spoken as generic "obstacle"); custom conf 0.5→0.4
  everywhere (partial/far doors live in 0.4-0.5).
- **F2** `cafc44c` safety net: `FrameDetector.detect` returns **null on NO
  DATA vs [] for verified-clear** — guidance PAUSES on network failure
  ("Connection lost, guidance paused" after 5 misses, sonar silenced,
  "Guidance restored" on recovery) instead of acting on a fake empty room.
  Portrait lock (landscape would flip left/right advice), wakelock +
  lifecycle re-init (screen timeout killed the stream mid-walk), infer
  timeout 3 s→1.2 s, server warmup + predict lock + Y-plane pad fix,
  startup errors SPOKEN with a 5 s retry loop.
- **F3** `0d143f3`: **UDP auto-discovery** (app broadcasts on 5002,
  server replies, IP comes from the reply packet) — no more per-hotspot
  config.dart edits/rebuilds; baked IP is fallback only.
- **F4** `ca878ef`: TalkBack (liveRegion banner, custom actions, status
  pill excluded); speech priority (on-demand read-outs not cut by routine
  chatter; "very close" still cuts through); voice "stop"/"repeat"/
  "sonar on|off"/"mute|unmute" + PLURAL grammar ("how many chairs");
  startup speaks immediately, Vosk loads in parallel; webapp voice-dispatch
  crash fixed ("clock mode" used to silently kill the voice thread);
  haptic zone-swallow + sonar-during-OCR fixes.
- **F5 DONE 2026-07-16 — remote pipeline verified live end-to-end.**
  The 07-15 prime suspect was CORRECT: Android hotspot mode routes
  255.255.255.255 out the cellular interface. Fix in discovery.dart:
  enumerate NetworkInterface.list() and ping each interface's /24 DIRECTED
  broadcast (e.g. 10.250.253.255) as well as 255.255.255.255 (dart:io has no
  netmask API — /24 assumed, fine for Android hotspots). Verified on the
  phone: "server via discovery", /health OK, /infer streaming 200s,
  detections spoken; user walked with it — "working perfectly".
  Folder moved to C:\adi\object_detection_blind this session (venv survived;
  Flutter needed only pub get + clean rebuild).
  MEASURED PERFORMANCE — **SUPERSEDED 2026-07-30, these were CPU-only
  numbers, see "GPU enablement" below**: server compute ~750 ms/frame at
  imgsz 640 (yolov8s 516 ms + custom 231 ms — this laptop is ~4x slower than
  the historical 140 ms note; that number predates running BOTH models and the
  Acer power scheme). Phone sees ~1 FPS with occasional 1.2 s-timeout
  drops. `--imgsz 480` flag added to infer_server.py (~470 ms/frame,
  ~1.6x) = first latency lever; JPEG frame compression remains the prepared
  fallback if that's still too slow in the field. NOTE: run the server with
  `python -u` (or add flush) — stdout buffering hides the per-frame timing
  prints when output is redirected.
- **Find-once UX (2026-07-16, user field feedback)**: in Find mode the
  engine now announces the found target's position ONCE and auto-returns to
  walk mode ("it still keeps looking" after success read as a bug). set_mode
  preserves _last_time so min_gap carries across the auto-switch; the target
  keeps its persistence streak, so re-asking immediately re-announces.
  Mirrored decision.py + decision.dart; both UIs (webapp pill, app buttons)
  read engine.mode live so they follow the auto-switch for free.
- **F6**: `FIELD_TEST.md` = the user's validation walk protocol (includes
  the server-kill failure drill and pocket drill). PATENT_RESEARCH.md
  changelog has the 2026-07-15 entries (fail-safe absence/negative
  distinction extends the "selective abstention" thesis).

Test counts: **122 Python / 113 Dart**, all passing.

## Agent layer + research paper (2026-07-30 — Python done, Dart NOT started)

Two deliverables that are really one: a **research paper** carved out of the
project, and an **agent layer** so the user can speak naturally instead of
learning command phrases. The agent is the paper's new contribution and slots
under the `PATENT_RESEARCH.md` §9 thesis — *say less, never mislead* — now
argued across four layers (perception / planning / transport / **dialogue**).

**The blocker that shaped the design:** the Vosk recognizer is
GRAMMAR-CONSTRAINED (`voice.py`), so free-form speech is not mis-parsed, it is
never *heard*. Hence a trigger word ("assistant" / "question") opens a short
dictation window that goes to local Whisper (`transcribe.py`) and then to the
router. Tier 0 keeps its accuracy and its ~5 µs latency for everything else.

- **`agent.py`** — the single capability registry (`TOOLS`, 13 capabilities +
  `abstain` + the internal `ask` trigger). Drives the recognizer's phrase list
  at runtime (`VoiceListener(phrases=...)`), the LLM tool schema, the one
  executor, and `capabilities.json` (committed; a test asserts they match).
  • `AgentRouter(llm=None)` = two-tier. **llm=None is behaviourally identical
    to the old system**, enforced by `test_grammar_hit_matches_parse_command_exactly`.
  • **`route()` never raises** — an exception on the voice thread silently
    kills voice for the whole session (that really happened with "clock mode").
  • **Authority boundary:** the model emits only `{tool, args}`; unknown tool /
    unknown class / missing arg / prose / timeout all become abstain, and even
    the clarifying question is an `ASK_TEMPLATES` key. No spoken token ever
    originates in the model.
- **`agent_server.py`** — `POST /agent`, registered by BOTH `infer_server.py`
  (phone posts text or a WAV; the phone executes the returned actions) and
  `webapp.py` (executes and reports what was spoken). Separate module so it is
  testable without cv2/ultralytics.
- **`webapp.py`** — `_on_voice_command` is now route-then-execute through the
  registry. This FIXED a real drift bug: the old hand-written dispatch silently
  dropped read/sonar/stop/repeat/mute. New flags `--agent-model` (Ollama, opt
  in) and `--whisper-model`. UI gains a router pill and an **Ask box** — type
  an utterance, see which tier answered, no mic needed.
- **`paper/`** — `PAPER.md` (draft, ASSETS LBW target), `EVAL_PROTOCOL.md`
  (frozen BEFORE the router existed, on purpose), `eval_set.jsonl` (200
  labelled utterances). `eval_agent.py` produces the tables.
- **Measured keyword baseline** (`python eval_agent.py --config keyword`, no
  downloads): canonical 100 %, paraphrase **0 %**, multi-intent 0 %,
  out-of-scope abstention 95 %, tier-0 routing p50 5 µs, 0/200 boundary leaks.
  The two out-of-scope over-triggers are substring collisions worth keeping:
  "read my email" → OCR, "how do i get to the bus stop" → stop.

**STILL OPEN (needs the user's laptop — nothing was downloaded this session):**
1. `ollama pull qwen2.5:3b-instruct`, then **`python bench_llm.py`** — the
   feasibility spike. **Model choice revised 2026-07-30** from 1.5b to 3b: that
   session assumed a CPU-bound laptop, but the RTX 3050 has ~3 GB VRAM free
   after both YOLO models (see "GPU enablement" below), so the larger model
   fits and buys real paraphrase accuracy — which is the whole point of tier 1.
   Neither Ollama nor the model is downloaded yet (user deferred 2026-07-30).
2. `pip install faster-whisper` for the "assistant" trigger.
3. `python eval_agent.py --config two_tier --model <name>` (and `llm_only`,
   `llm_freetext`) to fill T3-T6 — the paper's keyword column is already real.
4. Record the ASR condition: 2-3 people (not the author) reading ~60 records
   aloud, transcripts appended to each record's `asr` array.
5. **On-device verification of the whole agent path** — `flutter install` +
   a walk. The recognizer swap in `dictate()` (stop/dispose/re-init of
   vosk_flutter's SpeechService) is the one part that CANNOT be unit-tested;
   if the native side refuses a second `initSpeechService`, dictation fails
   and the code restores command recognition, but that has not been seen
   happen on hardware.

## Dart agent port (2026-07-30 — DONE, 131 Dart tests)

The port the previous session deferred. Structure mirrors the Python layer, but
the tier boundary is drawn at the **Wi-Fi link**, which is the interesting part:

- `lib/logic/agent_actions.dart` — mirror of `agent.TOOLS` + `ASK_TEMPLATES` +
  `validate_action`, plus `parseRouteResponse`. Hand-mirrored ON PURPOSE and
  pinned: `test/agent_test.dart` asserts the Dart table field-by-field against
  the committed `capabilities.json`, so a Python registry change turns the Dart
  suite red. Also asserts the class enum equals `targetClasses` on both sides.
- `lib/agent_client.dart` — `POST /agent`, 5 s timeout. Returns **null on NO
  DATA** (unreachable/timeout/non-200/garbage), never a synthesised action —
  same rule as `RemoteDetector.detect`. Never throws: an exception on the voice
  callback kills recognition for the whole session.
- **LOCAL FIRST.** `main.dart` only calls the agent after `parseCommand`
  already returned null (new `VoiceListener.onUnmatched` hook). Every trained
  phrase still routes on-device in ~0 ms with the laptop off — the agent adds
  no dependency to anything that works today. `_onVoiceCommand`'s switch is now
  `_dispatch(VoiceCommand)`, shared by both tiers; the anti-feedback dedupe
  became `_repeatedTooSoon(key)` and covers the remote path too.
- **Whole-reply rejection**: one unusable action voids the entire response
  (executing the half that parsed is itself an unverified action).
- With no server (`kUseRemote=false`, or before discovery succeeds) `_agent` is
  null and unmatched speech is silently ignored — exactly today's behaviour.
  Deliberate: speaking "I can't do that" at every noise the recognizer
  half-hears would be worse than nothing. An abstention the server actually
  returned IS spoken.

### Handset open dictation (same session) — user chose the on-device path

The phone can now hear free speech with the laptop off, using no new download:

- `triggerWords = ['assistant', 'question']` in `voice_commands.dart`, parsed
  **LAST** (mirrors voice.py:135) so no existing command loses precedence —
  "assistant find the door" still finds the door.
- `VoiceListener.dictate()`: stop + dispose the SpeechService, build a second
  recognizer on the SAME already-loaded model **with no grammar**
  (`createRecognizer` without `grammar:` → `vosk_recognizer_new`, the full LM),
  capture one utterance, swap the grammar recognizer back. 900 ms lead-in
  discards the spoken "Yes?" (the phone's speaker reaches its own mic — same
  reason voice.py's `_dictate` has one); 6 s window so a silent user never
  holds the microphone. `finally` ALWAYS restores command recognition; only if
  the restore itself fails does `error` get set, and main.dart speaks it.
- `main.dart._startDictation()`: speak `askTemplates['listening']`, capture,
  then **local `parseCommand` first**, agent only on a miss. No server →
  speaks the `unknown` template (a deliberate question must be answered, unlike
  a stray half-heard phrase, which stays silent).
- Accuracy caveat: small-model free dictation is well below Whisper. That is
  the accepted trade for zero downloads and laptop-off operation; the Whisper
  path on the laptop remains the accurate one.

Test counts: **199 Python / 133 Dart**, all passing. `flutter analyze` clean
apart from the 3 pre-existing `avoid_print` infos in detector.dart.
NOT verified on the phone yet (no `flutter install` run this session) — and the
recognizer swap is precisely the part unit tests cannot reach.

## GPU enablement (2026-07-30) — every prior latency number was CPU-only

**The laptop has an RTX 3050 Laptop GPU (4 GB, driver 552.27, CUDA 12.4) and it
had never been used.** `venv/` contains `torch 2.8.0+cpu`, so
`torch.cuda.is_available()` was `False` — a plain `pip install torch` gives a
CPU wheel and nothing in any log says the GPU is idle. Every inference figure in
this file, `PATENT_RESEARCH.md`, and `paper/PAPER.md` was therefore measured on
CPU, including the ~750 ms/frame that motivated `--imgsz 480` and the "this
laptop is ~4x slower than the historical 140 ms" note.

Fix: a **separate `venv-gpu/`** (torch 2.6.0+cu124 — the cp39 ceiling for
cu124; `venv/` deliberately left untouched as a working fallback, since it
vanished once before to OneDrive). Both benchmark arms run inside `venv-gpu` via
`device='cpu'` vs `device=0`, so the comparison isolates CUDA rather than
confounding it with a torch version change.

Measured (12 frames from `test_output/eval_a.mp4`, median, warmup excluded,
`cuda.synchronize()` before each stop; full table in `test_output/gpu_bench.md`):

| condition | yolov8s | custom | total | FPS |
|---|---|---|---|---|
| CPU @640 | 155.3 ms | 101.2 ms | 256.5 ms | 3.9 |
| **GPU fp32 @640** | **11.3 ms** | **9.9 ms** | **21.2 ms** | **47.1** |
| GPU fp32 @480 | 9.6 ms | 9.8 ms | 19.4 ms | 51.6 |
| GPU fp16 @640 | 11.4 ms | 9.5 ms | 20.8 ms | 48.0 |

Consequences:

- **`--imgsz 480` is retired as a latency lever** — it saves 2 ms on GPU and
  costs accuracy. Same for fp16 (0.4 ms): at this model size inference is
  kernel-launch-bound, not compute-bound.
- **`yuv420_to_bgr` is the new bottleneck.** These are `predict()`-only times;
  the ~750 ms came from `/infer` logs, which also include YUV→BGR
  reconstruction, rotation, and JSON. With models at ~21 ms that request path is
  now the overwhelming majority of server latency. Optimise it, not the models.
- **~3 GB VRAM free** for a tier-1 router model (torch peak *allocated* was only
  0.07 GB, but that excludes the CUDA context and cuDNN workspaces — budget
  0.5-1 GB actual). Hence the qwen2.5 1.5b→3b revision above.
- The remote-primary pivot stays correct regardless: the phone's Exynos 990 at
  ~2.5 s/inference is unrelated to the laptop's torch build. Only the
  *justification numbers* changed.
- Unexplained: `venv/` (torch 2.8.0+cpu) measured yolov8s CPU at 383 ms, while
  `venv-gpu/` (2.6.0+cu124, `device='cpu'`) measured 155 ms. Suspect threading
  or MKL differences between builds; not isolated, so do not cite it.

Run the benchmark: `venv-gpu/Scripts/python.exe` on the scratchpad script, or
regenerate from `test_output/gpu_bench.md`'s header for exact conditions.

## Environment notes

- Windows 11, PowerShell. Deps (`ultralytics`, `opencv-python`, `pyttsx3`,
  `flask`) installed in `venv/` (python 3.9). NOTE: the local venv vanished
  sometime before 2026-07-11 (likely OneDrive free-up-space) and was rebuilt
  from scratch 2026-07-11 — if imports fail again, recreate with
  `py -3.9 -m venv venv` + pip install the four deps.
- Repo: dedicated git repo in this folder, remote
  `github.com/Aditya17-bot/object_detection_blind` (branch `main`). Large
  model/export binaries are gitignored (see `.gitignore`) — regenerate locally.

## Storage / backup (updated 2026-07-15 — user decision)

- **Google Drive sync is RETIRED**: Drive is full (user 2026-07-15 — "don't
  sync there"). Do NOT run `sync_to_drive.ps1` anymore. The old Drive
  snapshot (2026-07-09/10) still exists but is stale.
- OneDrive is also out of space. Working copy stays LOCAL at
  `C:\Users\rober\OneDrive\Desktop\object_detection_blind` (fast, runnable) —
  OneDrive simply can't upload new files, nothing is lost locally.
- **Backup = GitHub**: push to `origin main` after each work session.
  Covers all code + docs + the user-trained `door_dustbin_stairs.pt`
  (committed on purpose). NOT covered (gitignored): auto-downloaded weights
  and the Vosk model (redownloadable), TFLite exports (regenerate from the
  .pt), and **`test_output/` (~27 MB of eval clips/keyframes/logs — the
  report + patent evidence; only copy is this laptop + the stale 07-10
  Drive snapshot — worth an occasional USB copy)**.
- Fine-tune plan for door + dustbin written up for the user's friend in
  `finetune_handoff.md`.

## Field walk + quieter guidance + real tier 1 (2026-07-31)

First walk with the agent build on the phone, then the changes it forced.

**What the walk proved** (server log, 612 frames over ~3 min): 76 % of frames
carried detections, **10 `/agent` round trips** — the trigger-word dictation and
the recognizer swap ran on hardware without killing voice recognition, which was
the one path unit tests could not reach. Server compute ~305 ms/frame at
720x480 (GPU; run `venv-gpu/Scripts/python.exe`, NOT `venv/` — `venv` is the CPU
torch build and gives ~750 ms).

**User's verdict:** "it keeps saying all the objects but it's too much of a
cluster" + "I need the LLM to converse". Three changes, all mirrored
Python/Dart:

- **Walk mode is quieter.** `WALK_MIN_PROXIMITY = "close"` in decision.py /
  `walkMinProximity` in decision.dart — medium obstacles are now silent EVEN
  DEAD AHEAD (the old rule announced medium in the centre third). Only
  close/very close speak. Rationale is written up as PATENT_RESEARCH §4.8: an
  over-full warning channel is less safe, not just annoying.
- **New `check` capability** — "is there anything in front of me", "what's on
  my left", "anything on my right" → `check_direction()` / `checkDirection()`
  reports the two closest things in that third, closest first, with proximity
  buckets ("A person very close on your right, and a bottle medium").
  Deliberately TIER 0 / on-device: works with the laptop off. Reports every
  class, not just obstacles — the user asked, so a cup counts.
  Parser rule needs BOTH a direction word and a question word, and sits AFTER
  `find`, so "find the door on my left" still finds.
- **Chat mode — the authority boundary was narrowed on purpose.** The claim is
  now "no **guidance** token originates in the model" (was: no spoken token).
  `RouteResult.say` is a separate channel: the model may write a REPLY, never a
  capability's output. Guards: grounded in the state block only, `clean_say()`
  caps at `MAX_SAY_CHARS` 240 and truncates at a sentence, bare prose where a
  tool call belongs is still discarded, and `AgentRouter(allow_chat=False)`
  restores the old absolute rule (the paper's ablation arm).
  **The phone now POSTs its own `state`** (`GuidanceEngine.stateSummary`) with
  every `/agent` request — infer_server has no engine, so without it a scene
  question would be answered from nothing.

**Tier 1 is live and needed no download:** Ollama was already installed with
`llama3.2:3b` (also qwen3:4b, gemma2). Run the server with
`--agent-model llama3.2:3b` (bare `--agent-model` now defaults to it).
Measured: paraphrases route in ~1.0-1.6 s, chat answers in ~2 s. Two real model
failures are pinned as tests — it answered a greeting with the INTERNAL
"listening" template ("Yes?"), so `MODEL_TEMPLATES` now limits which templates
it may pick; and it emits chat as a fake `{"tool": "say"}` call, which strict
validation was discarding (`_say_shaped_action` accepts the shape).

**UI rebuilt (same session).** All buttons removed from the main screen:
- `lib/features_page.dart` — swipe UP from the camera view. Generated from
  `kTools`, so a capability cannot appear there without existing. Cards show
  the trigger phrases, tappable ones run the capability, quick-find chips give
  a mic-free find, and it holds the settings.
- `lib/settings.dart` — `AppSettings` (shared_preferences, new dep) + pure
  `greetingFor()`. The app now opens with "Good morning/afternoon/evening,
  Aditya" — for a user with no splash screen the greeting IS the "it started"
  signal, and the name is editable in the features page.
- Main screen is camera + scrim + mode chip + one glass announcement card.
  Gestures unchanged (tap describe / double-tap sonar / long-press repeat) plus
  swipe-up; `Sonar.setEnabled()` added so the beeps pause while that page is open.

Test counts: **219 Python / 157 Dart**, all passing. `flutter analyze` clean
apart from the 3 pre-existing `avoid_print` infos in detector.dart.

## Paper: all evaluation arms measured (2026-08-01)

`paper/PAPER.md` is no longer a draft with reserved results — **T3-T6 are
filled**, the abstract is written, and §6.4/§8 carry the honest caveats. Runs
live in `test_output/agent_eval_{keyword,llm_only,two_tier,llm_freetext}.md`,
eval set sha256 `e4eeca83070e2d66`, model `llama3.2:3b` via Ollama.

Headline numbers (n=200):
- keyword 39.5 % overall · canonical 100 % · paraphrase 0 % · over-trigger 5.0 %
- llm_only 45.5 % · **canonical drops to 45 %** · over-trigger 52.5 %
- **two_tier 53.0 %** · canonical 100 % · paraphrase 47.1 % · over-trigger 55.0 %
- free-text ablation: **85/200 (42.5 %) fabricated** perceptual content
- tier 1 latency p50 1141 ms / p95 2141 ms (two-tier); tier 0 stays 5 µs
- 0 guidance-string boundary leaks in every routed configuration

Two findings to carry into any write-up: tiering **beats** LLM-only outright
(the model mis-routes canonical commands the parser gets right), and the
abstention collapse (5 %→55 % over-trigger) is a genuine negative result that is
NOT tuned away — the protocol was frozen before the router existed.

Fixes the eval run itself produced (both now regression tests):
- `voice.py` treated any "left"/"right" as a direction, so "how much battery is
  left" became `check(left)`. Ambiguous pair now needs a positional lead-in
  ("on **my** left", "check left"); ahead/front/forward need none.
- Ollama's JSON mode closes the string when `num_predict` runs out, so a
  half-word arrived as valid JSON (`{"say": "I don"}`). `MIN_SAY_CHARS = 12`
  rejects a short reply with no terminal punctuation; num_predict raised to 128.
- `eval_agent.py` now (a) knows `check_direction`'s outputs are legitimate
  deterministic speech and (b) counts conversational replies separately instead
  of flagging them as authority-boundary leaks.

Post-freeze amendments are documented in `paper/EVAL_PROTOCOL.md` §8 — including
the two eval records affected by the `check` capability (par-025, amb-008),
which were NOT re-labelled.

Study dossier (diagrams, charts, architecture, timeline) published as an
artifact: https://claude.ai/code/artifact/d6e5e754-5c6c-4e6e-946e-3fb762f99503
Republish by redeploying `scratchpad/blindassist_study.html` (same URL).

Test counts: **221 Python / 159 Dart**.

## Overleaf + ASR tooling (2026-08-01, later)

- **`paper/main.tex`** — ACM `acmart` (sigconf, nonacm) draft of the whole
  paper, **self-contained**: both diagrams are TikZ and both charts are
  pgfplots, so there are NO images to upload or re-export. Overleaf: upload
  `main.tex` alone, compiler pdfLaTeX. Setup + submission checklist in
  **`paper/README_OVERLEAF.md`** (remove `nonacm` + the two draft lines when
  ACM sends the rights block; references still need writing).
- **`asr_collect.py`** — the ASR condition of EVAL_PROTOCOL §4, which was
  specified but had no code. Three subcommands: `sheet` (stratified 60-record
  reading sheet, 12/category, deterministic), `record --speaker A` (one
  utterance at a time via sounddevice, WAV per record under
  `test_output/asr_audio/<speaker>/`), `transcribe` (writes transcripts into
  each record's `asr` array, one entry per speaker+engine, re-runnable without
  duplicating). Transcriber: faster-whisper if installed, else the **Vosk model
  already in the repo with its grammar removed** — which is what the handset
  itself does for open dictation, so it is a legitimate condition, not a
  degraded stand-in. NO DOWNLOAD NEEDED for the Vosk path.
- **`eval_agent.py --condition asr`** — expands one row per TRANSCRIPT (records
  with no audio are skipped, never silently scored on clean text), reports
  coverage, and writes `agent_eval_<config>_asr.md`.
  **Writing transcripts CHANGES THE EVAL-SET HASH** — keep clean-condition
  numbers under `e4eeca83070e2d66` and quote the new hash for ASR numbers.
## Paper finished to submission quality (2026-08-01, later still)

User: "make sure the paper is fully finished, enough references, remove all the
weak links, publication worthy". Nothing about the *system* changed; what
changed is that the paper's evidence now matches its claims.

- **Every eval config re-run** — the committed run reports were stale in two
  ways and had to go. They predated the harness fix that stops a conversational
  reply being scored as an authority-boundary leak, so `llm_only`/`two_tier`
  shipped with literal "AUTHORITY BOUNDARY LEAK — investigate before
  publishing" blocks while the paper claimed 0; and their T4 latencies came
  from a differently-loaded machine. **Re-run says `boundary leaks 0` for all
  three routed configs.** Changes: `llm_only` 45.5 % → **45.0 %** (paraphrase
  50.0 → 48.6). `keyword`/`two_tier` accuracy and over-trigger unchanged.
  Free-text fabrication reproduced exactly at 85/200.
- **One claim withdrawn**: two-tier's tier-1 median is NOT below llm_only's
  (1188 vs 1172 ms) — the old 1141-vs-1992 gap was machine load. The
  explanation for it is deleted, not softened. Correct C3 form: per-call cost is
  identical, tiering wins by not making the call for 30 % of traffic.
  Conversational replies now reported: 4/200 llm_only, 6/200 two_tier.
- **`paper/references.bib` — 53 entries, all cited** (was zero references,
  which was disqualifying). Threads: verification asymmetry (MacLeod, Adnin &
  Das, Stangl), reliance/false alarms (Lee & See, Parasuraman & Riley, Wickens
  & Dixon, alarm fatigue), abstention (Chow, selective prediction, deferral,
  calibration), containment (Ji, Toolformer/ReAct/ToolLLM, PICARD), assistive
  navigation (VizWiz, NavCog, CaBot), non-visual output (vOICe, van Erp).
  ⚠ **Assembled from memory, no DOIs, NOT machine-verified** — must be
  re-exported from ACM DL/DBLP before submission. Flagged in README + PAPER.md
  + PATENT_RESEARCH: a paper about not stating what you can't verify cannot
  ship an unverified reference list.
- **`main.tex` rebuilt.** Figure 2's arrows were wrong (validated actions drawn
  flowing INTO abstain; rejects flowing into the reply channel). Figure 1
  redrawn as two lanes split by the authority boundary. Added ethics /
  positionality / availability section (ASSETS expects it; no blind
  participants is stated as load-bearing). Related work now cited inline.
  No local LaTeX — **never compiled**; `scratchpad/texcheck.py` verified
  environments, braces, math mode and that all 53 cite keys resolve. Compile on
  Overleaf first.
- Fixed real internal contradictions: thirteen vs fourteen capabilities, four
  vs five mechanisms, test counts (now 221/159, verified), and two figures
  (latency waterfall, confusion matrix) promised in §7 that never existed.
  Clip-eval "100 % of reviewed keyframes" now carries its denominator:
  **31/31 direction correct, 0/31 phantom, 6/31 wrong name**.
- ASR condition is stated as **not reported** and the consequence written into
  §8 (paraphrase/out-of-scope numbers are upper bounds on the deployed
  pipeline). Slot it in when the recordings land.

- `OllamaRouter` now sends `"think": False`. Reason: the qwen3:4b sensitivity
  arm returned **"no tool call in model output" on 102 of 140 tier-1 calls** at
  6-8 s each — it spends the token budget on a thinking block — so tier 1
  contributed nothing and the run scored exactly the keyword baseline (39.5 %,
  5.0 % over-trigger). Written up in PAPER §8 as a limitation: the boundary
  degraded to fewer capabilities rather than wrong ones (designed behaviour),
  but the model-size comparison is uninformative until thinking is off.
