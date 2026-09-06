# BlindAssist

## Team Details

This project was developed collaboratively by:

- Aditya Sridhar
- Goureesankar S Nair
- Yuvan Raj Mathan

We worked together to build an assistive object-detection system designed to help visually impaired users understand their surroundings.


**A camera that says what matters.** Point a phone or webcam at a room; it detects obstacles, works out which way they are and how close, and decides — out loud — what is actually worth telling you.

Everything runs on the machine. No cloud, no API keys, no account. Speech recognition, object detection and the language model that handles free-form questions are all local.

---

## What it does

| | |
|---|---|
| **Detection** | Two YOLO models in parallel — a general one and a small fine-tune for doors, dustbins and stairs |
| **Position** | Turns a box into "left / ahead / right, top / bottom" plus a proximity bucket that escalates as something fills the frame |
| **Decision** | Persistence and cooldown rules so it speaks when a thing is real and stays quiet when it is not. Speech never blocks the camera loop |
| **Voice, tier 0** | Grammar-constrained keyword commands. ~5 µs to route, works with nothing downloaded |
| **Voice, tier 1** | A local LLM router for everything a closed grammar cannot hear — because a grammar genuinely cannot hear a paraphrase |
| **Modes** | Walk (announce what is in the way), Find (`find bottle`), Describe (say what is in the room) |

## Measured, not claimed

From [`EVALUATION.md`](EVALUATION.md), on real recorded clips:

| | |
|---|---|
| Direction accuracy | **100 %** of reviewed announcement keyframes — every left/ahead/right, top/bottom matched the image |
| Proximity bucket | 100 % plausible, including escalating to "very close" exactly as a wardrobe fills the frame |
| Inference | **21 ms/frame** for both models on an RTX 3050 (CUDA). 172 ms — 5.8 FPS — on the same laptop CPU-only |
| Announcement latency | ~0.35–0.5 s from first sighting, then TTS |
| **Object naming** | **The weak point.** Wrong names in ~6 announcements across 7 clips — though in every case the *warning* behaviour was still correct |

That last row is the honest one, and `EVALUATION.md` has a whole section on where this lacks. A system that tells a blind user the wrong noun for a real obstacle is a different failure from one that misses the obstacle, and they are worth separating.

**A hardware lesson worth stealing:** `pip install torch` gives you a CPU wheel by default and *nothing in the logs tells you the GPU is idle*. The ~750 ms/frame figure in early notes was that, not the model. Check `torch.cuda.is_available()` before you believe any benchmark.

## Run it

```powershell
python webapp.py          # web UI at http://127.0.0.1:5000
python webapp.py --no-voice
```

Video, mode controls, an announcement feed, sonar beeps and voice commands (`find bottle`, `walk mode`, `describe`).

**Phone as the camera and the speaker,** laptop as the compute:

```powershell
# 1. phone: start the IP Webcam app, note its URL
# 2. laptop:
python webapp.py --source http://<phone-ip>:8080/video --host 0.0.0.0
# 3. phone browser: open the "On your phone -> http://..." URL it prints,
#    turn ON "Speak on this device", turn OFF "Voice (laptop)", earphones in.
```

Console version, same pipeline, OpenCV window — `q` quit, `s` snapshot, `d` describe:

```powershell
python phase4_assist.py
python phase4_assist.py --source http://<phone-ip>:8080/video
python phase4_assist.py --mode find --target bottle
python phase4_assist.py --rate 200      # quieter/faster voice
python phase4_assist.py --mute          # print-only dry run
```

Reproducible recorded-clip tests, video-time clock, no speech:

```powershell
python phase3_detect.py --source "test_output\clip.mp4" --headless
```

Earlier stage demos: `phase1_detect.py` (raw boxes), `phase2_detect.py` (+ position grid and proximity colours).

## The two-tier voice router

Try tier 0 with **no downloads at all** — the web UI's **Ask** box types straight into the router and shows which tier answered:

```powershell
python webapp.py                       # then type "describe the room" into Ask
python eval_agent.py --config keyword  # the measured baseline, 200 utterances
```

Tier 1 needs two downloads, and **nothing is fetched automatically**:

```powershell
# local router model (~2 GB, offline). Install Ollama first.
# 3b not 1.5b: ~3 GB VRAM is free alongside both YOLO models on a 3050.
ollama pull qwen2.5:3b-instruct
python bench_llm.py --model qwen2.5:3b-instruct   # prints a verdict — run it first

pip install faster-whisper   # ~75 MB of weights on first run

python webapp.py --agent-model qwen2.5:3b-instruct --whisper-model
```

Say **"assistant"**, wait for "Yes?", then ask in your own words.

It works on the phone with no download too: the trigger word swaps the grammar-constrained recogniser for an open one over the same bundled Vosk model, catches one utterance, and swaps back. Less accurate than Whisper — the trade for working with the laptop off. The transcript hits the local parser first, then the router over `POST /agent`. Anything the phone can parse itself is handled on-device, and **if the server is unreachable it falls back to its offline capabilities rather than inventing an action.**

## Layout

```
webapp.py            the app: Flask UI, video, voice, announcement feed
phase1..4_detect.py  the pipeline, one stage at a time
decision.py          persistence, cooldown, what is worth saying
position.py          box -> direction + proximity
speech.py            TTS, off the camera thread
speech_policy.py     when to speak, and when to shut up
voice.py             Vosk recognition, grammar-constrained
agent.py             tier-1 router
name_index.py        object naming
paper/               the write-up, figures and eval protocol
test_*.py            12 test modules
```

Design notes in `PIPELINE.md`, full engineering log in `CLAUDE.md`, results and limits in `EVALUATION.md`, hardware plan in `ANDROID_PLAN.md`.

## Development

```powershell
.\venv\Scripts\activate       # CPU torch — known-good fallback
.\venv-gpu\Scripts\activate   # CUDA torch 2.6.0+cu124 — 12x faster
```

Both environments exist deliberately: `venv/` vanished once to OneDrive's free-up-space, so it stays as the fallback. Only `venv-gpu` uses the GPU.

`test_output/` is gitignored — around 27 MB of eval clips and keyframes.
