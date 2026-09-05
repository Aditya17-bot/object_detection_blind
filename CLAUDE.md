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

## Spoken-input evaluation + Word build (2026-08-01, night)

User supplied two WhatsApp voice notes of friends reading the 60-utterance
sheet, and asked for a DOCX in Overleaf style because Overleaf's free tier
stopped compiling and asked for payment.

**The Overleaf "paywall" was a compile timeout.** Four vector figures (2 TikZ
diagrams + 2 pgfplots charts) on top of `acmart` exceeded the free tier's time
budget. Fix: `paper/build_figures.py` renders all four as PNGs with matplotlib;
`main.tex` now uses `\includegraphics` and has zero TikZ/pgfplots. Upload
`main.tex` + `references.bib` + **the `figures/` folder**.

**Audio pipeline — no downloads.** Files were AAC in MP4 (`mp4a`), no ffmpeg on
this machine. `tools/aac_to_wav.ps1` uses the WinRT `MediaTranscoder` that ships
with Windows. Gotcha: `TranscodeAsync()` returns `IAsyncActionWithProgress<double>`,
not `IAsyncAction` — picking the wrong AsTask overload fails with a useless
`__ComObject` cast error.

**Segmentation: silence-splitting was tried and REJECTED.** `import` found 34
and 60 segments against a 60-line script; no parameters gave 60 for both
speakers. Worse, a count of 60 does not prove correct boundaries — one merge
plus one over-split cancels in the count and shifts every label between them,
silently. New `asr_collect.py align`: transcribe the whole session with word
timings, Levenshtein-align the word stream to the known script, take boundaries
from the script. Records where <34 % of script words aligned are DROPPED, not
guessed (11 for A, 2 for B). **107 transcripts over 59 records.**
- Bug worth remembering: first run fed 48 kHz interleaved **stereo** to Vosk as
  mono and got 101 fluent-nonsense words ("shoo shoo whoosh"). No crash, no
  warning. Always go through `_read_wav_mono16k`.

**Set hash changed: `e4eeca83070e2d66` (clean) → `f9e775b6a65279a4` (with
transcripts).** Only `asr` arrays differ. New `--asr-subset` flag re-runs the
clean condition over just the 59 recorded records — without it the comparison
would be between two different populations (the ASR subset is stratified
12/category, the full set is not).

**THE RESULT THAT MATTERS — spoken input mostly erases the agent layer's gain:**

| matched, 59 records | keyword text | keyword spoken | two-tier text | two-tier spoken |
|---|---|---|---|---|
| overall | 37.3 | 34.6 | **44.1** | 35.5 |
| out-of-scope abstention | 91.7 | 91.3 | 41.7 | 30.4 |
| over-trigger | 8.3 | 8.7 | 58.3 | **69.6** |

Two-tier's margin over baseline: **+6.8 points on text, +0.9 spoken.** Keyword
is nearly ASR-invariant; the LLM tier's abstention degrades exactly when input
quality drops. Written up as PAPER §7.1 + main.tex §7.1 + docx Table 3. The
gate biases optimistically (drops worst-recognised utterances) so the reported
degradation is a FLOOR — stated in all three.

**Word build:** `paper/docx_writer.py` = hand-rolled OOXML (no python-docx, no
pandoc, no LibreOffice here), `paper/build_docx.py` = the paper content.
Verified for real: Word COM opens it, **6 pages / 5889 words**, PDF exported
(`tools/docx_to_pdf.ps1`), pages rendered to PNG via WinRT
(`tools/pdf_to_png.ps1`) and inspected. Two bugs that only a render showed:
drawing XML was being escaped as visible text, and the final `sectPr` needs
`<w:type w:val="continuous"/>` or the title block sits alone on page 1.
PROSE IS DUPLICATED between `main.tex` and `build_docx.py` — change both.

- `OllamaRouter` now sends `"think": False`. Reason: the qwen3:4b sensitivity
  arm returned **"no tool call in model output" on 102 of 140 tier-1 calls** at
  6-8 s each — it spends the token budget on a thinking block — so tier 1
  contributed nothing and the run scored exactly the keyword baseline (39.5 %,
  5.0 % over-trigger). Written up in PAPER §8 as a limitation: the boundary
  degraded to fewer capabilities rather than wrong ones (designed behaviour),
  but the model-size comparison is uninformative until thinking is off.

## Detector investigation + two live defects found (2026-08-02)

User asked what the app needs next, whether a model better than YOLOv8 exists,
and whether dropping unused COCO classes would be a quick win. Investigation
only — **no app code changed this session.** Two defects found, both undocumented
until now, and both still OPEN.

### DEFECT 1 — the NAME_CONFIDENCE gate does not work

`decision.py:113` speaks the generic word "obstacle" instead of a class name
when confidence < `NAME_CONFIDENCE = 0.8`. That threshold rests on a probe
recorded in `EVALUATION.md:106-112`: misnames 0.65-0.75, correct names >=0.85.
**Measured on the actual clips (14 sampled frames, conf 0.6, GPU):**

| | EVALUATION.md claims | measured 2026-08-02 |
|---|---|---|
| dustbin -> "toilet" | 0.65-0.72 | **peak 0.94**, mean 0.80 |
| wardrobe -> "refrigerator" | 0.72-0.75 | **peak 0.82** |
| correct "chair" | >=0.85 | 0.92 |

The bands OVERLAP, so no threshold separates them and "Toilet ahead" gets spoken
by name — which `test_output/phase3_WhatsApp Video 2026-07-09 at 10.14.53 PM
(2)_walk.log:1` already shows happening. **Confidence is not a signal for "is
this word right".** `EVALUATION.md:106-112` is wrong as written and paper §4.1
describes a gate whose empirical basis is falsified; both need correcting
regardless of what else is done. (Paper's routing/ASR/fabrication results are
untouched — those measure the dialogue layer.)

### DEFECT 2 — clock bearings are ~2x off, in the DEFAULT configuration

