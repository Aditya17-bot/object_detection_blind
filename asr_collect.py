"""BlindAssist — collect the ASR condition for the routing evaluation.

EVAL_PROTOCOL.md section 4 defines an `asr` condition: the same 200-record set,
but fed real transcriptions instead of written text. It is explicitly not
automatable — it needs people who did not author the set reading utterances
aloud — so this script does the parts that ARE mechanical: choosing the
stratified subset, running the recording session, transcribing, and writing the
transcripts back into eval_set.jsonl without touching anything else.

Three steps, in order:

  1. python asr_collect.py sheet
        Prints (and writes) the stratified ~60-utterance reading sheet.

  2. python asr_collect.py record --speaker A
        One utterance at a time, ENTER to record, saves WAV per record.
        Run once per speaker. 2-3 speakers, none of them the set's author.

  3. python asr_collect.py transcribe
        Transcribes every WAV and appends each transcript to that record's
        `asr` array in paper/eval_set.jsonl. Errors are NOT cleaned up —
        the transcription errors ARE the condition.

Then:  python eval_agent.py --config two_tier --condition asr --model <model>

Transcriber: faster-whisper if installed (the accurate path, matches the
tethered system), otherwise the Vosk model already in the repo with its grammar
removed — which is what the handset itself falls back to, so it is a legitimate
condition in its own right. The choice is recorded in each transcript entry.
"""
import argparse
import json
import sys
import time
import wave
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
SET_PATH = ROOT / "paper" / "eval_set.jsonl"
AUDIO_DIR = ROOT / "test_output" / "asr_audio"
SHEET_PATH = ROOT / "test_output" / "asr_reading_sheet.txt"
SAMPLERATE = 16000
PER_CATEGORY = 12          # protocol section 4.1: ~60 records, 12 per category


