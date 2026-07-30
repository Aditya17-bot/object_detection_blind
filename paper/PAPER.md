# Say Less, Never Mislead: Cross-Layer Selective Abstention in an Offline Assistive Perception System, Extended to a Tool-Mediated Voice Agent

**Status:** working draft, 2026-07-30. Results sections are **reserved** — the
routing numbers do not exist until the router runs (see `EVAL_PROTOCOL.md`,
frozen before implementation). Convert to ACM LaTeX only at submission.

**Target venue:** ASSETS Late-Breaking Work / poster. Alternates: W4A, CHI LBW.
Post an arXiv preprint on submission. **Patent note:** a preprint is a public
disclosure — `PATENT_RESEARCH.md` must be current *before* posting.

**Authors:** Aditya (add full legal name, affiliation, co-authors before
submission).

---

## Abstract

*(reserved — write last, once §7 has numbers. Target ~150 words. Skeleton:
sighted users silently discard a system's wrong answers; blind users cannot.
We report BlindAssist, an offline camera-based guidance system for blind and
low-vision users, and argue that **selective abstention** — declining to speak
when an output would be unreliable — is a first-class design objective at
every layer, not an error-handling detail. We show four concrete mechanisms
spanning perception, planning, transport, and dialogue, the last being a
tool-mediated voice agent in which a local offline language model may select a
capability but never author what the user hears. We evaluate routing on N
labelled utterances across five categories and report accuracy, over-trigger
rate on out-of-scope input, latency, and fabricated-perception counts.)*

---

## 1. Introduction

A sighted person using an assistive app performs a silent, continuous audit.
The app says "chair on your right"; they glance right; there is no chair; they
discard the claim and lose nothing. That audit loop is invisible in design
documents precisely because it is free.

For a blind user it does not exist. Every spoken claim is accepted or acted on,
because there is no cheap channel to check it against. This asymmetry inverts a
default that most interactive systems take for granted: **answer something**.
Under the asymmetry, a confidently wrong answer is not a degraded answer — it is
worse than silence, because silence costs the user one query and a wrong answer
costs them their calibration of when to trust the system at all.

This paper reports on BlindAssist, a working offline guidance system (Python
reference implementation plus an Android/Flutter port, driven by a shared
pure-logic core with mirrored test suites), and makes one architectural claim:

> Under the verification asymmetry, **selective abstention should be designed
> per layer, with layer-specific abstention criteria** — not delegated to a
> single confidence threshold at the output.

We support the claim with four mechanisms already implemented and tested in the
system (§4), and then extend it to a layer that did not previously exist in
BlindAssist: the **dialogue layer** (§5). The extension is a voice agent in
which a local, offline language model is granted authority to *select* one of
thirteen deterministic capabilities, and no authority whatsoever to *author*
spoken content. Fabricated perception is therefore prevented structurally, not
discouraged by prompt engineering.

**Contributions.**

- **C1 — A cross-layer selective-abstention pattern**, instantiated four times
  with layer-specific criteria: reliability-gated metric distance (perception),
  openness-thresholded path advice (planning), fail-safe absence-vs-negative
  (transport), and routing abstention (dialogue, new).
- **C2 — A tool-mediated voice agent** for a safety-critical speech channel: the
  model emits only a validated `{tool, args}` pair drawn from a fixed registry;
  every spoken token originates in deterministic code or a fixed template,
  including clarifying questions.
- **C3 — Deterministic-first two-tier routing.** A zero-latency keyword grammar
  handles trained phrasings with no model and no network; the language model is
  consulted only on a tier-0 miss. Median routing latency stays at ~0 ms and the
  system degrades to a working subset rather than to a wrong answer.
- **C4 — A capability registry with enforced cross-site consistency.** One
  declarative table drives the ASR phrase list, the model's tool schema, and the
  executor, and emits a committed manifest that both the Python and Dart test
  suites assert against.
- **C5 — An evaluation protocol and results** for routing under paraphrase,
  multi-intent, out-of-scope, and ASR-corrupted conditions, with abstention rate
  and fabricated-perception count reported as first-class metrics rather than as
  failure modes.

---

## 2. Related work