`position.py:136-148` maps frame width onto **10-11-12-1-2 o'clock**, with the
comment justifying it from "a 60-70 degree cone". One clock hour is 30 deg, so
10->2 spans **120 deg** while the camera sees **60-70 deg**. Every spoken bearing
is roughly double the true angle: the right frame edge is ~+32 deg and gets
announced as "2 o'clock" (+60 deg). Clock mode is DEFAULT since 2026-07-14, so
an O&M-trained traveller — exactly the user the feature targets — is
systematically over-rotated. Untrained users ignore the number and are fine.
Correct mapping for 60 deg is **11-12-1**, which also destroys the feature's
stated rationale ("finer than the 3 zones"): at this FOV clock bearings CANNOT
be finer than left/center/right.

### Model comparison — answers to the user's questions

Benchmarked on the known-error clips (script was in scratchpad; regenerate from
the plan file). Downloads: `yolo11s.pt` (18.4 MB), `yolov8s-worldv2.pt`
(24.7 MB), both now gitignored.

- **YOLO11 does NOT fix the naming.** Still "toilet" @0.93 on the dustbin; on
  the dark-room clip it is arguably WORSE than yolov8s (loses the wardrobe,
  emits oven/bowl/chair @0.62-0.69). Do not re-try this expecting a fix.
- **The errors are VOCABULARY, not capacity.** COCO has no wardrobe/dustbin/
  window, so the model makes a forced choice over 80 words and picks the nearest.
  Corroborated by the repo's own evidence: the 6.2 MB nano custom model hit
  0.91 on doors, beating 21.5 MB yolov8s on exactly the objects it misnames.
- **YOLO-World (open vocabulary) works but is noisy.** `set_classes` with
  "trash can" gets it right @0.85 — but simultaneously emits "toilet" @0.87 for
  the SAME object, "wardrobe" only scores 0.22, and eval_a produces nine
  competing labels for the same furniture. Needs dedup + per-class thresholds +
  its own calibration before it is safe. The stairs precedent applies.
- **ResNet is not an option** — it is a classifier (one label per image, no
  boxes). The whole pipeline is box geometry: zone from box centre, proximity
  from box area, distance from box height, sonar pan and clock bearing from
  `center_x`. A classifier kills every capability. (ResNet as a *backbone*
  inside Faster R-CNN is real but slower and less accurate than what we have.)
- **Dropping unused COCO classes gives NO speedup.** The head computes all 80
  scores in one op; cost is the backbone, which runs identically. Detections are
  already filtered to `TARGET_CLASSES` post-hoc (`infer_server.py:150`).

### Agreed next step — embedding-based naming head

Full plan, written and approved-in-principle:
**`C:\Users\rober\.claude\plans\federated-painting-seal.md`**

Keep YOLO for *where* (31/31 direction correct), re-decide *what* from an
embedding of the crop matched against user-labelled examples. `YOLO.embed()`
exists, so no second model and no download. Insert at `infer_server.py:182`
(full-res frame + merged dets both in scope). Phone needs no Dart change —
`RemoteDetector` passes server names through verbatim.

Key point: **embedding distance is a calibrated abstention signal**, which is
exactly what Defect 1 proves confidence is not. User will do the manual
labelling (~20-40 min, dragging pre-grouped crops between folders).

Three constraints that will bite, detailed in the plan: output vocabulary must
stay within `TARGET_CLASSES` or things fail SILENTLY (person-sized proximity,
no metres, never walk-warned); `GuidanceEngine._streaks` is keyed by name so an
unstable namer makes the app QUIETER not better (needs hysteresis); and
`infer_server.py:150` filters before the hook, so a dustbin labelled "vase"
never reaches it.

### Also still open from this session

- GPS/Google-Maps indoor guidance was proposed and **dropped** — GPS indoors is
  10-50 m error against a 10-15 m flat, and a cloud Maps dependency would break
  the offline architecture and the §9 privacy claim. Camera-based place
  recognition is the viable route if it comes back.
- Standing list from 2026-08-01 night, unchanged: router model choice (app ships
  `llama3.2:3b` at 55 % over-trigger; gemma2 gets 10 % but 6 s/query), dictation
  audio never sent to the laptop's Whisper (server side is already wired at
  `agent_server.py:42` and `infer_server.py:217`, the phone just never uses it),
  the never-run server-kill drill in `FIELD_TEST.md`, battery/thermal never
  measured, stairs still disabled, and no blind user has ever used the app.

## Embedding naming head — BUILT, awaiting the user's labelling (2026-08-02)

Implementation of `.claude/plans/federated-painting-seal.md`. Keeps YOLO for
*where* and re-decides *what* from an embedding of the crop matched against
user-labelled examples. **All code is done and tested; the production index does
not exist yet because the labelling is a manual step only the user can do.**

- **`name_index.py`** — the runtime piece. `NameIndex` (nearest neighbour over
  L2-normalised `YOLO.embed()` vectors), `NameSmoother` (hysteresis), `Namer`
  (the thing the servers hold; `apply(frame, dets)` rewrites `d["name"]` in
  place and records the original under `d["yolo_name"]`). Embedder is injected,
  so `test_name_index.py` (30 tests) needs no weights and no images.
  Four abstention rules, all of which earned their place:
  • `MIN_SIM` / `MIN_MARGIN` — a rename needs the nearest labelled crop to be
    close AND clearly closer than the best competing label. Margin is the
    discriminating axis; min_sim barely matters in the sweep.
  • `IGNORE_LABEL = "_ignore"` is a real label IN the index, not a discard pile
    — junk crops are what make a junk query fail the margin test instead of
    snapping to the nearest real class.
  • `TRUSTED_KEY` — detections from the custom door/dustbin model are **never**
    renamed. Their classes exist because COCO had no word for them, so there is
    no forced choice to fix. Found empirically: without it the namer relabelled
    a real door "wardrobe" 3x on eval_a.
  • vocabulary containment — a label outside `TARGET_CLASSES` is refused at the
    decision point, because downstream it fails SILENTLY (person-sized
    proximity, no metres, never walk-warned).