def load_records():
    return [json.loads(line) for line in
            SET_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def subset(records):
    """Stratified pick: the first PER_CATEGORY of each category, in file order.

    Deterministic on purpose — every speaker reads the same list, and a rerun
    after a crash picks the same records."""
    by_category = defaultdict(list)
    for record in records:
        by_category[record["category"]].append(record)
    chosen = []
    for category in sorted(by_category):
        chosen.extend(by_category[category][:PER_CATEGORY])
    return chosen


# --------------------------------------------------------------------------

def cmd_sheet(args):
    records = subset(load_records())
    lines = ["BlindAssist - ASR reading sheet",
             f"{len(records)} utterances. Read each ONE TIME, at normal pace,",
             "in a normal room. Do not correct yourself; a natural stumble is",
             "part of the condition. Do not read the id.", ""]
    for i, record in enumerate(records, 1):
        lines.append(f"{i:>3}. [{record['id']}]  {record['utterance']}")
    text = "\n".join(lines) + "\n"
    SHEET_PATH.parent.mkdir(exist_ok=True)
    SHEET_PATH.write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {SHEET_PATH}")


def _save_wav(path, audio):
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(SAMPLERATE)
        fh.writeframes(audio.tobytes())


def cmd_record(args):
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("sounddevice is not installed in this interpreter "
                 "(it is what voice.py uses for the microphone)")

    records = subset(load_records())
    out_dir = AUDIO_DIR / args.speaker
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [r for r in records
            if args.overwrite or not (out_dir / f"{r['id']}.wav").exists()]
    if not todo:
        print(f"speaker {args.speaker} already has all {len(records)} "
              f"recordings - pass --overwrite to redo them")
        return

    # An ENTER-driven session needs a real terminal. Run through a wrapper that
    # gives the process no stdin (a tool runner, a pipe, nohup) and input()
    # raises EOFError on the first prompt, which is a confusing way to find out.
    interactive = sys.stdin is not None and sys.stdin.isatty()
    if not interactive and not args.auto:
        sys.exit(
            "no interactive terminal on stdin.\n"
            "  Either run this in a real PowerShell/terminal window:\n"
            f"      venv\\Scripts\\python.exe asr_collect.py record "
            f"--speaker {args.speaker}\n"
            "  or use the self-paced mode, which needs no keypresses:\n"
            f"      venv\\Scripts\\python.exe asr_collect.py record "
            f"--speaker {args.speaker} --auto")

    print(f"\nSpeaker {args.speaker} - {len(todo)} utterances to record, "
          f"{args.seconds:.0f}s each.")
    if args.auto:
        print(f"Self-paced: each line is shown, then {args.lead:.0f}s to get "
              f"ready, then it records. Ctrl-C stops (progress is kept).\n")
    else:
        print("ENTER starts a recording. 's' + ENTER skips. 'r' + ENTER redoes "
              "the previous one. Ctrl-C stops (progress is kept).\n")

    index = 0
    while index < len(records):
        record = records[index]
        target = out_dir / f"{record['id']}.wav"
        if target.exists() and not args.overwrite:
            index += 1
            continue
        print(f"[{index + 1}/{len(records)}]  \"{record['utterance']}\"",
              flush=True)

        if args.auto:
            for remaining in range(int(args.lead), 0, -1):
                print(f"       {remaining}...", end="\r", flush=True)
                time.sleep(1)
        else:
            try:
                choice = input("       ENTER to record > ").strip().lower()
            except EOFError:
                # isatty() can report a terminal that still has no readable
                # stdin (some tool runners and shells wrap it), so the honest
                # detection is the failure itself.
                sys.exit(
                    "\n\nno keyboard on stdin - this shell cannot run the "
                    "interactive session.\n"
                    "  Run it in a real PowerShell/terminal window, or use "
                    "the self-paced mode:\n"
                    f"      venv\\Scripts\\python.exe asr_collect.py record "
                    f"--speaker {args.speaker} --auto")
            if choice == "s":
                index += 1
                continue
            if choice == "r" and index > 0:
                index -= 1
                (out_dir / f"{records[index]['id']}.wav").unlink(missing_ok=True)
                continue

        print("       >> RECORDING - speak now", end="", flush=True)
        audio = sd.rec(int(args.seconds * SAMPLERATE), samplerate=SAMPLERATE,
                       channels=1, dtype="int16")
        sd.wait()
        _save_wav(target, audio)
        print(f"\r       saved {target.name}          \n", flush=True)
        index += 1

    print(f"done - {len(list(out_dir.glob('*.wav')))} files in {out_dir}")


# --------------------------------------------------------------------------
# Importing audio recorded somewhere else
# --------------------------------------------------------------------------
# Recording on a phone or in Audacity is often easier than sitting at the
# laptop, so `import` accepts what those produce: either one long WAV holding
# the whole session, which is split on the silences between utterances, or a
# folder of one-file-per-utterance. Either way the segments are mapped to the
# reading sheet IN ORDER, which is why the sheet is deterministic.

def _read_wav_mono16k(path):
    """Any PCM WAV -> mono int16 at 16 kHz, using numpy only (no ffmpeg, no
    scipy — neither is installed, and requiring them to import a recording
    would defeat the point)."""
    import numpy as np
    with wave.open(str(path), "rb") as fh:
        channels, width, rate, frames = (fh.getnchannels(), fh.getsampwidth(),
                                         fh.getframerate(), fh.getnframes())
        raw = fh.readframes(frames)
    if width == 2:
        audio = np.frombuffer(raw, np.int16).astype(np.float32)
    elif width == 1:                      # unsigned 8-bit
        audio = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) * 256
    elif width == 4:                      # 32-bit PCM
        audio = np.frombuffer(raw, np.int32).astype(np.float32) / 65536.0
    else:
        raise SystemExit(f"{path.name}: {width * 8}-bit WAV is not supported; "
                         "export 16-bit PCM")
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLERATE:                # linear resample is fine for speech
        n = int(round(len(audio) * SAMPLERATE / rate))
        audio = np.interp(np.linspace(0, len(audio) - 1, n),
                          np.arange(len(audio)), audio)
    return np.clip(audio, -32768, 32767).astype(np.int16)


