# BlindAssist — quick reference

Camera-based assistive prototype: detects indoor objects, works out direction
+ closeness, and decides short spoken guidance. Full design in `PIPELINE.md`
and `CLAUDE.md`; evaluation results (strengths & limits) in `EVALUATION.md`.

## Work here

```powershell
cd C:\adi\object_detection_blind
.\venv\Scripts\activate       # CPU torch — the known-good fallback env
.\venv-gpu\Scripts\activate   # CUDA torch 2.6.0+cu124 — 12x faster inference
```

Both envs exist on purpose: `venv/` vanished once to OneDrive's free-up-space,
so it stays as a working fallback. Only `venv-gpu` uses the RTX 3050.

## Back up at the end of every session

```powershell
git push origin main
```

Google Drive sync is retired (Drive is full) — GitHub is the backup. Not
covered: `test_output/` (gitignored, ~27 MB of eval clips and keyframes; the
report + patent evidence lives only on this laptop — worth an occasional USB
copy).

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

## Natural speech (agent layer)

Without a local model the app behaves exactly as it always has: the
grammar-constrained keyword commands, ~5 µs to route. The agent adds a second
tier for everything the grammar cannot hear — and a grammar genuinely cannot
hear a paraphrase, it is a closed list of phrases.

Try it with **no downloads at all** — the web UI's **Ask** box types straight
into the router and shows which tier answered:

```powershell
python webapp.py                 # then type "describe the room" into Ask
python eval_agent.py --config keyword    # the measured baseline, 200 utterances
```

To turn the second tier on you need two downloads. **Run these yourself** —
nothing is fetched automatically:

```powershell
# 1. the local router model (offline, ~2 GB). Install Ollama first.
#    3b, not 1.5b: ~3 GB VRAM is free alongside both YOLO models on the 3050.
ollama pull qwen2.5:3b-instruct
python bench_llm.py --model qwen2.5:3b-instruct   # IS IT FAST ENOUGH HERE?

# 2. free-speech transcription for the "assistant" trigger word
pip install faster-whisper       # first run downloads ~75 MB of weights

# then:
python webapp.py --agent-model qwen2.5:3b-instruct --whisper-model
```

Say **“assistant”**, wait for “Yes?”, then ask in your own words (laptop mic
only — the phone has no dictation window yet).

The phone talks to the same router over `POST /agent` on `infer_server.py`, but
**local first**: anything its own grammar can parse is handled on-device with
the laptop off, and only an unresolved utterance goes over the network. If the
server is unreachable the phone stays on its offline capabilities — it never
invents an action.

Run `bench_llm.py` before trusting tier 1 in the field — it prints a verdict.

Note on hardware: detection runs at **21 ms/frame for both models** on the
tether laptop's RTX 3050 once CUDA is actually in use (`venv-gpu/`, torch
2.6.0+cu124). The older ~750 ms figure came from a CPU-only torch build on the
same machine. If you are setting this up fresh, check
`torch.cuda.is_available()` first — `pip install torch` gives you a CPU wheel by
default, and nothing in the logs tells you the GPU is idle.

## Tests

```powershell
python -m unittest       # 199 tests: position, decision, speech, voice,
                         # webapp, infer_server, agent, agent_server
python agent.py --write-manifest   # after changing agent.TOOLS — then run the
                                   # Flutter suite, which asserts the Dart
                                   # registry against capabilities.json
cd blindassist_app; flutter test   # 131 tests: the mirrored Dart logic
```