**Deployed assistive systems.** Cloud scene-description apps (Be My Eyes AI,
Microsoft Seeing AI, Envision AI) produce rich descriptions but are
latency- and connectivity-dependent, verbose by design, and not built for
continuous walking obstacle avoidance. Dedicated wearables (OrCam MyEye) give
excellent near-field OCR and face recall at hardware cost. Spatial-audio
navigation (Microsoft Soundscape) operates at GPS/beacon granularity rather than
in-frame object localisation. Google Lookout sits closest to our object-naming
mode. Electronic travel aids (WeWALK, Sunu Band, ultrasonic canes) give
proximity without object identity or fine direction.

None of these, as far as we are aware, treats *declining to answer* as a
designed, evaluated behaviour rather than an error path. This is the gap C1
addresses.

**Monocular distance and free space.** Single-image object-distance estimation
and free-space/drivable-area segmentation are mature, and ADAS work has strong
accuracy under calibrated, fixed-camera, upright-object assumptions. Our
setting violates all three (handheld, uncalibrated, frequently truncated
objects). We therefore optimise for an *honesty policy* rather than accuracy:
§4.1 withholds the number under precisely the geometric conditions that make it
wrong in the dangerous direction.

**Non-visual output modalities.** Obstacle sonification and wearable haptic
direction belts are well established; our contribution is not the modality but
the single ordinal-localisation core that drives speech, stereo sonar, and
haptics with consistent semantics and shared anti-spam timing.

**LLM tool use and hallucination containment.** Function calling / tool use is
standard practice, and constraining a model to structured output is not novel.
What we add is the *application* of the containment argument to a channel where
the consumer cannot verify: we show that once the model's authority is reduced
to selection over a closed registry — including the selection of which fixed
clarifying question to ask — the fabricated-perception rate is not a number to
be minimised but a quantity that is zero by construction, and we report the
LLM-only ablation to show what that constraint is buying.

**Voice interfaces for accessibility.** Wake-word and command-grammar
interfaces trade coverage for accuracy. Our two-tier design (§5.2) is an attempt
to have both: the grammar keeps its accuracy and its zero latency for the
phrasings users have learned, and the open-dictation path exists only behind an
explicit trigger.

*(TODO before submission: replace this section's implicit citations with a
proper reference list; the seed list is `PATENT_RESEARCH.md` §7, extended here
with the tool-use / containment line, which that disclosure does not yet cover.)*

---

## 3. System

### 3.1 Pipeline

```
camera frame
  → object detection      YOLOv8s (COCO) + a custom door/dustbin model
  → position analysis     position.py — ordinal zone, proximity bucket,
                          gated metric distance, clock bearing
  → decision logic        decision.py — what (if anything) to say now
  → output                speech (TTS) · stereo sonar · haptic pulses
```

A parallel **input** path carries voice: offline speech recognition →
command parsing → the same decision core. §5 replaces the parsing stage of that
path with the agent layer.

### 3.2 Ordinal localisation

