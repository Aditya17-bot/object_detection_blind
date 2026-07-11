# BlindAssist — Android app plan (the FINAL PRODUCT)

User requirements (fixed 2026-07-11):
- **Android app is a must** — the phone runs everything, no laptop.
- **Minimal interface** — users are blind; the screen barely matters.
- **Voice controls everything** — users can't type. Speech + sonar out,
  voice in. The current web UI stays as the dev/demo tool.

## Recommended stack: Flutter + on-device models

| Piece              | Desktop prototype        | Android equivalent            |
|--------------------|--------------------------|-------------------------------|
| Camera             | OpenCV                   | `camera` plugin (frame stream)|
| Detection          | yolov8s.pt + custom .pt  | both exported to **TFLite**, run with `tflite_flutter` (yolov8n int8 @ 320-416 px for speed) |
| Position analysis  | position.py              | port to Dart (pure logic, ~100 lines) |
| Decision logic     | decision.py              | port to Dart (pure logic, ~250 lines) |
| Speech out         | pyttsx3                  | `flutter_tts` (Android TTS, offline) |
| Voice in           | Vosk + laptop mic        | **vosk_flutter** — same model file, offline |
| Sonar              | WebAudio in browser      | stereo beeps via `just_audio`/low-level audio, same pan/tick rules |
| Command parsing    | voice.py parse_command   | port to Dart (~40 lines)      |

Why Flutter: spec already names it; single codebase; every piece above has
a maintained plugin. Why NOT python-on-Android (Kivy/BeeWare): camera + TTS
+ STT support is poor; we'd fight the platform instead of building.

The pure-logic discipline pays off here: position.py, decision.py and
parse_command have NO cv2/YOLO/audio imports, so the Dart port is a direct
translation, and the 61 unit tests translate with them (same inputs, same
expected strings — instant correctness check for the port).

## Build phases

- **A0 — model export (do first, on laptop):**
  `yolo export model=yolov8n.pt format=tflite int8` (and the custom model).
  Sanity-check the TFLite outputs against the .pt outputs on bus.jpg.
  NOTE: mobile uses yolov8**n**, not s — phones need the speed; revisit if
  a mid-range phone turns out to handle s.
- **A1 — skeleton:** Flutter app, camera preview, TFLite inference drawing
  boxes on screen. Hardest phase (YOLO output decoding in Dart); everything
  after it is porting known logic. Target: ≥5 FPS on the user's phone.
- **A2 — brains:** port position.py + decision.py + their tests to Dart.
- **A3 — voice out:** flutter_tts announcements (same anti-spam engine).
- **A4 — voice in:** vosk_flutter with the same grammar; app OPENS listening
  — "walk mode", "find bottle", "describe" — no typing anywhere.
- **A5 — sonar:** stereo beeps, pan from center_x, tick rate from proximity.
- **A6 — blind-first UX:** starts directly in Walk Mode + listening; one
  full-screen tap = repeat last announcement; long-press = describe scene;
  TalkBack labels on everything; volume keys as backup mute. Field test
  with the phone protocol from EVALUATION.md.

## Open decisions (ask the user when starting)

1. Minimum phone to target (their own Android? version?).
2. Camera resolution/imgsz trade-off after first on-device FPS numbers.
3. Whether dustbin/door retraining (more own-photos + room-background
   negatives; stairs re-enable) happens before or after the port.

## Prototype quirks to NOT copy to Android

- "stairs" class disabled (0.072 recall — see position.py comment).
- Web-UI clip looping, --headless flags etc. are dev-harness only.
- pyttsx3's replace-pending-message rule DOES carry over (flutter_tts:
  always `stop()` before `speak()` — stale guidance is never spoken).
