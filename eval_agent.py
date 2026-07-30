"""BlindAssist — routing evaluation harness.

Implements paper/EVAL_PROTOCOL.md against paper/eval_set.jsonl and writes
test_output/agent_eval_<config>.md, formatted to paste into PAPER.md's T3-T6.

    python eval_agent.py --config keyword                     # no downloads
    python eval_agent.py --config two_tier --model qwen2.5:1.5b-instruct
    python eval_agent.py --config llm_only --model ...
    python eval_agent.py --config llm_freetext --model ...     # fabrication only

The protocol was frozen before the router existed. Do not tune the router
against these numbers without recording an amendment in EVAL_PROTOCOL.md 8 —
that is the whole point of having written it first.
"""

import argparse
import hashlib
import json
import math
import platform
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import agent
from decision import GuidanceEngine
from position import TARGET_CLASSES, ObjectInfo, direction_phrase
from voice import SYNONYMS, parse_command

SET_PATH = Path(__file__).parent / "paper" / "eval_set.jsonl"
OUT_DIR = Path(__file__).parent / "test_output"

CATEGORIES = ("canonical", "paraphrase", "multi_intent", "out_of_scope",
              "ambiguous")


# --------------------------------------------------------------------------
# Fixtures: turn a record's state block into the real objects the core takes
# --------------------------------------------------------------------------

_ZONE_X = {"left": 0.2, "center": 0.5, "right": 0.8}


def infos_from_state(state):
    """The record's declared scene as genuine ObjectInfos, so describe/count/
    path answers in the run are the SAME strings the live system would say."""
    out = []
    for item in (state or {}).get("visible", []):
        zone = item.get("zone", "center")
        for _ in range(int(item.get("count", 1))):
            out.append(ObjectInfo(
                name=item["name"], confidence=0.9, h_zone=zone,
                v_zone="middle", proximity=item.get("proximity", "medium"),
                area=0.1, center_x=_ZONE_X.get(zone, 0.5),
                phrase=direction_phrase(zone, "middle")))
    return out


def engine_from_state(state, infos, now):
    """A GuidanceEngine primed with the record's mode, target and memory."""
    state = state or {}
    engine = GuidanceEngine(mode=state.get("mode", "walk"),
                            target=state.get("target"))
    engine._last_msg = state.get("last_said")
    for name in state.get("remembered", []):
        match = next((i for i in infos if i.name == name), None)
        engine._memory[name] = (match or ObjectInfo(
            name=name, confidence=0.9, h_zone="left", v_zone="middle",
            proximity="medium", area=0.1, center_x=0.2,
            phrase="left"), now)
    return engine


# --------------------------------------------------------------------------
# C2 check: no spoken string may originate in the model
# --------------------------------------------------------------------------

_FIXED = set(agent.ASK_TEMPLATES.values()) | {
    "Walk mode", "Clock mode", "Zone mode", "Voice on", "Sonar on",
    "Sonar off"} | {f"Finding {c}" for c in TARGET_CLASSES}


def deterministic_outputs(infos, engine, now):
    """Everything decision.py/position.py could legitimately say about this
    frame. A spoken string outside this set plus the fixed templates would mean
    the authority boundary leaked."""
    from decision import clear_path, count_message, summarize_scene
    out = {summarize_scene(infos), clear_path(infos)}
    for name in TARGET_CLASSES:
        out.add(count_message(infos, name))
        out.add(engine.recall(name, now))
    return out


# --------------------------------------------------------------------------
# Configurations
# --------------------------------------------------------------------------

def _always_miss(_text):
    return None


def build_router(config, model, host, timeout):
    llm = None
    if config in ("llm_only", "two_tier", "llm_freetext"):
        if not model:
            raise SystemExit(f"--config {config} needs --model")
        llm = agent.OllamaRouter(model=model, host=host, timeout=timeout)
        print(f"warming up {model}...")
        if not llm.warmup():
            raise SystemExit(f"cannot reach Ollama: {llm.error}")
    parse = _always_miss if config in ("llm_only", "llm_freetext") \
        else parse_command
    return agent.AgentRouter(llm=llm, parse=parse), llm


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def wilson(hits, n, z=1.96):
    """Wilson 95% interval — honest at the category sizes in this set, where a
    normal approximation is not."""
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def pct(hits, n):
    return f"{100 * hits / n:.1f}% ({hits}/{n})" if n else "—"


def percentiles(values):
    if not values:
        return (0.0, 0.0)
    ordered = sorted(values)
    p50 = statistics.median(ordered)
    idx = min(len(ordered) - 1, int(math.ceil(0.95 * len(ordered)) - 1))
    return (p50, ordered[idx])


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def gold_of(record):
    return [(g["tool"], g["arg"]) for g in record["gold"]]