def _split_on_silence(audio, min_silence, min_utterance, margin_db):
    """Utterance spans in a long recording, as (start, end) sample indices.

    Threshold is derived from the recording's own noise floor rather than a
    fixed dBFS, because a phone in a bedroom and a laptop mic in a kitchen do
    not share one."""
    import numpy as np
    frame = int(0.02 * SAMPLERATE)                       # 20 ms
    usable = len(audio) // frame * frame
    frames = audio[:usable].reshape(-1, frame).astype(np.float32)
    rms = np.sqrt((frames ** 2).mean(axis=1)) + 1e-6
    db = 20 * np.log10(rms / 32768.0)
    floor = np.percentile(db, 10)                        # the quiet 10%
    threshold = floor + margin_db
    voiced = db > threshold

    spans, start = [], None
    silence_frames = max(1, int(min_silence / 0.02))
    run = 0
    for i, is_voice in enumerate(voiced):
        if is_voice:
            if start is None:
                start = i
            run = 0
        elif start is not None:
            run += 1
            if run >= silence_frames:
                spans.append((start, i - run + 1))
                start = None
                run = 0
    if start is not None:
        spans.append((start, len(voiced)))

    pad = int(0.12 * SAMPLERATE)                          # keep plosives
    out = []
    for a, b in spans:
        s, e = a * frame, b * frame
        if (e - s) < min_utterance * SAMPLERATE:
            continue
        out.append((max(0, s - pad), min(len(audio), e + pad)))
    return out, threshold, floor


def cmd_import(args):
    records = subset(load_records())
    source = Path(args.audio)
    if not source.exists():
        sys.exit(f"no such path: {source}")
    out_dir = AUDIO_DIR / args.speaker

    if source.is_dir():
        files = sorted([p for p in source.iterdir()
                        if p.suffix.lower() == ".wav"])
        if not files:
            sys.exit(f"no .wav files in {source} (only WAV is supported — "
                     "there is no ffmpeg on this machine, so export WAV from "
                     "the recorder, or from Audacity)")
        print(f"{len(files)} files, mapped to the reading sheet in name order")
        segments = [(p, _read_wav_mono16k(p)) for p in files]
        pieces = [audio for _, audio in segments]
        labels = [p.name for p, _ in segments]
    else:
        if source.suffix.lower() != ".wav":
            sys.exit(f"{source.name}: only WAV is supported (no ffmpeg here). "
                     "Export 16-bit PCM WAV from your recorder or Audacity.")
        audio = _read_wav_mono16k(source)
        spans, threshold, floor = _split_on_silence(
            audio, args.min_silence, args.min_utterance, args.margin_db)
        print(f"{source.name}: {len(audio) / SAMPLERATE:.0f}s, noise floor "
              f"{floor:.0f} dBFS, speech above {threshold:.0f} dBFS")
        print(f"found {len(spans)} utterances (expected {len(records)})")
        pieces = [audio[a:b] for a, b in spans]
        labels = [f"{a / SAMPLERATE:6.1f}s - {b / SAMPLERATE:6.1f}s"
                  for a, b in spans]

    if args.dry_run or (len(pieces) != len(records) and not args.force):
        for i, label in enumerate(labels):
            expected = (records[i]["utterance"] if i < len(records)
                        else "(no matching record)")
            print(f"  {i + 1:>3}. {label}   ->  \"{expected}\"")
        if args.dry_run:
            print("\ndry run: nothing written")
            return
        sys.exit(
            f"\nsegment count ({len(pieces)}) != records ({len(records)}), so "
            "the mapping would be wrong from that point on.\n"
            "  Check the list above, then either:\n"
            "   - re-run with --min-silence 0.5 (fewer splits) or 0.25 (more)\n"
            "   - --margin-db 8 if quiet speech is being cut (default 6)\n"
            "   - --force to map the first "
            f"{min(len(pieces), len(records))} anyway")

    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for record, piece in zip(records, pieces):
        _save_wav(out_dir / f"{record['id']}.wav", piece)
        written += 1
    print(f"wrote {written} clips to {out_dir}")
    print("check a few before transcribing:")
    for record in records[:3]:
        print(f"  {out_dir / (record['id'] + '.wav')}  should be "
              f"\"{record['utterance']}\"")


# --------------------------------------------------------------------------

def _whisper_transcriber():
    """The accurate path, if the optional dependency is present."""
    try:
        from transcribe import Transcriber
    except ImportError:
        return None
    transcriber = Transcriber("small.en")
    if not transcriber.load():
        print(f"  faster-whisper unavailable ({transcriber.error})")
        return None

    def run(path):
        with open(path, "rb") as fh:
            return transcriber.transcribe_file(fh)
    return ("whisper-small.en", run)


