# BlindAssist — quick reference

Camera-based assistive prototype: detects indoor objects, works out direction
+ closeness, and decides short spoken guidance. Full design in `PIPELINE.md`
and `CLAUDE.md`; evaluation results (strengths & limits) in `EVALUATION.md`.

## Work here (LOCAL copy)

Always work in this folder, **not** the Google Drive copy:

```powershell
cd C:\Users\rober\OneDrive\Desktop\object_detection_blind
.\venv\Scripts\activate
```

`G:\My Drive\object_detection_blind` is backup-only (its `venv` is stale —
never activate it; running code off Drive is slow and flaky).

## Back up at the end of every session

```powershell
.\sync_to_drive.ps1
```

Mirrors the project to `G:\My Drive\object_detection_blind` (skips venv,
__pycache__, .git).

## Run things

```powershell
# THE APP with web UI — video, mode controls, announcement feed, sonar
# beeps, VOICE COMMANDS ("find bottle" / "walk mode" / "describe")
# open http://127.0.0.1:5000 after it starts
python webapp.py
python webapp.py --no-voice          # without the microphone listener

# PHONE TESTING (phone = camera AND screen/voice; laptop just computes):
# 1. phone: start IP Webcam app, note its URL
# 2. laptop:
python webapp.py --source http://<phone-ip>:8080/video --host 0.0.0.0
# 3. phone browser: open the "On your phone -> http://..." URL it prints,
#    turn ON "Speak on this device", turn OFF "Voice (laptop)", earphones in.
#    (First run: click Allow on the Windows firewall prompt.)

# Console version (phase 4) — same pipeline, OpenCV window
# keys: q quit, s snapshot, d describe scene aloud
python phase4_assist.py

# Phone as camera (IP Webcam app; ask the app for the current URL)
python phase4_assist.py --source http://<phone-ip>:8080/video

# Find Mode, spoken
python phase4_assist.py --mode find --target bottle

# Quieter / faster voice
python phase4_assist.py --rate 200
python phase4_assist.py --mute   # print-only dry run

# Reproducible recorded-clip tests (video-time clock, no speech):
python phase3_detect.py --source "test_output\clip.mp4" --headless
# announcements land in test_output\*.log + one annotated jpg each

# Earlier stage demos
python phase1_detect.py          # raw detection boxes
python phase2_detect.py          # + position grid / proximity colors
```

## Tests

```powershell
python -m unittest -v    # position + decision + speech + webapp + voice (58 tests)
```