- **Hysteresis tracks are keyed by the DETECTOR's word, not just IoU.** Two
  models over one frame give near-identical boxes for one object (COCO
  "refrigerator" + custom "door" on the wardrobe), and greedy IoU matching let
  one steal the other's track — silently swallowing every rename on eval_a until
  keys were added. Pinned by
  `test_overlapping_boxes_from_two_models_keep_separate_tracks`.
- **`harvest_crops.py`** — samples the 8 clips, detects at conf 0.25 with NO
  class filter, crops from `frame.copy()` taken BEFORE annotation (every JPEG
  already in `test_output/` has boxes and grid burned into the pixels), dedupes
  by embedding similarity, then farthest-point-samples to `--max-per-name` 15.
  665 raw crops -> 280 to label, in 31 folders named by YOLO's guess.
- **`build_name_index.py`** — folders become labels, writes `name_index.npz`,
  and prints a **leave-one-out report + threshold sweep**. The sweep is the
  point: it looks for a setting with zero wrong names and says so in words if
  there isn't one.
- **`verify_namer.py`** — runs clips through the real pipeline and reports what
  changed. Keep `--stride` SMALL: at stride 10 the tracker loses boxes between
  samples (eval_a gives 34 renames at stride 1 and 1 at stride 10 — a sampling
  artifact, not a namer failure).
- **Wiring:** `infer_server.py` (`--name-index`, auto-loads if present) and
  `webapp.py` (same flag). `phase2_detect.py` was split into `collect_dets` /
  `apply_namer` / `infos_from_dets` / `draw_dets` so naming happens ONCE over
  the merged detections of both models — per-model calls would clobber the
  smoother's tracks. `annotate()` keeps its old signature for phase2/3/4.
  Class filtering moved to AFTER naming (a dustbin YOLO calls "vase" has to
  reach the namer). Phone needs no Dart change.
- **Vocabulary expanded**: `wardrobe` (obstacle) and `window` (find-only) added
  to `position.py` + `position.dart` + both threshold/height tables, voice
  synonyms cupboard/almirah/closet -> wardrobe in `voice.py` +
  `voice_commands.dart`, `capabilities.json` regenerated. No detector emits
  these — they exist so the namer has a correct word to use.
  **`laundry basket` added the same day** during the user's labelling pass
  (0.85 m tall, 0.3 m wide, obstacle, thresholds copied from suitcase, real
  height 0.85, synonyms laundry/basket/hamper/"laundry bag"). Note the failure
  mode it fixes: YOLO calls one "handbag", which is NOT in TARGET_CLASSES, so
  today the app drops it entirely — a waist-high floor obstacle it never warns
  about. Expect more of these as labelling continues; the recipe is
  position.py + position.dart (class + `_AREA_THRESHOLDS` + `_REAL_HEIGHTS`),
  voice.py + voice_commands.dart synonyms, `agent.py --write-manifest`.

**Two defects from 2026-08-02 are now resolved in the docs:**
`EVALUATION.md` §6.2 is corrected in place (confidence gate RETRACTED with the
measured overlap table), the paper reports it as a negative result in all three
duplicated sources (`PAPER.md` §7, `main.tex` §6, `build_docx.py`), and
`PATENT_RESEARCH.md` gains **§4.9** plus a change-log entry. **Defect 2 (clock
bearings ~2x off) is still OPEN and untouched.**

## Naming head: real index built and verified (2026-08-02, later)

User labelled all 280 crops. `name_index.npz` is built, tuned and committed —
**17 labels, 280 crops** (_ignore 72, chair 40, bed 24, suitcase 19, dining
table 18, backpack 17, wardrobe 16, bottle 16, potted plant 12, person 11,
laundry basket 9, book 8, laptop 6, dustbin 5, door 3, couch 2, window 2).
Report: `test_output/name_index_report.md`.

**Thresholds tuned from the sweep: `MIN_MARGIN` 0.05 -> `0.15`** (`MIN_SIM`
stays 0.62). That is the highest-coverage row with **zero wrong names**:
leave-one-out names 49/280 with **49/49 correct**, versus 10 errors at 0.05.
The sweep also shows `MIN_SIM` is inert anywhere in 0.50-0.65 — **margin does
all the separating**, similarity almost none. Do not carry these numbers to a
differently-labelled index; re-run the sweep.

**Clip verification at stride 1** (`verify_namer.py --stride 1`, 8 clips,
~2000 frames): **105 renames, 8 distinct patterns, every one inspected by eye.
104 correct, 1 arguable.** Five of them are defects previously recorded in
`EVALUATION.md` as unfixable COCO-vocabulary errors:

| rename | count | verdict |
|---|---|---|
| refrigerator -> wardrobe | 31 | correct (defect #1) |
| laptop -> book | 28 | correct — the paper notebook EVALUATION.md §3 flags |
| toilet -> dustbin | 23 | correct (defect #2) |
| cell phone -> suitcase | 11 | correct — the maroon suitcase from the dark clip |
| person -> chair | 4 | correct — a **blanket draped over a chair**; YOLO hallucinated a person |
| toilet -> chair | 3 | correct — the cream plastic stool |
| keyboard -> book | 3 | correct — a hardcover notebook |
| chair -> laundry basket | 1 | correct — the new class earning its keep on day one |
| bench -> suitcase | 1 | ARGUABLE: box is a bench with a suitcase on it. Both are obstacle classes, so the warning is unchanged in kind |

**Zero renames on the 2 clips containing none of the labelled objects** — the
false-positive bar the stairs class failed. Abstention dominates everywhere:
`ambiguous` is the most common reason by far, `trusted source` next (the custom
door/dustbin model is never renamed), and `matched _ignore` fires in the
hundreds on the cluttered clips — the junk label is doing real work.

### Two bugs the labelling pass exposed (both fixed, both now pinned by tests)

1. **`harvest_crops.py` filenames were not globally unique.** The suffix was
   `int(conf * 100)`, so two boxes in one frame that rounded to the same
   confidence got the same name in different guess-folders. Labelling flattens
   those folders, and **Explorer replaces silently on a same-name move** — 3
   crops were destroyed, one of them a dustbin (a 5-example class). Filename is
   now `<clip>_f<frame>_<record index>_<class>.jpg`. The 3 lost crops were
   regenerated from `manifest.csv` (which carries clip + frame + box) and
   re-placed. `test_harvest_crops.py` = 7 tests.
2. **`build_name_index.leave_one_out` scored a predicted `_ignore` as a WRONG
   NAME.** At runtime matching `_ignore` is an abstention — the detection keeps
   YOLO's word — so the report was charging the model for its safest outcome
   and reported "**No setting reaches zero errors**" when a clean setting
   existed. Now mirrors `NameIndex.classify_vectors` exactly, and a test
   asserts decision-for-decision equality across three threshold settings.
   The reverse direction (a crop the user put in `_ignore` matching a real
   class) still counts as wrong — that one does put a word in the user's ear.

Also fixed during the audit: 2 crops the user had **copied instead of moved**
(same bytes under two contradictory labels — they were full-frame crops holding
a stool AND a suitcase AND a bench, so both went to `_ignore`), and 1 pair of
byte-identical crops of one object detected as both `sink` and `toilet`.

## Speech ordering: focus arbitration + input floor (2026-08-02, night)

First walk with the naming index. User's report: *"it randomly says I can't do
that when I don't ask it anything"*, in find mode *"it does find the bottle but
immediately says nothing to your right"*, and *"it's still a cluster ... when I
ask find bottle it should find bottle and not do anything else for some time"*.

**Both symptoms reproduced deterministically** by POSTing glue-word soup to the
running server:

```
/agent [abstain] 'the is my on' -> - ask=unknown (1907 ms)
   error: rejected action {'tool': 'check', 'args': {'left': 'on'}}
```

Three compounding faults, all now fixed:

1. **The router was being fed noise.** `voice_listener.dart` sent EVERY
   unparseable recognizer result to `/agent` — 26 round trips in 2.5 min on the
   walk. Vosk is grammar-constrained: it cannot return "I didn't understand",
   only its best match over the trained phrases, for any audio at all. Ambient
   speech, a door closing, and the app's own TTS all arrive as word-soup. The
   router (measured **55% out-of-scope over-trigger**, paper §7) turned some
   into `check(...)` and the rest into a spoken abstention nobody asked for.
2. **No echo gate.** The phone's speaker reaches its own mic. `_repeatedTooSoon`
   caught exact repeats but not a phrase that force-matches into a DIFFERENT
   command — which is how "Bottle on your right" became a directional query.
3. **No ordering.** `Speaker` had preemption (on-demand cannot be cut by
   routine, "very close" cuts through) but nothing about *order*, so any
   capability spoke the instant it fired.

### What was added

- **`speech_policy.py` / `lib/logic/speech_policy.dart`** (new, mirrored, pure
  logic). Four priorities — `SAFETY > RESPONSE > CONFIRM > ROUTINE` — plus
  **FOCUS**: a task the user asked for owns the speech channel until it
  finishes. While focused, routine guidance is DROPPED (never queued: stale
  guidance spoken late is worse), informational read-outs wait whoever
  triggered them, the user's own steering commands still go through (being
  unable to interrupt is how an assistive device becomes frightening), and
  safety speech is never gated. `find` takes an OPEN-ENDED hold — it runs until
  the target is located — released by the engine's auto-return to walk, by
  `walk`/`stop`, or by the 90 s cap. Every hold expires; one that never
  released would silence the app.
- **`is_plausible_request()`** — the floor before the router is consulted: ≥2
  words AND ≥1 capability keyword or object name. `"the is my on"` never leaves
  the phone now.
- **`Speaker.isEchoing`** — recognizer results are dropped while the app is
  speaking plus a 900 ms tail. Belt-and-braces expiry so a missing TTS callback
  cannot deafen the app permanently.
- **`solicited` flag threaded through `_dispatch`/`_askAgent`.** True only when
  the user deliberately opened a dictation window with the trigger word. An
  unsolicited route may RUN a capability but **may never speak an abstention** —
  silence is the right answer to a question nobody asked. Also gates commands,
  not just speech: `read` pauses the camera stream and `find` changes mode, so
  a spurious trigger costs more than a spurious sentence.
- **3 s minimum gap** between unsolicited router calls.
- **`/agent` now logs the utterance and what it became.** The walk could not be
  diagnosed from the old log — 26 POSTs, not one word of what was heard.
  `VoiceListener.transcripts` keeps the last 40 on-device, `echoDropped`
  counts what the gate ate.

Tests: `test_speech_policy.py` (22) + `test/speech_policy_test.dart` (23,
including a table-parity assertion against the Python categories).
**294 Python / 183 Dart**, `flutter analyze` clean apart from the 3 pre-existing
`avoid_print` infos.

### Second walk, same night — the log named the real culprit

Symptoms after the first fix: *"better, but again issue with find mode, it finds
it but the voice gets interrupted by something else and it goes away"*, *"it
keeps saying nothing at left for some reason"*, and *"it randomly started
finding phone"*. This time `/agent` logging existed, and it settled the question
in one screen — **31 calls, and the model was inventing arguments nobody said**:

```
'door'        -> check(left)      <- the "nothing at left"
'the cup'     -> check(left)
'bag'         -> check(left)
'the person'  -> check(right)
'cup phones'  -> check(ahead)
'the mobiles' -> find(cell phone) <- the "randomly started finding phone"
'is'          -> describe   'bed' -> recall(bed)   'tv' -> recall(tv)
```

**FIX A — argument grounding (`agent.argument_is_grounded`).** The authority
boundary validated the tool name and the enum, so `check(left)` was *well
formed*; what was wrong with it was its **provenance**. New rule: the model may
CHOOSE a capability, it may not INVENT the capability's argument.
- Applied to **direction** and **onoff** args, NOT to class names, and the
  asymmetry is the design. `left/right/ahead` ARE the words a person says —
  there is no paraphrase of "left" that is not "left", so an ungrounded
  direction is fabrication. A class argument is exactly where paraphrase lives
  ("the exit" -> door, "my water bottle" -> bottle); grounding those verbatim
  would delete the capability tier 1 exists for (paraphrase 0% -> 47%).
- Required arg ungrounded -> reject the action. Optional arg ungrounded -> keep
  the capability, drop the invention (an unrequested "sonar off" degrades to a
  toggle).
- Verified live: `'door'` and `'the cup'` now abstain; `'anything on my left'`
  still routes. `test_agent.ArgumentGroundingTest` pins every field utterance.

**FIX B — focus must cover the SENTENCE, not the state change.** The find
announcement was cut off mid-word because `GuidanceEngine` auto-returns to walk
the instant it announces the target, and the code released focus on that
transition — freeing the channel before the user had heard the answer.
`SpeechPolicy.extend()` (mirrored) pushes a hold out to cover the estimated
speaking time and never shortens one; `_say` extends on every `kResponse`.

**FIX C** — a single force-matched token is never a request, on **any** path in
(`_askAgent` guards the dictation path too, which had no floor — that is how
bare `'door'`/`'is'`/`'bed'` reached the router at all).

⚠ **The frozen eval is now stale.** Argument grounding changes what the router
accepts, so `paper/` T3-T6 no longer describe the shipped code. Expect
over-trigger to IMPROVE (grounding rejects exactly the fabricated-argument
class). Re-run all four configs and record it in `EVAL_PROTOCOL.md` §8 as a
post-freeze amendment before quoting those tables again.

⚠ **Known residual risk, deliberately not designed away:** ambient human speech
that happens to contain a content word still clears the floor and can reach the
router. The trigger word exists precisely so free speech is deliberate; the
unsolicited path is a convenience the eval says over-triggers. It is kept
because it is what makes an unrehearsed paraphrase work with no server round
trip in the user's head — but the next walk's log will show whether it earns
its place, and that is now decidable from evidence rather than argument.

## Photo capability + open conversation (2026-08-03)

User decision: the paper is **submitted**, so evaluation drift is no longer a
constraint — "we can explore more things and revert if it doesn't work".

**`photo` capability.** Voice "take a picture" / "take a photo" / "photo", or
the features page (generated from `kTools`, so it appears there for free).
`main.dart._takePhoto()` uses the same pause/capture/resume dance as
`_readText()` — the detection stream and a still capture cannot both own the
camera — and saves via **`gal ^2.3.3`** (new dep) into a *BlindAssist* album in
the phone's **gallery**. Gallery, not app-private storage, is the whole point:
the user cannot review the photo, so its only purpose is handing it to a
sighted person, and it must appear where every other photo does. Permission
refusal is spoken ("Photo not saved, permission denied") — a user who cannot
see the dialog has no other way to find out. Registered in `agent.TOOLS` +
`Hooks.take_photo`; parsed in both `voice.py` / `voice_commands.dart` BEFORE
the object queries so "take a picture of the chair" is not dragged into find,
and AFTER `read` so "read the text in the picture" is still OCR. `photo` is
`INFORMATIONAL` in both speech policies.

**Open conversation (`_SYSTEM` rewritten).** Before, `"hello how are you"`,
`"what is the capital of france"` and `"who won the world cup in 1998"` all
returned **abstain** — the prompt clamped the model to the state block, so
anything off-topic became "Sorry, I can't do that". Now general knowledge,
small talk, jokes and questions about the app are answered normally, and the
prompt carries an **app description** so "what can this app do" gets a real
answer. `MAX_SAY_CHARS` 240 -> 400 (that question has a longer honest answer;
"stop" already exists for a reply the user does not want to sit through).

**The two hard limits were kept, and they are what makes allowing the rest
safe.** The model may talk about the world; it may never (1) claim anything
about the user's SURROUNDINGS — the state block stays the only source for what
is in the room — or (2) give walking, crossing or safety instructions, which
route to `path`/`check`. Guidance strings still originate in decision.py.

Measured after the rewrite (`llama3.2:3b`):

| utterance | result |
|---|---|
| hello how are you | chat, sensible greeting |
| who wrote romeo and juliet | "William Shakespeare." |
| what is 12 times 8 | "Ninety-six." |
| tell me something interesting | real trivia, correct |
| what can this app do | accurate app description |
| which way should i cross the road | routes to `path` — the safety rule holds |
| where is the eiffel tower / how far is the moon | "I cannot see that" |
| what is the capital of france | fails; "capital city of japan" answers fine |

**Known and accepted:** *spatial phrasing* ("where is...", "how far is...") is
deflected by the surroundings rule. That is the correct trade — the model
cannot reliably separate "where is the Eiffel Tower" from "where is my cup",
and the cup MUST stay a recall query. The France miss is 3B smallness, not
prompt logic; a bigger local model fixes it at ~6 s/query (gemma2, measured
2026-08-01), which is not worth the latency.

⚠ Chat replies are only ever SPOKEN on the solicited path — say "assistant"
first. Ambient recognizer noise still cannot make the phone talk; that is what
the 2026-08-02 arbitration work bought and it is unchanged.

Test counts: **307 Python / 189 Dart**, all passing.

### Still open

- **START HERE NEXT SESSION: `flutter install` has NOT been run for the photo +
  conversation build.** Everything is coded, tested and analyzed clean, but the
  phone dropped off USB before the install completed, so the handset is still
  running the 2026-08-02 arbitration build (focus/echo gate/grounding — that
  one IS installed and was walked). Steps: connect the phone, `flutter devices`
  to confirm `RZCR906FDTD`, then
  `cd blindassist_app && flutter install -d RZCR906FDTD`. Start the server
  first — see the note below about how.
- **Run the server DETACHED, not as a Claude background job.** Two background
  jobs were reaped mid-session, killing the server while the user was walking.
  What works:
  `Start-Process -FilePath C:di\object_detection_blindenv-gpu\Scripts\python.exe`
  `-ArgumentList '-u','infer_server.py','--agent-model','llama3.2:3b'`
  `-WorkingDirectory C:di\object_detection_blind -RedirectStandardOutput <log>`
  `-RedirectStandardError <errlog> -WindowStyle Hidden`.
  Always `venv-gpu`, never `venv` (CPU torch = ~750 ms/frame).
- **Then verify on the handset, in this order:** "take a picture" lands in the
  gallery (and the permission prompt is handled); say "assistant" then a
  general question and confirm it answers instead of abstaining; re-check the
  2026-08-02 fixes still hold (find announcement not clipped, no unrequested
  "nothing on your left"); and confirm the naming index gives stable names
  rather than flickering ones.
- The hotspot IP changes between sessions (10.250.253.247 -> 172.17.77.158 in
  one evening). UDP discovery handles it; only the baked fallback in
  `config.dart` goes stale.
- The webapp worker-loop refactor still has no runtime smoke test (unit tests
  cover its parts, not the loop).
- Nothing has been committed for two sessions — the naming head, the speech
  policy, argument grounding, photo and open conversation are all uncommitted.
- ⚠ **The labelled crops live under `test_output/`, which is gitignored** — the
  user's manual work has no backup. `name_index.npz` IS tracked (repo root), so
  the *product* is safe; the raw crops are not. Un-ignoring
  `test_output/crops/` is the user's call: photos of their own rooms, and the
  GitHub remote's visibility was never confirmed.

Test counts at the end of 2026-08-03: **307 Python / 189 Dart**, all passing;
`flutter analyze` clean apart from the 3 pre-existing `avoid_print` infos in
detector.dart.

## Production-readiness pass: five defects from the first real walk (2026-09-05)

User walked the 08-03 build and reported: read mode cut off mid-page, obstacles
"weirdly said", no memory of the door, "randomly says clock mode", and the
agent underperforming. All five reproduced and fixed; **317 Python / 203 Dart
tests pass**, `flutter analyze` clean apart from the 3 pre-existing
`avoid_print` infos. APK rebuilt and installed on RZCR906FDTD.

**The one that caused three of the symptoms — raw frames were breaking
perception.** The app POSTed uncompressed YUV420: **506 KB/frame**, measured on
the hotspot at **320-510 ms to upload** against ~171 ms for both models plus the
namer, under the 1.2 s timeout. logcat was full of `BlindAssist remote infer
timeout`. A dropped frame breaks `GuidanceEngine._streaks` two-frame
persistence — hence erratic announcements AND the door never accumulating
enough sightings to be remembered. `recall()` was never broken.
- Fix: `MainActivity.kt` gains a `blindassist/frame` method channel doing
  hardware `YuvImage.compressToJpeg`; `lib/frame_codec.dart` calls it and
  **falls back to raw planes permanently after one failure** (retrying per
  frame would pay the channel round trip forever to rediscover a broken
  encoder). `infer_server.py` accepts a `jpeg` part or the old `y`/`u`/`v`, and
  logs which — so a silent fallback is visible. Measured **506 KB -> 26 KB**.
- Profiling script pattern worth reusing: synthesise the phone's YUV planes
  from a clip frame and time each stage separately. That is what showed the
  models were never the problem.

**`trusted_name` now travels end to end.** `Namer.apply` renamed
refrigerator->wardrobe but never marked the detection trusted, so
`_spoken_name` re-gated it on YOLO confidence — the signal EVALUATION.md 6.2
already records as falsified — and said "Obstacle" for an object the index had
identified correctly. Flag now flows namer -> server JSON -> `Detection` ->
`ObjectInfo` -> spoken word. Legacy 0.8 gate kept for UN-renamed COCO
detections only, with its falsified status documented at both definitions.

**Clock bearings were ~2x off (the long-open Defect 2), in the DEFAULT config.**
`_CLOCK_HOURS = (10,11,12,1,2)` spans 120 deg across a ~65 deg camera. Now
derived from `CAMERA_FOV_DEG = 65.0` / `cameraFovDeg`, giving 11-12-1.
⚠ Consequence to keep stated: at this FOV clock bearings CANNOT be finer than
left/center/right. The value is the O&M vocabulary, not resolution.

**`[unk]` was being thrown away — the "randomly says clock mode" cause.** The
Vosk grammar carries an explicit `[unk]` token (the recognizer saying "I could
not place this sound") and `_clean()` **stripped the markers and kept the
rest**, so `"[unk] [unk] clock mode"` looked exactly like a deliberate command.
The grammar path had no floor at all while the free-speech path had three.
Now `parseRecognizerResult` / `recognitionIsUsable` weigh the ratio
(`kMaxUnknownRatio` 0.5) — public and pure, so it is unit-testable without a
mic (`test/voice_noise_test.dart`).

**`_readText` bypassed the speech policy entirely.** Called `_speaker.say`
directly, so it never took the `read` focus, then `finally` released a hold it
had not taken — and since `say()` does not await completion, the camera stream
resumed while the text was still being read. Now goes through `_say(...,
kResponse, 'read')`, which extends focus to cover the speaking time. The stream
still resumes immediately ON PURPOSE: a very-close obstacle while the user
stands reading is worth interrupting for; going blind for a page of text is
worse than a cut sentence. `_setClock` had the same bypass, also fixed.

**Also:** a NUL byte at `decision.dart:313` (a composite map-key separator) made
grep/ripgrep treat the whole file as BINARY and return nothing — it produced
false negatives during this very investigation. Replaced with `|`.

### Room-walk evaluation (`test_output/room_walk_20260905.mp4`, 1080x1920, 42.5 s)

Pulled off the phone over adb. 424 frames sampled through the real pipeline:
72% carried a detection, 15 walk announcements, door dominant (158 frames — the
custom model is the star), object memory correct for bed/bottle/chair/couch.

⚠ **The naming head made 0 renames on this room.** It abstained everywhere,
nearly always `ambiguous`: similarities were high (0.75-0.90) but margins tiny
(0.005-0.11) against `MIN_MARGIN` 0.15. The index was labelled from the eight
OLDER clips; this is a new room, so the crops are out of distribution. That is
the DESIGNED behaviour (the stairs precedent — decline rather than guess), but
it means **§4.9's benefit is room-specific until labelled**. To get correct
names in this room, run `harvest_crops.py` over
`test_output/room_walk_20260905.mp4` and repeat the labelling pass. This is the
single highest-value next step for perceived quality.

### Still open after this session

- **Not committed.** This session plus the previous two are all uncommitted.
- The agent quality complaint is NOT addressed — `llama3.2:3b` still measures
  55% out-of-scope over-trigger. Argument grounding helped; the frozen eval
  tables still do not describe the shipped router (see the 08-02 warning).
- The JPEG path is verified against the server by direct POST (26 KB, HTTP 200,
  `trusted_name` present) but **NOT yet on the handset** — proof will be
  `/infer ... jpeg ->` in the server log rather than `raw`.
- Server must be started detached from `venv-gpu` (see the 08-03 note); two
  background jobs were reaped mid-session once before.

## Second field walk: find was structurally broken, and voice input was deaf (2026-09-05, later)

User walked the morning build: "not hearing me properly when I say read, find";
"in find person I see on the screen it can see person but it's not telling, it
just keeps saying finding person"; "walk mode is already mediocre at best, at
least make read, find and the other features better".

**JPEG transport is CONFIRMED on the handset** — 283 `/infer ... jpeg` frames,
0 raw. But the walk exposed three deeper faults.

### 1. Find required evidence it could never get

`_update_find` needed `persistence = 2` CONSECUTIVE frames. That threshold was
chosen on the laptop at ~6 FPS, where two frames is 0.3 s. The phone runs at
**1.8-2.3 FPS**, so it demanded a full second of unbroken detection.

Reproduced exactly by replaying the user's own room clip at 2 FPS: the person's
detection runs were `[1,1,1,1,2,2]` frames, so **four of six sightings never
announced**, and because `_absent` kept incrementing through the gaps the engine
announced "Person not visible" and "Still looking for person" with the person on
screen. First correct answer came at **19.5 s**.

Fixed by making the evidence ASYMMETRIC, which is the real insight:
- `find_persistence = 1` — the user ASKED; announcing a misdetection costs one
  wasted look, while silence about a visible object reads as a broken app, and
  a blind user cannot check the screen to tell which happened.
- `absence_grace = 2.5` SECONDS, not frames — the claim "it is not there" needs
  more evidence than "it is there", and a frame count means different things at
  2 FPS and 6 FPS.
- `miss_decay = 0.5` — streaks now DECAY instead of resetting to zero, so an
  object detected on alternate frames accumulates. A one-frame ghost still
  decays away without reaching walk's `persistence = 2`, so this does not make
  false warnings likelier (pinned by a test).

After: **12/12 classes in the user's room answer on the first frame, 0 false
"not visible"**. Was 19.5 s and two wrong messages.

### 2. Voice input: I over-corrected the noise floor that morning

`kMaxUnknownRatio` rejected any result whose `[unk]` tokens were half or more.
**"read", "walk", "stop" and "repeat" are single words**, so one stray token put
them at exactly 0.5 and they were dropped. I had made the app deaf to precisely
the commands the user needed.

The floor is now set PER COMMAND by the cost of being wrong:
- `kSettingCommands` {clock, zones, sonar, mute} require `unknownCount == 0` —
  a spurious toggle silently changes behaviour a blind user cannot see.
- Everything else accepts `unknownRatio <= 0.5` — the user hears the result
  immediately and can repeat it, so a false REJECT is the worse error.

### 3. The echo gate was time-based, so the app was deaf while talking

`isEchoing` blocked the microphone for the whole of every announcement plus a
900 ms tail. In walk mode that is most of the session — and it is exactly when a
user wants to interrupt. Now content-aware: `isProbablyEcho(heard, lastSpoken)`
(pure, mirrored in `speech_policy.py` / `speech_policy.dart`) rejects only text
whose EVERY word we just said. Our guidance never contains a bare command word,
so "read" gets through while our own "Door at 11 o'clock" coming back does not.

### 4. Unsolicited routing is now OFF by default — on the project's own criterion

CLAUDE.md said the unsolicited path was kept because "the next walk's log will
show whether it earns its place, and that is now decidable from evidence rather
than argument". The log: **two unsolicited calls, both grammar-forced noise
("many plant", "my left"), both abstained, both 6.8-8.0 s.** It did not earn it.
`kRouteUnmatchedSpeech = false` in config.dart. The trigger word ("assistant")
is unaffected — that path is deliberate.

### 5. `_takePhoto` had the same focus bug as `_readText`

Both called `_say(..., kResponse, tag)` — which extends the hold to cover the
sentence — and then released it in `finally`, freeing the channel before the
user had heard the answer. Neither releases now; the hold expires on its own.

### GPU contention is the real latency ceiling, and it is a user decision

`llama3.2:3b` and the two YOLO models share 4 GB of VRAM:

| | agent latency | server compute |
|---|---|---|
| GPU idle | 485-1140 ms | ~171 ms |
| frames streaming | **6766-8016 ms** | **266-468 ms** |

Every mid-walk question timed out at the old 5 s. Timeout raised to 12 s, but
the honest fix is not to run both on one GPU. Options for the user: drop
`--agent-model` (roughly doubles frame rate, loses paraphrase + chat), or try
`llama3.2:1b` (already pulled, 1.3 GB).

### Room-specific naming, restated

Still 0 renames in this room; 48% of detections carry a trusted name, all of
them from the custom door/dustbin model. The 2 remaining generic "obstacle"
warnings and the stray `refrigerator`/`toilet` labels are exactly what
harvesting and labelling crops from `room_walk_20260905.mp4` would fix. That
remains the highest-value next step for perceived quality.

Test counts: **325 Python / 215 Dart**, analyze clean apart from the 3
pre-existing `avoid_print` infos.

## Router model switched to llama3.2:1b (2026-09-05, user decision)

The 3b model was not slow because it is 3b — it was slow because it shares one
4 GB GPU with yolov8s and the door model. Measured with a live frame stream
posting to `/infer`:

| model | tier-1, GPU idle | tier-1, frames streaming |
|---|---|---|
| llama3.2:3b | 485-1140 ms | **6766-8016 ms** (timed out on the phone) |
| **llama3.2:1b** | 266 ms median / 672 ms worst | **281 ms median / 484 ms worst** |

`--agent-model` with no value now gives `llama3.2:1b`. Run the server as:

    venv-gpu\Scripts\python.exe -u infer_server.py --agent-model llama3.2:1b

**Quality, measured on 20 utterances (`router_check` pattern, regenerate from
the scratchpad script) — the honest trade:**

| category | 1b | note |
|---|---|---|
| canonical commands | 6/6 | tier 0, never reaches the model |
| paraphrase | 5/6 | missed "what is around me right now" -> answered as chat instead of `describe` |
| out-of-scope | 5/5 abstained | battery, capital of Japan, call my mother, play music, what time is it |
| **grammar noise** | **0/3** | "the is my on", "many plant", "my left" all became `walk` |

So 1b is WORSE at abstaining on word-soup, where 3b abstained on the same
inputs. Two reasons that is acceptable here, and one reason to keep watching it:

1. Noise now largely cannot reach the router at all. `kRouteUnmatchedSpeech` is
   false, so the unsolicited path is closed, and `is_plausible_request` rejects
   "the is my on" outright (no content word). Only the deliberate trigger-word
   path remains, and only "many plant" / "my left" clear the floor there.
2. The capability it invents is `walk`, which merely returns to walk mode. It
   speaks no perceptual claim, so the authority boundary is intact.
3. ⚠ Worth re-checking if the trigger word ever starts firing spuriously: with
   1b the failure mode is a wrong capability rather than an abstention.

This does NOT change the paper's evaluation tables, which were run on 3b and
are reported as such. Any re-run must state the model.

## Third walk: the policy was eating commands, and OCR never had the pixels (2026-09-05, night)

User: "not hearing me properly when I say read, find"; "my suitcase is shown as
both dustbin and suitcase"; "again no memory of laundry basket"; "read keeps
saying no text found"; "change the voice to a different accent".

Four of the five were misattributed. None of them was a hearing problem.

### 1. The speech policy was silently dropping commands the user SAID

`speech_policy` line "if kSteering.contains(action) return solicited; return
false" meant any non-steering capability was refused while another held focus —
**including one the user had just spoken**. The field log says it plainly:

    policy: dropped "describe" (focus=photo, solicited=true)
    policy: dropped "check"    (focus=describe, solicited=true)

Heard correctly, parsed correctly, thrown away. To someone who cannot see the
screen that is indistinguishable from not being heard, and it is exactly the
failure the module's own class comment warns about ("being unable to interrupt
is how an assistive device becomes frightening").

`allow_command` now returns `solicited`: a guess from the dialogue layer is
still gated, a command the user spoke never is. `allow_speech` matched it —
lowered from RESPONSE to CONFIRM, because letting the capability run and then
refusing to speak its result leaves silence with no explanation. Mirrored,
and pinned by a test that walks every capability against every focus holder.

### 2. There was no cross-model deduplication ANYWHERE

`infer_server` concatenated yolov8s's detections and the custom model's. Each
NMSes only its own output, so one object came back twice under two names — the
suitcase. Device log, one frame:

    suitcase@0.91 backpack@0.70 dustbin@0.81 dustbin@0.70 dustbin@0.46

New `detect_merge.py` (pure, 15 tests). Two decisions worth keeping:

- **Overlap is IoU, never containment.** Containment is the obvious test for "a
  dustbin box inside the suitcase box" and it is dangerous: measured on the
  user's own room clip, the pairs it flags include **person inside bed**. A
  person standing in front of a bed is contained by it, and nesting is also how
  a bottle on a table looks. `person` is additionally hard-protected.
- **Confidence compared as margin above each model's OWN floor.** COCO is
  thresholded at 0.6 and the custom model at 0.4, so raw values are not
  comparable; `(conf - floor) / (1 - floor)` is. A committed rename from the
  naming head outranks both, being the only calibrated namer in the pipeline.

Also `_CUSTOM_FLOOR` dustbin 0.4 -> **0.6**. The 0.4 was justified for DOORS
("a partial doorway lives in the 0.4-0.5 band") and dustbin inherited it. The
0.81 false positive survives and is a NAMING problem, not a threshold one.

### 3. OCR was reading 480p

`ResolutionPreset.medium` drives BOTH the streamed frames and `takePicture()`.
Detection never cared — the server letterboxes to 640 regardless — but `read`
was OCR-ing text at 480p and ML Kit returned nothing every time. Now `high`
(720p, 2.25x the pixels), which costs little since frames go up as JPEG. Also
added autofocus + a 700 ms settle before the capture: firing `takePicture()`
straight after `stopImageStream()` inherits whatever focus the streaming path
left, and a blurred page yields no blocks at all — indistinguishable from an
empty one. The capture now logs `previewSize -> N chars`, so if it still fails
the log says whether it is resolution or focus.

### 4. Accent picker

`kAccents` in settings.dart (en-IN default, plus GB/US/AU/IE/ZA) + a chip row in
the features page that applies AND speaks a sample immediately — the point of
the setting is how it sounds, and the user cannot read the list. Deliberately
LOCALES, not voice names: which voices exist differs per phone, so a hardcoded
name would silently fall back. `Speaker.applyVoice` checks
`isLanguageAvailable` first and keeps the current voice if absent.

### 5. Laundry basket — not a memory bug

It is never DETECTED, so nothing ever reaches the object memory. YOLO calls it
"handbag", which is not in TARGET_CLASSES, and the naming index abstains in this
room. `recall` was answering correctly.

**Room crops are now harvested and waiting**: `test_output/crops_room/`, 196
crops in 24 guess-folders from `room_walk_20260905.mp4` — including **4 in
`handbag/`, almost certainly the laundry basket**, plus 12 `dustbin` and 12
`suitcase` (the confusion pair) and hallucinated `cat`/`dog`/`stairs` for
`_ignore`. Labelling those into `test_output/crops/<label>/` and re-running
`build_name_index.py` is what fixes the laundry basket, the suitcase-as-dustbin
name, and the remaining generic "obstacle" warnings. It is the user's 20-40 min
and it is now the single highest-value action left.

Test counts: **342 Python / 217 Dart**, analyze clean apart from the 3
pre-existing `avoid_print` infos.

