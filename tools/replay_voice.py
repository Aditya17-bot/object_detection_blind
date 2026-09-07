"""Replay a walk's AUDIO through the real Vosk grammar and the real parser.

Two capabilities have now been lost to input problems rather than logic
problems: a grammar that drifted from the registry (2026-09-07 morning) and an
out-of-vocabulary word that Vosk silently drops (`unmute`, same day). Both were
invisible until a walk failed. This makes that class of fault findable from a
recording:

  * every registry capability is checked for a spoken route back to itself,
  * every grammar word is checked against the model's own lexicon,
  * the clip's audio is transcribed through the SAME grammar the phone uses and
    each utterance is pushed through parse_command / the noise floors.

    venv\\Scripts\\python.exe tools/replay_voice.py test_output/field_walk_20260907.mp4
"""
import argparse
import collections
import json
import os
import subprocess
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
import voice

MODEL_DIR = "vosk-model-small-en-us-0.15"


# ----------------------------------------------------------------------
# static checks — no audio needed, and these are the ones that bite
# ----------------------------------------------------------------------
def check_registry_reachable():
    """Every spoken capability must have an example that parses back to it."""
    problems = []
    for spec in agent.TOOLS:
        # `abstain` is the router's refusal, not something anyone says
        if spec.internal or spec.name == "abstain":
            continue
        routes = []
        for ex in spec.examples:
            parsed = voice.parse_command(ex)
            routes.append((ex, parsed))
        if not any(p and p[0] == spec.name for _, p in routes):
            problems.append((spec.name, routes))
    return problems


def check_grammar_in_vocabulary():
    """Words Vosk does not know are dropped from the grammar with a warning
    nobody reads, so the phrase becomes unhearable rather than misheard.

    The warning goes to the C library's stderr, which cannot be captured from
    inside this process — hence the subprocess.
    """
    phrases = agent.grammar_phrases()
    words = sorted({w for p in phrases for w in p.split()})
    script = (
        "import json,sys\n"
        "from vosk import Model, KaldiRecognizer, SetLogLevel\n"
        "SetLogLevel(0)\n"
        f"m = Model({MODEL_DIR!r})\n"
        f"KaldiRecognizer(m, 16000, json.dumps({words!r}))\n"
    )
    proc = subprocess.run([sys.executable, "-c", script],
                          capture_output=True, text=True)
    missing = []
    for line in (proc.stderr or "").splitlines():
        if "Word" in line and "not in vocabulary" in line:
            missing.append(line.strip().split("Word", 1)[1].strip())
    return missing, len(words), proc.returncode


def check_noise_floor():
    """The floors must reject field noise and keep real phrasings. Both
    directions matter: over-tight floors made 'read' unhearable once."""
    noise = ["the is my on", "describe light left", "the clock summary",
             "the many where of me is there read walk", "many plant",
             "my left", "cup phones", "the mobiles"]
    real = [s for spec in agent.TOOLS if not spec.internal
            for s in spec.examples]
    leaks = [n for n in noise if voice.looks_like_one_request(n)
             and voice.parse_command(n)]
    rejects = [r for r in real if not voice.looks_like_one_request(r)]
    return leaks, rejects, len(real)


# ----------------------------------------------------------------------
# audio
# ----------------------------------------------------------------------
def extract_wav(video, out_wav):
    """Pull 16 kHz mono PCM out of the clip. No ffmpeg on this machine, so
    the Windows MediaTranscoder does it (same route as tools/aac_to_wav.ps1)."""
    if os.path.exists(out_wav):
        return out_wav
    ps = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "aac_to_wav.ps1")
    proc = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps,
         "-InputPath", os.path.abspath(video),
         "-OutputPath", os.path.abspath(out_wav)],
        capture_output=True, text=True)
    if not os.path.exists(out_wav):
        raise SystemExit(f"audio extraction failed:\n{proc.stdout}\n{proc.stderr}")
    return out_wav