def _vosk_transcriber():
    """No-download fallback: the model already in the repo, grammar removed.
    This is exactly what the HANDSET does for open dictation, so it is a
    legitimate condition rather than a degraded stand-in."""
    try:
        from vosk import KaldiRecognizer, Model, SetLogLevel
    except ImportError:
        return None
    model_dir = ROOT / "vosk-model-small-en-us-0.15"
    if not model_dir.is_dir():
        return None
    SetLogLevel(-1)
    model = Model(str(model_dir))

    def run(path):
        with wave.open(str(path), "rb") as fh:
            rec = KaldiRecognizer(model, fh.getframerate())
            rec.SetWords(False)
            while True:
                data = fh.readframes(4000)
                if not data:
                    break
                rec.AcceptWaveform(data)
            return json.loads(rec.FinalResult()).get("text", "").strip()
    return ("vosk-small-en-us", run)


# --------------------------------------------------------------------------
# align: one continuous recording -> per-record transcripts, without trusting
# silence detection to find the utterance boundaries
# --------------------------------------------------------------------------

def _vosk_word_stream(path):
    """Every recognised word in a whole session, with timings.

    Grammar removed, i.e. the open language model — the same configuration the
    handset uses for dictation, so this is the condition under test rather than
    a degraded stand-in."""
    from vosk import KaldiRecognizer, Model, SetLogLevel
    model_dir = ROOT / "vosk-model-small-en-us-0.15"
    if not model_dir.is_dir():
        sys.exit(f"vosk model not found at {model_dir}")
    SetLogLevel(-1)
    model = Model(str(model_dir))
    # MUST go through _read_wav_mono16k: a session recorded on a phone arrives
    # as 48 kHz stereo, and handing interleaved stereo frames to Vosk as if
    # they were mono produces fluent-looking nonsense ("shoo shoo whoosh")
    # rather than an obvious failure.
    audio = _read_wav_mono16k(path)
    raw = audio.tobytes()
    rec = KaldiRecognizer(model, SAMPLERATE)
    rec.SetWords(True)
    words = []
    step = 8000                                  # 4000 samples
    for start in range(0, len(raw), step):
        if rec.AcceptWaveform(raw[start:start + step]):
            words += json.loads(rec.Result()).get("result", [])
    words += json.loads(rec.FinalResult()).get("result", [])
    return words


def _word_cost(a, b):
    """Substitution cost. A near-miss ("chair"/"chairs", "beeps"/"beep") must
    not cost as much as an unrelated word, or the alignment walks off the
    script exactly where the recogniser struggled — which is where the data
    matters most."""
    if a == b:
        return 0.0
    if a[:4] == b[:4] and min(len(a), len(b)) >= 4:
        return 0.35
    if a[:3] == b[:3] and min(len(a), len(b)) >= 3:
        return 0.6
    return 1.0


def _align_words(hyp, ref):
    """Levenshtein alignment of the recognised word sequence onto the script.

    Returns, for each reference word index, the list of hypothesis indices that
    landed on it. Insertions attach to the preceding reference word, so a
    hallucinated word stays inside the utterance it was spoken during."""
    n, m = len(hyp), len(ref)
    INS, DEL = 1.0, 1.0
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]     # 0 diag, 1 up(ins), 2 left(del)
    for i in range(1, n + 1):
        cost[i][0] = i * INS
        back[i][0] = 1
    for j in range(1, m + 1):
        cost[0][j] = j * DEL
        back[0][j] = 2
    for i in range(1, n + 1):
        hi = hyp[i - 1]
        row, prev = cost[i], cost[i - 1]
        brow = back[i]
        for j in range(1, m + 1):
            d = prev[j - 1] + _word_cost(hi, ref[j - 1])
            u = prev[j] + INS
            l = row[j - 1] + DEL
            best = d
            move = 0
            if u < best:
                best, move = u, 1
            if l < best:
                best, move = l, 2
            row[j] = best
            brow[j] = move

    assigned = [[] for _ in range(m)]
    matched = [False] * m
    i, j = n, m
    while i > 0 or j > 0:
        move = back[i][j]
        if move == 0 and i > 0 and j > 0:
            assigned[j - 1].append(i - 1)
            matched[j - 1] = _word_cost(hyp[i - 1], ref[j - 1]) < 0.5
            i, j = i - 1, j - 1
        elif move == 1 and i > 0:
            # insertion: attach to the reference word to its left (j-1), or the
            # first one if we are still before the script started
            assigned[max(0, j - 1)].append(i - 1)
            i -= 1
        else:
            j -= 1
    for slot in assigned:
        slot.reverse()
    return assigned, matched


