"""BlindAssist — tier-1 feasibility spike. RUN THIS BEFORE ENABLING THE AGENT.

The tether laptop takes ~750 ms/frame for two small YOLO models, which says
there is no strong GPU here. A local instruct model on CPU could be anywhere
from 1 s to 10 s per route, and only measurement settles it. This script sends
the REAL router prompt — the real registry, a real state block — so the number
it prints is the number the user will wait through.

    ollama pull qwen2.5:1.5b-instruct       # ~1 GB, do this first
    python bench_llm.py --model qwen2.5:1.5b-instruct
    python bench_llm.py --model llama3.2:3b-instruct-q4_K_M --runs 5

Reading the result:

  under ~1.5 s   comfortable — tier 1 is usable for on-demand questions
  1.5 s - 3 s    usable with the spoken "One moment" acknowledgement
  over ~3 s      try a smaller model; if the floor stays here, report local
                 routing as viable only for non-urgent queries and say so in
                 the paper rather than pretending otherwise

Nothing here is inside the continuous guidance loop — voice commands are
on-demand, which buys real headroom. It does not buy ten seconds of it.
"""

import argparse
import statistics
import time

import agent
from position import ObjectInfo, direction_phrase

# A representative moment: a couple of things in view, walk mode, something
# remembered. Same shape state_summary() produces live.
_SCENE = [
    ObjectInfo("chair", 0.88, "left", "middle", "close", 0.13, 0.2,
               direction_phrase("left", "middle")),
    ObjectInfo("door", 0.71, "center", "middle", "medium", 0.09, 0.5,
               direction_phrase("center", "middle")),
    ObjectInfo("bottle", 0.83, "right", "middle", "far", 0.004, 0.82,
               direction_phrase("right", "middle")),
]

# Deliberately tier-0 MISSES: these are the utterances that would actually
# reach the model.
_PROMPTS = [
    "is there anywhere i can sit",
    "what does this label say",
    "help me get to the exit",
    "how many of them are there",
    "what's the weather like today",
    "turn on the beeps and find the door",
]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="qwen2.5:1.5b-instruct")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--runs", type=int, default=3,
                    help="passes over the prompt list")
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()

    llm = agent.OllamaRouter(model=args.model, host=args.host,
                             timeout=args.timeout)
    router = agent.AgentRouter(llm=llm)

    print(f"model: {args.model}")
    print("warming up (this also loads the weights — a cold model is the "
          "worst case a user could hit)...")
    started = time.monotonic()
    if not llm.warmup():
        raise SystemExit(f"  cannot reach Ollama: {llm.error}\n"
                         f"  is `ollama serve` running, and is the model pulled?")
    print(f"  loaded in {time.monotonic() - started:.1f} s\n")

    state = agent.state_summary(_SCENE, None, 0.0)
    timings, abstentions = [], 0
    for run in range(args.runs):
        for prompt in _PROMPTS:
            started = time.monotonic()
            result = router.route(prompt, state)
            elapsed = time.monotonic() - started
            timings.append(elapsed)
            if result.source == "abstain":
                abstentions += 1
            actions = ", ".join(
                f"{a.tool}({a.arg})" if a.arg else a.tool
                for a in result.actions) or f"abstain:{result.ask}"
            if run == 0:
                print(f"  {elapsed:5.2f}s  {prompt!r} -> {actions}")

    ordered = sorted(timings)
    p50 = statistics.median(ordered)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    print(f"\n{len(timings)} routes: p50 {p50:.2f}s  p95 {p95:.2f}s  "
          f"max {ordered[-1]:.2f}s")
    print(f"abstained on {abstentions} (one of the six prompts is "
          f"out-of-scope by design, so 1 per run is correct)")

    if p95 < 1.5:
        verdict = "COMFORTABLE — tier 1 is usable as-is"
    elif p95 < 3.0:
        verdict = ("USABLE — keep the spoken acknowledgement; consider a "
                   "smaller model")
    else:
        verdict = ("TOO SLOW — try a smaller model, or report local routing "
                   "as on-demand-only and say so in the paper")
    print(f"\nverdict: {verdict}")
    print("\nAccuracy is NOT measured here — run eval_agent.py for that.")


if __name__ == "__main__":
    main()