def read_wav_mono16k(path):
    """Vosk wants 16 kHz mono. Feeding it 48 kHz stereo does not fail — it
    returns fluent nonsense (that cost a whole ASR run on 2026-08-01)."""
    import audioop
    with wave.open(path, "rb") as w:
        ch, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        data = w.readframes(w.getnframes())
    if width != 2:
        data = audioop.lin2lin(data, width, 2)
        width = 2
    if ch > 1:
        data = audioop.tomono(data, width, 0.5, 0.5)
    if rate != 16000:
        data, _ = audioop.ratecv(data, width, 1, rate, 16000, None)
    return data


def transcribe(pcm, phrases):
    from vosk import KaldiRecognizer, Model, SetLogLevel
    SetLogLevel(-1)
    model = Model(MODEL_DIR)
    rec = KaldiRecognizer(model, 16000, json.dumps(sorted(phrases) + ["[unk]"]))
    rec.SetWords(True)
    out = []
    chunk = 4000
    for i in range(0, len(pcm), chunk):
        if rec.AcceptWaveform(pcm[i:i + chunk]):
            r = json.loads(rec.Result())
            if r.get("text"):
                out.append(r)
    r = json.loads(rec.FinalResult())
    if r.get("text"):
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out", default="test_output/replay_voice.md")
    args = ap.parse_args()

    L = []
    a = L.append
    a("# Voice-input replay\n")

    a("## Registry reachable by speech\n")
    problems = check_registry_reachable()
    if problems:
        for name, routes in problems:
            a(f"- **{name}** — no example parses back to it")
            for ex, parsed in routes:
                a(f"    - {ex!r} -> {parsed}")
    else:
        a("- every spoken capability has an example that parses back to it")
    a("")

    a("## Grammar words the speech model actually knows\n")
    missing, nwords, rc = check_grammar_in_vocabulary()
    if rc != 0:
        a(f"- could not check (vosk exited {rc})")
    elif missing:
        a(f"- **{len(missing)} of {nwords} grammar words are NOT in the "
          f"model's lexicon** — phrases using them are unhearable:")
        for m in missing:
            a(f"    - {m}")
    else:
        a(f"- all {nwords} grammar words are in the model's lexicon")
    a("")

    a("## Noise floor\n")
    leaks, rejects, nreal = check_noise_floor()
    a(f"- field noise that still reaches a capability: "
      f"{leaks if leaks else 'none'}")
    a(f"- real phrasings rejected by the floor ({nreal} checked): "
      f"{rejects if rejects else 'none'}")
    a("")

    if args.video:
        a(f"## Utterances heard in {os.path.basename(args.video)}\n")
        wav = os.path.join("test_output",
                           os.path.splitext(os.path.basename(args.video))[0]
                           + "_16k.wav")
        extract_wav(args.video, wav)
        pcm = read_wav_mono16k(wav)
        a(f"- {len(pcm) / 32000:.1f} s of audio")
        results = transcribe(pcm, agent.grammar_phrases())
        counts = collections.Counter()
        for r in results:
            text = r["text"]
            unk = text.split().count("[unk]")
            usable = voice.looks_like_one_request(text)
            parsed = voice.parse_command(text) if usable else None
            # the listener's own gate: a setting must have been ASKED for, not
            # merely contained in the noise
            if parsed and not voice.setting_is_deliberate(parsed[0], text):
                parsed = None
                usable = "setting not deliberate"
            counts["heard"] += 1
            counts["parsed" if parsed else "dropped"] += 1
            verdict = ("pass" if usable is True
                       else ("REJECT" if usable is False else usable))
            a(f"- {text!r}  unk={unk}  floor={verdict}  -> {parsed}")
        a("")
        a(f"- {counts['heard']} utterances, {counts['parsed']} routed, "
          f"{counts['dropped']} dropped")
    a("")

    md = "\n".join(L)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(md)


if __name__ == "__main__":
    main()