def cmd_align(args):
    records = subset(load_records())
    all_records = load_records()
    by_id = {r["id"]: r for r in all_records}

    print(f"transcribing {args.audio} (open language model, no grammar)...")
    stream = _vosk_word_stream(args.audio)
    hyp = [w["word"].lower() for w in stream]
    print(f"  {len(hyp)} words recognised")

    ref, owner = [], []
    for index, record in enumerate(records):
        for word in record["utterance"].lower().split():
            ref.append(word)
            owner.append(index)
    print(f"  script is {len(ref)} words across {len(records)} utterances")

    assigned, matched = _align_words(hyp, ref)

    per_utterance = [[] for _ in records]
    hits = [0] * len(records)
    totals = [0] * len(records)
    for ref_index, hyp_indices in enumerate(assigned):
        who = owner[ref_index]
        totals[who] += 1
        if matched[ref_index]:
            hits[who] += 1
        per_utterance[who].extend(hyp_indices)

    out_dir = AUDIO_DIR / args.speaker
    audio = _read_wav_mono16k(args.audio) if args.clips else None
    if args.clips:
        out_dir.mkdir(parents=True, exist_ok=True)

    written, weak, empty = 0, 0, 0
    print()
    for index, record in enumerate(records):
        indices = sorted(per_utterance[index])
        text = " ".join(hyp[i] for i in indices).strip()
        score = hits[index] / totals[index] if totals[index] else 0.0
        exact = text == record["utterance"].lower()

        if not text:
            empty += 1
            print(f"  {record['id']}  NO AUDIO ALIGNED  (skipped)")
            continue
        if score < args.min_match:
            weak += 1
            print(f"  {record['id']}  match {score:.0%} < {args.min_match:.0%} "
                  f"-> {text!r}  (skipped, alignment not trustworthy)")
            continue

        mark = "exact" if exact else f"match {score:.0%}"
        print(f"  {record['id']}  [{mark}]  {text!r}")

        target = by_id[record["id"]]
        entry = {"speaker": args.speaker, "engine": "vosk-small-en-us",
                 "text": text}
        existing = target.setdefault("asr", [])
        existing[:] = [e for e in existing
                       if not (isinstance(e, dict)
                               and e.get("speaker") == args.speaker
                               and e.get("engine") == entry["engine"])]
        existing.append(entry)
        written += 1

        if args.clips and indices:
            start = int(stream[indices[0]]["start"] * SAMPLERATE)
            end = int(stream[indices[-1]]["end"] * SAMPLERATE)
            pad = int(0.12 * SAMPLERATE)
            _save_wav(out_dir / f"{record['id']}.wav",
                      audio[max(0, start - pad):min(len(audio), end + pad)])

    print(f"\n{written} aligned, {weak} below --min-match, {empty} with no audio")
    if args.dry_run:
        print("dry run: nothing written")
        return
    with SET_PATH.open("w", encoding="utf-8") as fh:
        for record in all_records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    covered = sum(1 for r in all_records if r.get("asr"))
    print(f"wrote {SET_PATH}: {covered}/{len(all_records)} records carry ASR")
    print("NOTE: the eval-set hash changes - quote the new one with any ASR "
          "number, and keep clean-condition numbers under the old hash.")


