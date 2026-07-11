# BlindAssist — Project Pipeline

Camera-based assistive app for visually impaired users: detects common indoor
objects, works out their rough direction and closeness, and speaks short
guidance messages.

## Processing pipeline (per frame)

```
 PHONE CAMERA (IP Webcam app)          or  recorded clip.mp4  /  laptop webcam
        │  http://<phone-ip>:8080/video
        ▼
 ┌─────────────────────┐
 │ 1. FRAME CAPTURE    │  OpenCV (cv2.VideoCapture) grabs frames
 └─────────┬───────────┘
           ▼
 ┌─────────────────────┐
 │ 2. OBJECT DETECTION │  YOLOv8s (yolov8s.pt), conf ≥ 0.6
 │                     │  → boxes: class name, confidence, x1 y1 x2 y2
 └─────────┬───────────┘  keep only our 18 target classes
           ▼
 ┌─────────────────────┐
 │ 3. POSITION ANALYSIS│  position.py → analyze_box()
 │    (phase 2, DONE)  │  • 3×3 grid zone from box center ("left", "top right")
 │                     │  • proximity from box area (very close/close/medium/far)
 │                     │  • obstacle vs findable class split
 └─────────┬───────────┘  → ObjectInfo per object, with spoken phrase
           ▼
 ┌─────────────────────┐
 │ 4. DECISION LOGIC   │  decision.py → GuidanceEngine.update(infos, now)
 │    (phase 3, DONE)  │  Walk Mode: ONE most important obstacle
 │                     │    (closest, then most central; far ignored)
 │                     │  Find Mode: asked-for class, biggest match wins
 │                     │  Anti-spam: 2-frame persistence, 3 s repeat
 │                     │  cooldown, 1.5 s min gap, escalation override
 └─────────┬───────────┘  → ONE message string per moment, or nothing
           ▼
 ┌─────────────────────┐
 │ 5. VOICE OUTPUT     │  speech.py → Speaker (phase 4, DONE)
 │    (phase 4, DONE)  │  pyttsx3 on its own thread; never blocks the
 │                     │  camera loop; latest message replaces a stale
 └─────────────────────┘  waiting one. Full app: phase4_assist.py
```

## Stage-by-stage status

| Stage | Status | Where |
|---|---|---|
| 1. Capture | DONE | `phase1_detect.py` / `phase2_detect.py` (`--source` takes webcam, URL, or file) |
| 2. Detection | DONE | YOLOv8s chosen after nano-vs-small comparison (`compare_models.py`); ~7 FPS |
| 3. Position | DONE — 13 unit tests + verified on recorded room videos | `position.py`, tests in `test_position.py`, demo in `phase2_detect.py` |
| 4. Decision | DONE — 23 unit tests + verified on all 4 recorded clips | `decision.py`, tests in `test_decision.py`, demo in `phase3_detect.py` |
| 5. Speech | DONE — 4 unit tests (fake engine) + spoken end-to-end on couch clip | `speech.py`, tests in `test_speech.py`, full app in `phase4_assist.py` |

## Two user modes

- **Walk Mode** — continuous obstacle awareness. Announces only the single
  most relevant obstacle at a time ("Obstacle ahead", "Chair on right").
- **Find Mode** — user asks for one object class ("find bottle"); app
  announces its location ("Bottle top right") or "Target not visible".

## Planned innovation features (plug in around stages 4-5)

- **Voice commands** (Vosk, offline) — "find bottle", "walk mode", "describe"
  feed mode switches INTO the decision stage.
- **Sonar audio mode** — second audio output ALONGSIDE speech: stereo-panned
  beeps (pan from the object's `center_x`, tick rate + pitch from proximity).
- **Smart scene summary** — DONE early (pure decision logic):
  `decision.summarize_scene()` groups all current detections into one
  sentence ("A dining table ahead, 2 chairs on your left, a person on your
  right"); press `d` in phase3_detect.py. Voice command "describe" will
  trigger it later.

## Development / workflow pipeline

1. Code and test in the local project folder (OneDrive path, works offline).
2. Verify: `python -m unittest` (position logic), recorded clips in
   `test_output/` (reproducible), or live phone stream (IP Webcam app).
3. Back up: run `.\sync_to_drive.ps1` → mirrors project (minus venv) to
   `G:\My Drive\object_detection_blind`.
4. Future: friend fine-tunes a door + dustbin model on Colab
   (see `finetune_handoff.md`) → drops in as a second `.pt` at stage 2.

## Known model limits (from real-room video tests, 2026-07-10)

- Dustbin is not a COCO class → detected as "toilet" (right warning, wrong
  name). Doors also not in COCO → ignored. Both are the fine-tune targets.
- Low light + motion blur degrade detection (suitcase misread, dark chair
  missed). Lighting matters for the live test protocol.