Each detection becomes an `ObjectInfo`: horizontal zone (left/centre/right),
vertical zone, proximity bucket (very close / close / medium / far, from box
area relative to frame area with per-class thresholds), normalised centre-x, an
optional distance in metres, and a spoken location phrase. Direction may be
spoken as thirds or as a **camera-frame clock bearing** (frame width spans
10–2 o'clock over the ~60° view), the latter being the default because
Orientation & Mobility instruction already teaches clock positions. We note in
§8 that this mapping is *not* a literal O&M bearing.

### 3.3 Pure-logic core, mirrored

All guidance logic lives in a layer with no camera, no model, and no real clock:
it takes plain bounding-box numbers and a monotonic timestamp. This layer is
implemented twice — Python reference and Dart/Flutter — with mirrored unit-test
suites (122 Python / 113 Dart tests passing as of 2026-07-16). Every spoken
string in this paper is emitted by a function in that layer and pinned by a
test that asserts the exact text.

### 3.4 Anti-spam timing

`GuidanceEngine.update(infos, now)` returns at most one message per frame under
four rules: 2-frame persistence (one-frame misdetections never speak), a 3 s
repeat cooldown, a 1.5 s minimum gap between any two messages, and an
**escalation override** — if the same obstacle's proximity bucket worsens, the
warning speaks immediately regardless of cooldown. In recorded-clip evaluation
this produced 8 announcements across 471 frames on a bedroom walkthrough with
zero phantom announcements.

### 3.5 Remote-primary architecture

On the target device (Galaxy S20 FE) on-device TFLite measured ~2.5 s per
inference for both the GPU and NNAPI delegates — the YOLOv8 head partitions
badly and every frame pays host↔accelerator copies. The system therefore
defaults to **tethered inference**: the phone ships raw YUV420 planes to a
laptop over Wi-Fi, which runs both models and returns normalised boxes, while
sonar, haptics, voice, and OCR stay native. Server compute measures ~750 ms per
frame at imgsz 640 (YOLOv8s 516 ms + custom model 231 ms) and ~470 ms at
imgsz 480; the phone observes ~1 FPS end to end. UDP auto-discovery removes
per-session IP configuration, including the case where the phone itself is the
access point (§8).

This architecture is not a novelty claim — edge offload is well known — but it
is what preserves the sub-second guidance budget the rest of the design assumes,
and it is what creates the transport-layer failure mode that §4.3 addresses.

---

## 4. Abstention mechanisms

Each subsection states the mechanism, its specific failure mode, and why
silence beats the wrong answer there. All four are implemented and covered by
named tests (§6.1).

### 4.1 Perception: reliability-gated metric distance

Distance comes from a pinhole model, `distance = real_height × F /
box_height_fraction`, with `F` the vertical focal length as a fraction of frame
height (one constant, ≈0.85 for a phone in portrait) and `real_height` from a
per-class table. The number is spoken as "about N metres" only when **three
gates** all pass:

1. **Edge-clip gate.** If the box touches the top or bottom frame edge, its
   height is truncated and the model reads *falsely far*. This is the important
   one: the error points in the dangerous direction, and it does so precisely
   for the nearest, largest objects — the ones most likely to be clipped.
2. **Confidence gate.** Below the name-confidence threshold the class may be a
   misdetection, and a wrong class means a wrong `real_height`, i.e. a
   confidently wrong number.
3. **Range gate.** Only medium/far. Up close the estimate is least reliable and
   the ordinal bucket already conveys "here".

When any gate fails, the system speaks the ordinal proximity bucket instead.
Metres are also **Find-mode only**: continuous walk warnings stay short, because
the actionable token there is the direction.

### 4.2 Planning: openness-thresholded path advice

On demand ("which way is clear?"), each of left/centre/right is scored by the
**proximity rank of its closest obstacle**, not by summed occupied area. The
naive area metric inverts under a common case — a far bulky object outweighs a
near small hazard — and steers the user *toward* the danger. Doorways are
excluded from obstacle mass (a door is the thing you walk *through*), and far
objects are ignored.

The abstention is the threshold: if even the emptiest third contains a
close obstacle, the system does not return a least-bad direction. It says
**"Stop, no clear path."** An always-answer recommender has no way to express
"none of these is acceptable", and a blind user acting on its least-bad output
walks into something.

### 4.3 Transport: fail-safe absence vs. negative

Under tethered inference a frame can fail — timeout, Wi-Fi blip, server death.
The detector returns **`null` for no-data**, never `[]`. Downstream, `[]` is not
absence; it is a *verified-clear scene*, and acting on it has three specific
consequences: sonar falls silent (silence means "path clear"), walk-mode
escalation state resets, and Find mode reports "not visible" for an object that
may be directly ahead.

On no-data the engine **pauses** guidance rather than acting, and — critically —
says so: "Connection lost, guidance paused" after five consecutive misses, and
"Guidance restored" on recovery. The system never converts its own outage into a
confident wrong answer, and it never lets a blind user mistake an outage for an
empty room.

### 4.4 Dialogue: routing abstention (new)

The three mechanisms above concern what the system *says about the world*. The
fourth concerns what it does when it does not understand what it was *asked*.

The keyword baseline abstains by construction — an unmatched utterance returns
nothing — but it abstains far too often, because it cannot hear paraphrases at
all (§5.1). A language-model router fixes the coverage problem and introduces a
new failure: routing an out-of-scope request ("what's the weather?", "call my
mum") to the nearest available tool, which produces a confident, well-formed,
completely irrelevant spoken answer. §5.3 describes the mechanism; §6 measures
it as **over-trigger rate**, and treats it as the safety metric of the agent
layer.

---

## 5. The agent layer

### 5.1 The problem the grammar creates

BlindAssist's offline recogniser is *grammar-constrained*: it is built with an
explicit list of ~200 phrases, and only those phrases can be transcribed at all.
This is a good trade for a small offline acoustic model — recognition accuracy
on the trained phrasings is much higher than free dictation — but it means
free-form speech is not mis-parsed, it is **never heard**. "Where's my water
bottle" does not become a bad transcript; it produces nothing. Any natural-speech
layer therefore requires an open-dictation path as a precondition, not as a
refinement.

### 5.2 Two-tier routing

```
utterance
  │
  ├─ Tier 0  keyword grammar (parse_command)      ~0 ms, no model, offline
  │            hit → action
  │            miss ↓
  └─ Tier 1  local offline LLM over the registry  → validate → action
                                                  → reject  → abstain
```

Tier 0 is the existing parser, unchanged. Tier 1 is consulted only on a miss.
Three properties follow, and all three are why the tiering exists rather than
replacing the parser outright:

- **Median routing latency stays ~0 ms.** Trained users pay nothing for the
  agent's existence.
- **The system runs with no model present.** With the LLM disabled the router
  is behaviourally identical to today's system; this is enforced by a
  regression test over every phrase in the grammar.
- **Degradation is toward fewer capabilities, never toward wrong ones.** If the
  LLM is unavailable, unmatched utterances abstain instead of being guessed at.
  This mirrors the transport rule of §4.3 one layer up.

Open dictation is opened by a **trigger word** inside the grammar (e.g.
"assistant"). Hearing it records a short window, transcribes it with a local
Whisper model on the tether laptop, and routes the result. Tier 0 is therefore
untouched by the addition — the recogniser's constrained grammar keeps doing
exactly what it does today, and only an explicitly requested utterance takes the
open path.

### 5.3 The authority boundary

The model is given a system prompt containing the tool registry (name,
one-line description, argument type) and the class enumeration once, plus a
deterministic state block (§5.4) and the utterance. It must return JSON of the
form `{"actions": [{"tool": ..., "args": {...}}]}`.

Everything after that point treats the model's output as **untrusted input**:

- Unknown tool name → reject.
- Argument not in the class enumeration (which is derived from the detector's
  own class list, so it cannot drift) → reject.
- Missing required argument, malformed on/off value, more than `max_actions`
  actions → reject.
- Prose instead of JSON, timeout, or any exception → reject.

Every rejection becomes **abstain**. And abstain does not mean the model gets to
explain itself: the clarifying question is selected from a fixed template table
by key. The model may choose *which* question is asked; it may not write one.

The result is that no token the user hears has ever passed through the language
model. Spoken content originates in `decision.py`/`position.py` — the same
functions, pinned by the same tests, that the button-driven UI calls — or in a
fixed template. This is what makes the fabricated-perception count zero by
construction rather than by measurement, and §6.5 reports the LLM-only ablation
to show what that constraint is worth.

An implementation constraint worth recording: the router must never raise. In
this codebase an exception thrown on the voice thread silently kills voice
recognition for the entire session — an incident that actually occurred when a
new command reached a dispatcher that did not know about it. The router
therefore catches everything and converts it to abstain.

### 5.4 Deterministic state summary

Multi-turn references ("is it still there", "the other one", "find it") need
context. Supplying that context as pixels or as free description would put
perception back inside the model. Instead the router receives a compact,
deterministic block built from the current `ObjectInfo` list and engine state:
mode and target, bearing style, visible classes with zone/proximity/count, the
last thing said, and the class names currently held in object memory.

"Is it still there" therefore resolves against the detector's own output. The
model's job is reduced to mapping an English phrase onto a tool and an argument
drawn from a closed set — a task small enough for a 1–4 B local model, which is
the point.

### 5.5 Capability registry

Thirteen capabilities exist today: walk, find, describe, count, recall, path,
read, clock, zones, sonar, mute, stop, repeat. Before this work they were
declared in four places — a Python parser, its phrase list, a Python dispatcher,
and the Dart equivalents — and the sites had already drifted: the web
dispatcher silently dropped five capabilities the parser could produce.

The registry is one declarative table. It drives the recogniser's phrase list at
runtime, generates the model's tool schema, backs a single executor, and emits a
committed manifest that both language's test suites assert against. We claim
*enforced consistency across sites*, not literal single-source generation: the
field-validated parser is deliberately left in place rather than regenerated,
because the regression risk of rewriting it exceeds the value of the stronger
claim.

### 5.6 Latency handling

A local model on a CPU-only laptop is not free. Two design responses are built
in rather than tuned in later. First, the model is kept resident between
queries; a cold reload costs seconds and would land on exactly the utterance the
user cared about. Second, tier-1 entry immediately speaks a short
acknowledgement, because the speech layer is latest-wins and the real answer
simply replaces it. Unexplained silence is the specific failure this system
already designs against elsewhere — the same reasoning produced the "Still
looking for X" reminder in Find mode, after a field session where silence read
as "the app died".

---

## 6. Evaluation

Protocol and metric definitions are frozen in `EVAL_PROTOCOL.md`, and the
labelled utterance set in `eval_set.jsonl` was authored and committed **before**
the router was implemented. This ordering is deliberate: it prevents the router
from being tuned against its own test set.

### 6.1 Existing system (prior evaluation, for context)

Recorded-clip evaluation over 7 phone clips: direction accuracy 100 % of
reviewed announcement keyframes, 0 phantom announcements, 5.8 FPS / 172 ms per
frame on the development laptop, announcement latency ≈0.35–0.5 s. The known
weakness is object *naming*, not object *warning*: COCO assigns the nearest
lookalike (dustbin → "toilet", wardrobe → "refrigerator"), which is why
low-confidence warnings speak the generic word "obstacle" instead of a class
name. Gate behaviours are pinned by named tests
(`test_clipped_box_suppresses_meters`, `test_low_confidence_suppresses_meters`,
`test_meters_are_find_mode_only_not_walk`, `test_all_blocked_says_stop`,
`test_door_is_not_an_obstacle_for_path`, `test_near_small_hazard_beats_far_bulk`).

### 6.2 Routing evaluation

~200 labelled utterances across five categories — `canonical` (phrasings the
grammar already covers), `paraphrase`, `multi_intent`, `out_of_scope` (gold
label: abstain), and `ambiguous` (gold depends on a state block encoded in the
record) — evaluated under three configurations (keyword-only, LLM-only,
two-tier) and two ASR conditions (clean text, and real transcripts from
multiple speakers).

### 6.3 Metrics

Routing accuracy (exact match on the ordered action list), **over-trigger rate**
on out-of-scope input, tier-0 coverage, latency p50/p95 per stage, and
fabricated-perception count. Definitions and the fabrication detector's known
crudeness are in `EVAL_PROTOCOL.md`.

---

## 7. Results

The **keyword baseline is measured**; the two LLM configurations are reserved
until the router runs on hardware with a local model (`eval_agent.py --config
two_tier --model …`). Numbers below come from
`test_output/agent_eval_keyword.md`, eval set sha256 `e4eeca83070e2d66`.

**T3 — Routing accuracy by category and configuration.**

| Category | n | keyword | LLM-only | two-tier |
|---|---|---|---|---|
| canonical | 40 | **100.0 %** (40/40) | | |
| paraphrase | 70 | **0.0 %** (0/70) | | |
| multi_intent | 20 | **0.0 %** (0/20) | | |
| out_of_scope | 40 | **95.0 %** (38/40) | | |
| ambiguous | 30 | **3.3 %** (1/30) | | |
| **overall** | 200 | **39.5 %** (79/200) | | |

Overall Wilson 95 % CI for the baseline: 33.0–46.4 %.

The baseline's shape is the paper's motivation stated as data. It is perfect on
the phrasings it was designed for and *zero* on paraphrase and multi-intent —
not degraded, absent, because a grammar-constrained recogniser cannot hear what
is not in its grammar (§5.1). It is also, notably, already good at abstention:
95 % on out-of-scope, because an unmatched utterance returns nothing. Tier 1
must not spend that.

Tier-0 routing latency, for the C3 claim: **p50 5 µs, p95 13 µs**. This is why
the tiering is worth its complexity — the users who have learned the command
phrases pay literally nothing for the agent's existence.

**T4 — Latency p50/p95 (ms) per stage and ASR condition.**

| Stage | clean p50 | clean p95 | ASR p50 | ASR p95 |
|---|---|---|---|---|
| transcription | | | | |
| routing (tier 0) | | | | |
| routing (tier 1) | | | | |
| execution | | | | |
| **utterance → speech** | | | | |

**T5 — Out-of-scope behaviour (n = 40).**

| Configuration | abstain | wrong tool | over-trigger rate |
|---|---|---|---|
| keyword | 38 | 2 | **5.0 %** (CI 1.4–16.5 %) |
| LLM-only | | | |
| two-tier | | | |

Both keyword over-triggers are instructive rather than anomalous, and both are
substring collisions: *"read my email"* contains "read" and routes to the OCR
reader; *"how do i get to the bus stop"* contains "stop" and halts the current
announcement. Neither is a bug in the parser — they are the price of matching
on keywords, and they are exactly the errors a router with sentence-level
context should remove.

**T6 — Fabricated perception.**

| Configuration | fabricating responses / n |
|---|---|
| keyword, tool-mediated | **0 / 200** (verified) |
| LLM-only, free text | |
| LLM-only, tool-mediated | |
| two-tier | |

The verification is not a claim that nothing was fabricated; it is a check that
every spoken string in the run was a member of the set `decision.py` /
`position.py` could produce for that record, plus the fixed templates. The
harness fails loudly on any string outside that set, so the boundary is
monitored on every run rather than argued for once.

**Figures.** F1 system diagram with the agent as a parallel input path and an
explicit perception-authority boundary; F2 two-tier router flow including the
abstain branch; F3 latency waterfall (ASR → route → execute → speak); F4
accuracy by category across the three configurations; F5 routing confusion
matrix (13 tools + abstain).

---

## 8. Discussion and limitations

**No blind-participant study.** The system has been field-walked by a single
sighted developer. Every claim in this paper about what is *safer* for a blind
user is a design argument supported by mechanism and by deterministic tests —
not by user data. An IRB-approved study with blind participants is the obvious
and necessary next step, and specifically the one that could falsify the central
premise: it is possible that users prefer a guessed answer to an abstention,
and that the over-trigger metric we optimise against is not the one that matters
to them.

**The clock mapping is camera-frame, not O&M.** Frame width spans 10–2 o'clock
over roughly a 60° field of view, so "2 o'clock" means the right frame edge
(~30°), not the literal 90° an O&M-trained traveller would turn to. A trained
user may over-rotate. This needs either relabelling or a genuine remapping
before the system claims compatibility with O&M training.

**Distance is coarse.** Roughly ±30–40 % at 5 m with an uncalibrated focal
constant. The reliability-gating argument of §4.1 does not depend on accuracy —
it is about *when* to speak a number, not how good the number is — but a
one-time per-device calibration would strengthen any accuracy claim.

**Clear-path scores box centres only.** A wide object straddling two thirds is
scored in its centre third alone. Box-extent scoring is a known fix.

**Tether dependency.** The remote-primary architecture assumes a laptop and a
local network. §4.3 makes the failure safe, not absent. On-device viability
awaits either a lighter detector head or hardware where the delegate partitions
cleanly.

**Local-model routing has a latency floor.** Tier 1 costs whatever a small
instruct model costs on the user's CPU. §5.6 mitigates the two worst cases
(cold reload, unexplained silence) but does not eliminate the floor. If the
measured floor proves too high on commodity hardware, the honest framing is that
local routing is viable for on-demand queries and not for anything inside the
continuous guidance loop — which is where all thirteen capabilities happen to
live, but that is a fact about this system, not a general result.

**The fabrication detector is keyword-based.** It flags a response naming a
detector class absent from the state block. It will miss subtler fabrication
(invented spatial relations, invented counts of a class that *is* present) and
will occasionally over-flag. Reported as a lower bound.

---

## 9. Conclusion

For users who cannot audit what a system tells them, abstention is not an error
path — it is a feature that must be designed, implemented, and measured at every
layer where the system can be wrong. We showed four such designs in a working
offline assistive system, each with criteria specific to its layer's failure
mode, and extended the pattern to a voice agent whose language model may choose
what the system does and never what it says. The interesting claim is not that
tool mediation prevents hallucination — it plainly does — but that the same
principle that motivates it also explains a distance gate, a path threshold, and
a null-versus-empty distinction three layers away.

---

## Appendix A — Capability registry (T1)

| Tool | Argument | Spoken examples | Backing function |
|---|---|---|---|
| `walk` | — | "walk mode" | `GuidanceEngine.set_mode('walk')` |
| `find` | class (required) | "find the bottle" | `set_mode('find', c)` → `decision.find_message` |
| `describe` | — | "describe the scene" | `decision.summarize_scene` |
| `count` | class (required) | "how many chairs" | `decision.count_message` |
| `recall` | class (required) | "where is my cup" | `GuidanceEngine.recall` |
| `path` | — | "which way is clear" | `decision.clear_path` |
| `read` | — | "read the text" | on-device OCR |
| `clock` | — | "clock mode" | `GuidanceEngine.set_clock(True)` |
| `zones` | — | "zone mode" | `GuidanceEngine.set_clock(False)` |
| `sonar` | on/off (optional) | "sonar off" | sonar controller |
| `mute` | on/off (required) | "unmute" | speech controller |
| `stop` | — | "stop" | speech controller |
| `repeat` | — | "say again" | speech controller |
| `abstain` | template key | — | fixed template table |

## Appendix B — Figure sketches (F1, F2)

**F1 — System, with the agent as a parallel input path.** The dashed boundary is
the authority claim of §5.3: nothing on the left may author text that crosses it.

```mermaid
flowchart LR
    CAM["camera"] --> DET["YOLOv8s + custom<br/>door/dustbin model"]
    DET --> POS["position.py<br/>zone · bucket · gated metres"]
    POS --> DEC["decision.py<br/>what to say now"]
    DEC --> OUT["speech · sonar · haptic"]

    MIC["microphone"] --> ASR["Vosk grammar<br/>/ Whisper dictation"]
    ASR --> RT["agent.py router"]
    RT -.->|"tool + arg only"| DEC

    subgraph untrusted["model may SELECT"]
      RT
    end
    subgraph trusted["deterministic — authors all spoken text"]
      POS
      DEC
    end
```

**F2 — Two-tier router with the abstain branch.**

```mermaid
flowchart TD
    U["utterance"] --> T0{"tier 0<br/>keyword grammar"}
    T0 -->|"hit (~0 ms)"| ACT["validated action list"]
    T0 -->|"miss"| L{"LLM enabled?"}
    L -->|"no"| AB["abstain →<br/>fixed template"]
    L -->|"yes"| M["local LLM<br/>JSON tool call"]
    M --> V{"validate:<br/>known tool? known class?<br/>arg present? ≤ max actions?"}
    V -->|"pass"| ACT
    V -->|"reject / prose / timeout / exception"| AB
    ACT --> EX["execute_action → decision.py"]
    AB --> SP["speak template"]
    EX --> SP

    style AB fill:#fde,stroke:#c39
    style ACT fill:#dfe,stroke:#3a6
```

## Appendix C — Eval-set composition (T2)

| Category | n | Gold label | Purpose |
|---|---|---|---|
| `canonical` | 40 | tool | Baseline sanity — keyword config must score ~100 % |
| `paraphrase` | 70 | tool | The coverage gap the agent exists to close |
| `multi_intent` | 20 | 2 tools | Ordered action lists |
| `out_of_scope` | 40 | abstain | Carries the C1 dialogue claim |
| `ambiguous` | 30 | tool, state-dependent | Tests the deterministic state block |