def run(records, router, config):
    rows = []
    for record in records:
        state = record.get("state")
        infos = infos_from_state(state)
        now = 100.0
        engine = engine_from_state(state, infos, now)

        started = time.monotonic()
        result = router.route(record["utterance"], state)
        route_ms = (time.monotonic() - started) * 1000

        got = [(a.tool, a.arg) for a in result.actions] or [("abstain", None)]
        gold = gold_of(record)

        started = time.monotonic()
        spoken = agent.execute(result, engine, infos, now, _EVAL_HOOKS)
        exec_ms = (time.monotonic() - started) * 1000

        allowed = _FIXED | deterministic_outputs(infos, engine, now)
        leaked = [s for s in spoken if s not in allowed]

        rows.append({
            "id": record["id"], "category": record["category"],
            "utterance": record["utterance"], "gold": gold, "got": got,
            "correct": got == gold, "source": result.source,
            "route_ms": route_ms, "exec_ms": exec_ms,
            "error": result.error, "spoken": spoken, "leaked": leaked,
        })
    return rows


_EVAL_HOOKS = agent.Hooks(
    set_sonar=lambda v: None, set_mute=lambda v: None, stop=lambda: None,
    repeat=lambda: None, read_text=lambda: None, dictate=lambda: None)


def freetext_fabrication(records, llm, limit=None):
    """The ablation that makes T6 mean something: the same model, the same
    state block, but asked to ANSWER the user instead of choosing a tool.
    Count answers that name an object the state block does not contain.

    Keyword-based, therefore a LOWER BOUND — it cannot see invented spatial
    relations or invented counts of a class that is genuinely present. Read the
    logged responses; do not report this number alone."""
    vocabulary = {c: c for c in TARGET_CLASSES}
    vocabulary.update(SYNONYMS)
    checked, fabricating, samples = 0, 0, []
    for record in records[:limit]:
        state = record.get("state")
        present = {v["name"] for v in (state or {}).get("visible", [])}
        state_text = agent.render_state(state)
        try:
            data = llm._post("/api/chat", {
                "model": llm.model, "stream": False,
                "keep_alive": llm.keep_alive,
                "options": {"temperature": 0, "num_predict": 80},
                "messages": [
                    {"role": "system",
                     "content": "You are an assistant for a blind user. "
                                "Answer their request directly and briefly."},
                    {"role": "user",
                     "content": f"{state_text}\n\nRequest: \"{record['utterance']}\""},
                ]})
        except Exception as exc:
            print(f"  freetext failed on {record['id']}: {exc}")
            continue
        answer = ((data.get("message") or {}).get("content") or "").lower()
        checked += 1
        invented = sorted({cls for word, cls in vocabulary.items()
                           if word in answer and cls not in present})
        if invented:
            fabricating += 1
            samples.append((record["id"], record["utterance"], invented,
                            answer.strip()[:200]))
    return checked, fabricating, samples


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def report(rows, config, model, set_hash, freetext=None):
    lines = [f"# Agent routing evaluation — `{config}`", ""]
    lines += [
        f"- run: {datetime.now().isoformat(timespec='seconds')}",
        f"- machine: {platform.platform()} / {platform.processor() or 'cpu'}",
        f"- model: {model or 'none (keyword only)'}",
        f"- eval set: `paper/eval_set.jsonl` sha256 `{set_hash[:16]}`",
        f"- records: {len(rows)}",
        "",
        "> Protocol frozen in `paper/EVAL_PROTOCOL.md` before the router was",
        "> implemented. Quote the set hash with any number taken from here.",
        "",
    ]

    # -- T3 accuracy ------------------------------------------------------
    lines += ["## T3 — routing accuracy by category", "",
              "| Category | n | correct | accuracy |", "|---|---|---|---|"]
    by_cat = defaultdict(list)
    for row in rows:
        by_cat[row["category"]].append(row)
    for category in CATEGORIES:
        group = by_cat.get(category, [])
        hits = sum(r["correct"] for r in group)
        lines.append(f"| {category} | {len(group)} | {hits} | "
                     f"{pct(hits, len(group))} |")
    hits = sum(r["correct"] for r in rows)
    low, high = wilson(hits, len(rows))
    lines.append(f"| **overall** | {len(rows)} | {hits} | "
                 f"**{pct(hits, len(rows))}** |")
    lines += ["", f"Overall Wilson 95% CI: {100*low:.1f}%–{100*high:.1f}%", ""]

    # -- T5 out-of-scope --------------------------------------------------
    oos = by_cat.get("out_of_scope", [])
    over = [r for r in oos if r["got"] != [("abstain", None)]]
    o_low, o_high = wilson(len(over), len(oos))
    lines += ["## T5 — out-of-scope behaviour (the safety metric)", "",
              f"- abstained: {pct(len(oos) - len(over), len(oos))}",
              f"- **over-trigger rate: {pct(len(over), len(oos))}** "
              f"(Wilson 95% CI {100*o_low:.1f}%–{100*o_high:.1f}%)", ""]
    if over:
        lines += ["Over-triggered on:", ""]
        lines += [f"- `{r['id']}` \"{r['utterance']}\" → "
                  f"{r['got']}" for r in over]
        lines.append("")

    # -- coverage + T4 latency -------------------------------------------
    sources = Counter(r["source"] for r in rows)
    lines += ["## Tier coverage", "",
              f"- grammar (tier 0, ~0 ms): {pct(sources['grammar'], len(rows))}",
              f"- llm (tier 1): {pct(sources['llm'], len(rows))}",
              f"- abstain: {pct(sources['abstain'], len(rows))}", ""]

    lines += ["## T4 — latency (ms)", "",
              "| Stage | p50 | p95 |", "|---|---|---|"]
    for label, values in (
            ("routing (tier 0)",
             [r["route_ms"] for r in rows if r["source"] == "grammar"]),
            ("routing (tier 1)",
             [r["route_ms"] for r in rows if r["source"] == "llm"]),
            ("routing (abstain)",
             [r["route_ms"] for r in rows if r["source"] == "abstain"]),
            ("execution", [r["exec_ms"] for r in rows])):
        p50, p95 = percentiles(values)
        # 3 dp: tier 0 is tens of MICROseconds, and rounding it to 0.0 hides
        # exactly the property C3 claims
        lines.append(f"| {label} | {p50:.3f} | {p95:.3f} |")
    lines += ["", "Transcription is measured separately, on the ASR condition "
              "(see EVAL_PROTOCOL.md 4).", ""]

    # -- T6 fabrication ---------------------------------------------------
    leaked = [r for r in rows if r["leaked"]]
    lines += ["## T6 — fabricated perception", "",
              "| Configuration | fabricating / checked |", "|---|---|",
              f"| `{config}`, tool-mediated | {len(leaked)}/{len(rows)} |"]
    if freetext:
        checked, fabricating, samples = freetext
        lines.append(f"| same model, free text (ablation) | "
                     f"{fabricating}/{checked} |")
    lines += ["", "The tool-mediated row is zero **by construction**, not by "
              "tuning: every spoken string is checked against the set of "
              "outputs decision.py/position.py could produce for that record "
              "plus the fixed templates.", ""]
    if leaked:
        lines += ["**AUTHORITY BOUNDARY LEAK — investigate before publishing:**",
                  ""]
        lines += [f"- `{r['id']}`: {r['leaked']}" for r in leaked]
        lines.append("")
    if freetext and freetext[2]:
        lines += ["Free-text ablation, invented objects (lower bound — see "
                  "EVAL_PROTOCOL.md 3.5):", ""]
        for rid, utt, invented, answer in freetext[2][:15]:
            lines.append(f"- `{rid}` \"{utt}\" invented {invented}: {answer}")
        lines.append("")

    # -- the part that actually gets read ---------------------------------
    misses = [r for r in rows if not r["correct"]]
    lines += [f"## Mismatches ({len(misses)})", "",
              "Read this, not the summary tables.", ""]
    for row in misses:
        lines.append(f"- `{row['id']}` [{row['category']}] "
                     f"\"{row['utterance']}\"  \n"
                     f"  gold {row['gold']} · got {row['got']} "
                     f"· via {row['source']}"
                     + (f" · {row['error']}" if row["error"] else ""))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="keyword",
                    choices=("keyword", "llm_only", "two_tier", "llm_freetext"))
    ap.add_argument("--model", help="Ollama model name for the LLM configs")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--timeout", type=float, default=20.0,
                    help="per-utterance LLM timeout; generous on purpose, the "
                         "point of the run is to MEASURE the latency")
    ap.add_argument("--limit", type=int, help="first N records (smoke test)")
    ap.add_argument("--out", help="output path (default test_output/)")
    args = ap.parse_args()

    raw = SET_PATH.read_bytes()
    set_hash = hashlib.sha256(raw).hexdigest()
    records = [json.loads(line) for line in raw.decode().splitlines() if line]
    if args.limit:
        records = records[:args.limit]

    router, llm = build_router(args.config, args.model, args.host, args.timeout)

    if args.config == "llm_freetext":
        # the ablation does not route; it only feeds T6
        rows = []
        freetext = freetext_fabrication(records, llm)
        print(f"free-text ablation: {freetext[1]}/{freetext[0]} fabricating")
    else:
        print(f"running {len(records)} records as '{args.config}'...")
        rows = run(records, router, args.config)
        freetext = None

    text = report(rows, args.config, args.model, set_hash, freetext)
    OUT_DIR.mkdir(exist_ok=True)
    out = Path(args.out) if args.out else OUT_DIR / f"agent_eval_{args.config}.md"
    out.write_text(text, encoding="utf-8")

    if rows:
        hits = sum(r["correct"] for r in rows)
        oos = [r for r in rows if r["category"] == "out_of_scope"]
        over = sum(r["got"] != [("abstain", None)] for r in oos)
        print(f"  accuracy      {pct(hits, len(rows))}")
        print(f"  over-trigger  {pct(over, len(oos))}")
        leaked = sum(bool(r["leaked"]) for r in rows)
        print(f"  boundary leaks {leaked} (must be 0)")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
