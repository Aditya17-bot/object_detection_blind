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
    lines = ["BlindAssist — ASR reading sheet",
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


def cmd_record(args):
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("sounddevice is not installed in this interpreter "
                 "(it is what voice.py uses for the microphone)")

    records = subset(load_records())
    out_dir = AUDIO_DIR / args.speaker
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nSpeaker {args.speaker} — {len(records)} utterances, "
          f"{args.seconds:.0f}s each.")
    print("ENTER starts a recording. 's' + ENTER skips. 'r' + ENTER redoes the "
          "previous one. Ctrl-C stops (progress is kept).\n")

    index = 0
    while index < len(records):
        record = records[index]
        target = out_dir / f"{record['id']}.wav"
        if target.exists() and not args.overwrite:
            index += 1
            continue
        print(f"[{index + 1}/{len(records)}]  \"{record['utterance']}\"")
        choice = input("       ENTER to record > ").strip().lower()
        if choice == "s":
            index += 1
            continue
        if choice == "r" and index > 0:
            index -= 1
            (out_dir / f"{records[index]['id']}.wav").unlink(missing_ok=True)
            continue
        audio = sd.rec(int(args.seconds * SAMPLERATE), samplerate=SAMPLERATE,
                       channels=1, dtype="int16")
        sd.wait()
        with wave.open(str(target), "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(SAMPLERATE)
            fh.writeframes(audio.tobytes())
        print(f"       saved {target.name}\n")
        index += 1
    print(f"done — {len(list(out_dir.glob('*.wav')))} files in {out_dir}")


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
        sys.exit(f"no recordings under {AUDIO_DIR} — run `record` first")

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
    print("NOTE: the eval-set hash changes — quote the new one with any ASR "
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

    tr = sub.add_parser("transcribe", help="transcribe and write into the set")
    tr.add_argument("--vosk", action="store_true",
                    help="force the Vosk fallback even if Whisper is present")
    tr.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    {"sheet": cmd_sheet, "record": cmd_record,
     "transcribe": cmd_transcribe}[args.cmd](args)


if __name__ == "__main__":
    main()