def cmd_transcribe(args):
    engine = None
    if not args.vosk:
        engine = _whisper_transcriber()
    if engine is None:
        engine = _vosk_transcriber()
    if engine is None:
        sys.exit("no transcriber available: install faster-whisper, or keep "
                 "vosk-model-small-en-us-0.15/ in the project root")
    name, transcribe = engine
    print(f"transcriber: {name}")

    records = load_records()
    by_id = {r["id"]: r for r in records}
    wavs = sorted(AUDIO_DIR.glob("*/*.wav"))
    if not wavs:
        sys.exit(f"no recordings under {AUDIO_DIR} - run `record` first")

    added, empty = 0, 0
    for wav in wavs:
        record = by_id.get(wav.stem)
        if record is None:
            print(f"  skipping {wav} (no such record id)")
            continue
        speaker = wav.parent.name
        text = transcribe(wav)
        if not text:
            empty += 1
            print(f"  {wav.stem} [{speaker}] -> (nothing heard)")
            continue
        entry = {"speaker": speaker, "engine": name, "text": text}
        existing = record.setdefault("asr", [])
        # re-running must not duplicate: one entry per (speaker, engine)
        existing[:] = [e for e in existing
                       if not (isinstance(e, dict)
                               and e.get("speaker") == speaker
                               and e.get("engine") == name)]
        existing.append(entry)
        added += 1
        flag = "" if text.lower() == record["utterance"].lower() else "  <-- differs"
        print(f"  {wav.stem} [{speaker}] -> {text!r}{flag}")

    if args.dry_run:
        print(f"\ndry run: {added} transcripts NOT written")
        return
    with SET_PATH.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    covered = sum(1 for r in records if r.get("asr"))
    print(f"\nwrote {SET_PATH}: {added} transcripts, {empty} silent, "
          f"{covered}/{len(records)} records now carry ASR")
    print("NOTE: the eval-set hash changes - quote the new one with any ASR "
          "number, and keep the clean-condition numbers under the old hash.")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sheet", help="print/write the reading sheet")

    rec = sub.add_parser("record", help="run a recording session")
    rec.add_argument("--speaker", required=True,
                     help="short label, e.g. A / B / C (never a real name)")
    rec.add_argument("--seconds", type=float, default=4.0)
    rec.add_argument("--overwrite", action="store_true")
    rec.add_argument("--auto", action="store_true",
                     help="self-paced: no keypresses, a countdown before each "
                          "recording. Required when stdin is not a terminal.")
    rec.add_argument("--lead", type=float, default=3.0,
                     help="seconds between showing a line and recording it "
                          "(--auto only)")

    imp = sub.add_parser("import", help="import audio recorded elsewhere")
    imp.add_argument("--speaker", required=True, help="short label, e.g. A")
    imp.add_argument("--audio", required=True,
                     help="one long WAV of the whole session, or a folder of "
                          "one WAV per utterance (name order = sheet order)")
    imp.add_argument("--dry-run", action="store_true",
                     help="show the segment-to-utterance mapping, write nothing")
    imp.add_argument("--force", action="store_true",
                     help="import even when the segment count is wrong")
    imp.add_argument("--min-silence", type=float, default=0.35,
                     help="seconds of quiet that separate two utterances")
    imp.add_argument("--min-utterance", type=float, default=0.35,
                     help="drop anything shorter than this (coughs, clicks)")
    imp.add_argument("--margin-db", type=float, default=6.0,
                     help="dB above the recording's own noise floor that counts "
                          "as speech")

    al = sub.add_parser(
        "align",
        help="one continuous recording -> per-record transcripts, by aligning "
             "the recognised word stream to the reading sheet")
    al.add_argument("--speaker", required=True, help="short label, e.g. A")
    al.add_argument("--audio", required=True,
                    help="one WAV of the whole session, read in sheet order")
    al.add_argument("--min-match", type=float, default=0.34,
                    help="fraction of an utterance's script words that must "
                         "align before its transcript is trusted; below this "
                         "the record is skipped rather than guessed at")
    al.add_argument("--clips", action="store_true",
                    help="also cut a per-record WAV, so the alignment can be "
                         "checked by ear")
    al.add_argument("--dry-run", action="store_true")

    tr = sub.add_parser("transcribe", help="transcribe and write into the set")
    tr.add_argument("--vosk", action="store_true",
                    help="force the Vosk fallback even if Whisper is present")
    tr.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    {"sheet": cmd_sheet, "record": cmd_record, "import": cmd_import,
     "align": cmd_align, "transcribe": cmd_transcribe}[args.cmd](args)


if __name__ == "__main__":
    main()
