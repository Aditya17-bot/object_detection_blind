# BlindAssist — Patent & Research Disclosure

**Status:** living document, updated as the project evolves (started 2026-07-14).
**Working title:** *A camera-based assistive guidance system for visually
impaired users combining ordinal object localisation, multi-modal output, and
reliability-gated monocular distance estimation.*
**Inventor(s):** Aditya (add full legal name + any co-inventors before filing).
**Assignee:** (student project — decide before filing).

> ⚠️ **Not legal advice.** This file is a *technical disclosure* to seed a
> provisional patent application and/or a research paper. Patentability requires
> a professional **prior-art / novelty search** and a patent attorney. Several
> individual components below exist in prior art; the strongest case is the
> **specific combination + the blind-safety reliability gating**, not any single
> block in isolation. Treat "Candidate claims" as discussion starters.

---

## 1. Field of the invention

Assistive technology for blind and low-vision users; real-time computer vision
on a commodity smartphone; multi-modal (speech + spatialised audio + haptic)
non-visual human-computer interaction; hands-free voice control.

## 2. Problem / background

Existing aids fall into groups, each with gaps:

- **Cloud "describe the scene" apps** (e.g. Be My Eyes AI, Seeing AI, Envision):
  rich descriptions but latency- and connectivity-dependent, verbose, and not
  built for *continuous walking* obstacle avoidance.
- **Wearable OCR/near-field readers** (e.g. OrCam MyEye): expensive dedicated
  hardware.
- **Spatial-audio navigation** (e.g. Microsoft Soundscape): GPS/beacon-level
  guidance, not fine-grained in-frame object localisation.
- **Ultrasonic canes / parking-sensor aids**: distance beeps, no object
  identity, no direction beyond crude.

None combine, fully **offline on one phone**: (a) per-object *ordinal* direction
+ proximity, (b) a shared pure-logic decision core driving speech AND stereo
sonar AND haptic, (c) offline grammar-constrained voice control, (d) object
*memory* to relocate a thing that has left the frame, and (e) a monocular
distance estimate that **refuses to speak when it would be unreliable** — a
safety property specific to non-visual users who cannot sanity-check a number.

## 3. System overview

Pipeline: **Camera → object detection (YOLOv8n TFLite, + a small custom
door/dustbin model) → position analysis → decision logic → output (TTS / sonar
/ haptic)**, with an offline voice-command listener (Vosk) as a parallel input.

Architectural principle (relevant to several claims): **all guidance logic lives
in a pure, model-free, camera-free layer** (`position.*`, `decision.*`,
`voice_commands.*`) that takes plain bounding-box numbers and a monotonic clock,
and is mirrored 1:1 across a Python reference and a Dart/Flutter implementation,
each covered by an identical unit-test suite (100 Python / 89 Dart tests as of
2026-07-14). This makes the behaviour deterministic, portable, and verifiable —
useful both as an engineering practice and as *reduction-to-practice* evidence.

## 4. Novel / candidate-novel features (the disclosure)

Each item: what it is, how it works, why it may be non-obvious, closest known
prior art. Ranked by perceived strength of the novelty case.

### 4.1 Reliability-gated monocular distance for non-visual users *(strongest)*
- **What:** a rough distance in metres from a single frame, spoken as "about N
  metres", but **suppressed whenever the estimate is untrustworthy**.
- **How:** pinhole model `distance = real_height × F / box_height_fraction`,
  where `F` is the vertical focal length expressed as a fraction of frame height
  (one calibration constant, ~0.85 for a typical phone in portrait), and
  `real_height` comes from a per-class table. Then three **gates** decide
  whether to *speak* it: (1) **edge-clip gate** — if the bounding box touches
  the top/bottom frame edge its height is truncated and the pinhole reads
  *falsely far*; the number is withheld (critical: the failure mode points the
  wrong way — it under-warns for the closest, most dangerous objects); (2)
  **confidence gate** — below a name-confidence threshold the class (hence the
  assumed height) may be a misdetection, so no number; (3) **range gate** — only
  medium/far; up close the coarse proximity bucket is used because the estimate
  is least reliable there and "close" already conveys "here".
- **Why non-obvious:** prior monocular-distance work optimises for *accuracy*.
  Here the inventive step is the opposite: an *honesty policy* that treats a
  wrong absolute number as worse than silence *because the consumer is blind and
  cannot visually reject it*. The gating conditions are tied to the specific
  geometric failure modes (clipping, misclassification) of handheld,
  non-upright, partially-framed capture.
- **Prior art to distinguish:** generic monocular depth/size-based ranging;
  ADAS distance estimation (assumes calibrated, fixed camera, upright vehicles).

### 4.2 Clear-path finder by nearest-obstacle ranking *(strong)*
- **What:** on demand ("which way is clear?"), names the most open of
  left/ahead/right, or says **"Stop, no clear path."**
- **How:** each direction third is scored by the **proximity rank of its
  closest obstacle** (not summed box area), doorways are *excluded* from
  obstacle mass (a door is to walk *through*), far objects ignored, and an
  absolute-openness threshold produces an honest "Stop" instead of always
  returning a "least-bad" direction.
- **Why non-obvious:** the naive metric (occupied area per region) inverts under
  a common case — a far bulky object outweighs a near small hazard — steering
  the user *toward* danger. Ranking by nearest-obstacle proximity + a stop
  threshold + door exclusion is the corrective insight.
- **Prior art to distinguish:** free-space/drivable-area segmentation (needs
  dense depth/semantic seg); robot obstacle-avoidance cost maps.

### 4.3 Object memory / "where did I leave it" recall *(moderate)*
- **What:** the system remembers each object class's last sighting (direction +
  how-long-ago), so it can answer "where is my cup?" after the cup has left the
  frame, and automatically turns a Find-mode "not visible" into "last seen on
  your left" — a lead to follow rather than a dead end. Memories older than a
  TTL go stale.
- **Why non-obvious:** couples short-term visual memory to the *speech* layer
  specifically to solve the blind-user failure of losing an object the instant
  it exits view.
- **Prior art:** object tracking/re-ID (persistence *within* view); reminder
  apps (manual).

### 4.4 Unified ordinal-localisation core driving three output modalities *(moderate — combination)*
- **What:** one pure decision function emits a single "what to say/feel now",
  and the same per-object `ObjectInfo` (direction third, proximity bucket,
  centre-x, optional distance) drives **speech**, **stereo-panned proximity
  sonar** (parking-sensor-for-walking: pan = direction, tick-rate + pitch =
  closeness), and **haptic**, with shared anti-spam timing (persistence,
  cooldown, min-gap, escalation override).
- **Why non-obvious:** the combination + the single-source-of-truth
  localisation feeding heterogeneous modalities with consistent semantics.

### 4.4a Offline OCR text reader as part of the combination *(supporting)*
- **What:** on demand ("read"), the same phone captures a still and reads
  printed text aloud (labels, signs, mail, medicine) via on-device OCR —
  fully offline.
- **Role in the claim:** OCR alone is well-known prior art (Seeing AI, OrCam).
  Its value here is *combination breadth*: a single offline app that switches
  between continuous obstacle guidance, object find/count, scene summary, AND
  text reading, all hands-free by voice, with no cloud. Strengthens an
  "integrated multi-function offline assistant" combination claim; weak alone.

### 4.4b On-demand object counting *(minor)*
- **What:** voice "how many chairs" → spoken count of that class currently
  visible. Trivial mechanism; included for completeness of the voice-command
  surface, not as an independent novelty.

### 4.7 Tool-mediated voice agent with routing abstention *(strong — the dialogue-layer instance of the §9 thesis)*
- **What:** the user speaks naturally; a **local, offline** language model
  chooses which of the system's deterministic capabilities to run, and is given
  **no authority to author any spoken content whatsoever**. It emits a
  `{tool, argument}` pair and nothing else. Every word the user hears still
  comes from `decision.py` / `position.py` — the same functions the buttons
  call, pinned by the same tests — or from a fixed template table.
- **How:**
  1. **Two-tier routing.** Tier 0 is the existing grammar-constrained keyword
     parser (measured p50 **5 µs**, p95 13 µs, no model, no network). Tier 1 is
     consulted only on a tier-0 miss. Median routing latency is therefore
     unchanged for trained phrasings, and the system still works with no model
     present at all — degradation is toward FEWER capabilities, never toward
     wrong ones (the same rule as §4.3's transport fail-safe, one layer up).
  2. **Closed-registry validation.** One declarative capability table generates
     the recognizer's phrase list, the model's tool schema, the executor, and a
     committed `capabilities.json` manifest. The model's output is treated as
     untrusted input: unknown tool, unknown object class (the enum is derived
     from the DETECTOR's own class list, so it cannot drift), missing required
     argument, malformed value, prose instead of JSON, timeout, or any
     exception all become **abstain**.
  3. **Template-only clarification.** Even the clarifying question is selected
     by key from a fixed table. The model may choose *which* question is asked;
     it may not write one. This is what makes "no spoken token originates in
     the model" absolute rather than approximate.
  4. **Deterministic state block.** Multi-turn references ("is it still
     there") resolve against the current `ObjectInfo` list and engine state —
     visible classes with zone/proximity/count, mode, last announcement,
     object memory — never against a description. Perception never re-enters
     the model.
  5. **Trigger-word dictation.** The offline recognizer's grammar is a closed
     list, so free speech is not mis-heard, it is never heard. A trigger word
     opens a short window that goes to an open-vocabulary transcriber and then
     to the router, which keeps tier 0 both accurate and instant. The trigger
     is evaluated LAST in the parser, so it can only fire on an utterance no
     real command claimed. Two transcriber implementations, chosen by what is
     reachable: local Whisper on the tethered machine, or — on the handset —
     **a second recognizer built on the same already-loaded model with its
     grammar removed**, swapped in for one utterance and swapped back. The
     second is less accurate and deliberately so: it keeps free speech
     available with no server and no additional model, and its transcript is
     still passed through the deterministic parser before the router is
     consulted. Every failure path restores the command recognizer, because
     losing dictation is an inconvenience and losing voice control is not.
  6. **The tier boundary may be a network link.** On the handset, tier 0 runs
     locally and only an unresolved utterance is posted to the tethered
     server's router. The reply is **re-validated on the client against the
     same closed registry** before execution, so the containment guarantee does
     not rest on trusting the transport; an unreachable server, timeout or
     unparseable body yields NO DATA (distinct from an abstention, and never a
     synthesised action); and a reply containing one unusable action is
     discarded whole rather than partially executed, since performing the half
     that happened to parse is itself an unverified action.
  7. **The boundary was narrowed, deliberately, on 2026-07-31** (user
     decision after the first hardware walk): the model may now author a
     **conversational reply**, and only that. The claim is therefore no longer
     "no spoken token originates in the model" but the sharper and more
     defensible **"no *guidance* token originates in the model"**. The split is
     enforced structurally, not by prompt: a reply travels in a separate `say`
     channel that the executor never routes through a capability; guidance
     (walk warnings, find, distance, clear path, directional query) is
     unreachable from that channel; unstructured prose emitted where a tool
     call belongs is still discarded, so a chatty model does not become speech
     by accident; replies are grounded in the same deterministic state block
     and are length-capped and sentence-truncated, because a user who cannot
     skim also cannot skip a monologue; and a single flag (`allow_chat=False`)
     restores the absolute rule, which is what the paper's ablation arm uses.
     Two hardware-observed failures are pinned as tests: a model that answered
     a greeting with the *internal* "listening" template (so the app sounded
     like it had mis-heard a trigger word — control templates are now
     unselectable), and a model that expresses its reply as a fake `say` tool
     call, which strict validation would have discarded as malformed, losing a
     legitimate answer over a format quibble.
- **Why non-obvious:** structured/constrained LLM output is well known. The
  step here is *why* it is applied: for a consumer who cannot visually reject a
  wrong answer, hallucination containment is not a quality improvement, it is a
  safety property, and the correct design target is not "minimise fabricated
  perception" but "make it impossible to express". Reducing the model's
  authority to selection over a closed registry — **including selection of the
  clarifying question** — achieves that by construction. The measured
  counterpart is the **over-trigger rate**: an always-answer router maps an
  out-of-scope request onto the nearest available tool and produces a
  confident, well-formed, irrelevant spoken answer.
- **Reduction to practice:** `agent.py` (registry, validator, router,
  executor), `agent_server.py` (POST /agent, shared by both servers),
  `transcribe.py`, `eval_agent.py`, 200-utterance frozen evaluation set with a
  protocol written BEFORE the router existed (`paper/`); on the handset,
  `lib/logic/agent_actions.dart` (mirrored registry + validator) and
  `lib/agent_client.dart` (local-first tiering, null-on-failure), with the
  Dart registry asserted field-by-field against the committed
  `capabilities.json`. Measured keyword
  baseline: canonical 100 %, paraphrase 0 %, out-of-scope abstention 95 %,
  boundary leaks 0/200.
- **Prior art to distinguish:** LLM function calling / tool use; constrained
  decoding; voice assistants with intent classifiers; retrieval grounding.
  None of these, as far as the search so far shows, frames the containment as a
  *non-visual-consumer safety* requirement or extends abstention across
  perception, planning, transport AND dialogue as one principle.

### 4.8 Attention budget: proximity-gated warnings plus on-demand directional query *(moderate — and the cleanest statement of the §9 thesis)*
- **What:** the continuous channel is cut back to a hazard threshold, and the
  information removed from it is made available on request instead. Concretely:
  walk warnings fire only at *close* or nearer (previously *medium* also spoke
  when centred), and a new deterministic capability answers "is there anything
  in front of me / on my left" with the two nearest objects in that third of
  the frame, closest first, with their proximity buckets.
- **Why:** from the first hardware walk (2026-07-31) the user's words were
  "it keeps saying all the objects but it's too much of a cluster". This is the
  failure mode the whole project's thesis predicts: a warning stream that
  exceeds the user's attention budget is not merely annoying, it is **less
  safe**, because the user stops parsing it and the one warning that mattered
  arrives inside noise they have already tuned out. An unheeded warning has
  negative value — it consumed attention and delivered nothing.
- **The design move:** do not suppress information, **change who initiates it**.
  Continuous output carries only what the user must act on now; everything else
  moves to a pull interface the user can spend attention on when they choose.
  The directional query is the pull counterpart of the walk warning: same
  ordinal localisation core, same proximity buckets, same trust gating on the
  class name (a low-confidence label is answered as "an obstacle"), but issued
  only on request and reporting *everything* detected in that direction rather
  than obstacles alone — because a user who asks has, by asking, granted the
  attention.
- **Non-obviousness angle:** the novelty is not the threshold value. It is
  treating the *rate* of assistive speech as a safety-relevant design variable
  with a push/pull split, in a system where the same perception core serves
  both channels, so the pulled answer is guaranteed consistent with the pushed
  warning — a claim a two-subsystem design (navigation aid + separate
  assistant) cannot make.
- **Evidence to gather:** announcements per minute before/after on the same
  recorded clips, plus the user's subjective load. The clips exist
  (`test_output/eval_*.mp4`), so the before/after is reproducible from the
  logged announcement streams.

### 4.5 Pulse-count haptic direction *(minor)*
- **What:** on a single-vibrator phone, direction is encoded by **number of
  pulses** (1 = left, 2 = ahead, 3 = right), firing only on a zone *change*.
- **Why:** users cannot reliably discriminate 3 vibration *amplitudes*; counting
  discrete taps is far more robust, and reserves intensity/rate for proximity
  (used by the sonar). Minor but a concrete, testable design choice.

### 4.6 Camera-frame clock-face bearings *(minor / likely prior-art-adjacent)*
- **What:** speaks direction as clock hours mapped across the camera's field of
  view (10–2 over ~60°), matching Orientation-&-Mobility clock training.
- **Note:** clock-direction speech for the blind is known; the only wrinkle is
  the explicit *camera-frame* remapping. Weak on its own; include only as part
  of the combination. (See open issue: mapping ≠ literal O&M bearings.)

## 5. Candidate independent claim (illustrative, non-final)

> A method for assisting a visually impaired user, comprising: capturing frames
> from a handheld camera; detecting objects and their bounding boxes on-device;
> for each detected object, computing an ordinal horizontal direction, an
> ordinal proximity category, and a monocular distance estimate from the box
> height and a stored per-class physical height; **conditionally converting the
> distance estimate to speech only when a set of reliability conditions is
> satisfied — the bounding box not being truncated by a frame edge, the
> detection confidence exceeding a threshold, and the proximity category being
> beyond a near range — and otherwise announcing only the ordinal proximity
> category**; and rendering the result as at least one of speech, stereo-panned
> audio whose pan encodes said direction and whose tempo encodes said proximity,
> and a haptic pulse train whose pulse count encodes said direction.

Dependent claims: the clip condition (edge thresholds); the "Stop, no clear
path" openness threshold; door exclusion from path scoring; object-memory recall
with staleness TTL; the shared pure-logic core driving multiple modalities;
offline grammar-constrained voice control of the modes.

## 6. Reduction to practice (evidence)

- Working Python prototype (desktop + phone-stream) and Flutter Android app,
  same pure-logic core, in this repository.
- Deterministic unit tests encode the exact spoken outputs and the safety gates:
  **107 Python + 96 Dart** tests passing as of 2026-07-14 (see `test_*.py`,
  `blindassist_app/test/*_test.dart`). Specific gate tests:
  `test_clipped_box_suppresses_meters`, `test_low_confidence_suppresses_meters`,
  `test_meters_are_find_mode_only_not_walk`, `test_all_blocked_says_stop`,
  `test_door_is_not_an_obstacle_for_path`, `test_near_small_hazard_beats_far_bulk`,
  and for §4.7: `test_prose_is_never_spoken`,
  `test_no_spoken_string_originates_in_the_model`,
  `test_invalid_action_abstains_rather_than_guessing`,
  `test_llm_exception_abstains_and_never_propagates`,
  `test_grammar_hit_matches_parse_command_exactly` (the tier-0 no-regression
  gate), `test_manifest_file_matches_the_registry`.
- Prior recorded-clip evaluation: `EVALUATION.md` (direction accuracy, FPS,
  false/missed-announcement counts).

## 7. Prior art to search before filing (starter list)

Be My Eyes AI, Microsoft Seeing AI, Envision AI, OrCam MyEye, Microsoft
Soundscape, Lookout by Google, Sunu Band, WeWALK cane, ultrasonic ETAs;
academic: monocular object-distance estimation, free-space detection for the
blind, sonification of obstacle proximity, wearable haptic direction belts.
Patents: search classes G06V (image/video recognition), A61H 3/06 (walking aids
for the blind), G08B (signalling), H04R (stereophonic).

**Abstention literature (added 2026-08-01 — a searcher hits this first).** The
idea of a system declining to answer is old and formalised, so no claim may rest
on abstention *as such*; what is argued is the per-layer criteria and the
application to an unverifiable channel.
- Classification with a reject option — Chow 1970; selective prediction
  (El-Yaniv & Wiener 2010; Geifman & El-Yaniv 2017); learning to defer (Madras
  et al. 2018; Mozannar & Sontag 2020); OOD/confidence baselines (Hendrycks &
  Gimpel 2017) and calibration (Guo et al. 2017). All of these threshold a
  *model's* score; §4.1-4.3, 4.7 and 4.8 each abstain on a criterion derived
  from the layer's own failure mode instead, which is the distinguishing point.
- Containment for generated language — tool use (Toolformer; ReAct; ToolLLM),
  constrained/guided decoding (PICARD; guided generation), hallucination surveys
  (Ji et al. 2023). §4.7's mechanism is standard practice; the argued novelty is
  the *consumer* — a user with no cheap way to reject a wrong answer — and the
  resulting design target of making fabricated perception inexpressible rather
  than merely rare.
- Reliance and false alarms — Parasuraman & Riley 1997; Lee & See 2004;
  Wickens & Dixon 2007 (the reliability crossover below which an imperfect alert
  is worse than none); Breznitz 1984; clinical alarm fatigue. This supports
  §4.8's "an unheeded warning has negative value" as an established human-factors
  result rather than an assertion, and is the strongest external support in the
  file for the whole thesis.
- The blind-user half of the asymmetry — MacLeod et al. 2017 (blind readers
  build confident interpretations of wrong captions); Adnin & Das 2024 (blind
  users of generative tools); Stangl et al. 2020. Cite these rather than
  asserting the asymmetry.

## 8. Open technical questions affecting claims

- Focal constant `F` is un-calibrated per device — distance is coarse; a
  one-time calibration step would strengthen accuracy claims (not required for
  the *reliability-gating* claim, which stands even with a rough estimate).
- Clock mapping is camera-frame, not literal O&M bearings — resolve before
  claiming "matches O&M training".
- Clear-path scores by box centre only; straddling wide objects need box-extent
  scoring for a stronger claim.
- GPU-delegate acceleration is unverified on the target device (may fall back to
  CPU); a latency claim needs on-device measurement.

## 8a. Prior art specific to §4.7 (search before filing or preprinting)

LLM function calling / tool use and constrained decoding (OpenAI, Anthropic,
Toolformer and successors); intent-classification voice assistants; grounded
generation and hallucination mitigation; "guardrail" / policy-router
architectures; accessibility voice agents. Patent classes to add: G06F 40/35
(dialogue systems), G10L 15/22 (speech-recognition control), G06N (models).
**Note:** an arXiv preprint is a public disclosure — file, or decide not to,
BEFORE posting.

## 9. Suggested paper framing (if academic route)

*"Honesty-gated perception for non-visual assistive guidance"* — thesis: for
users who cannot visually verify system output, **selective abstention** (say
less, but never mislead) is a first-class design objective, demonstrated via
(a) reliability-gated monocular distance and (b) an openness-thresholded
clear-path recommender, evaluated against a naive always-answer baseline on
recorded walkthroughs. Metrics: rate of confidently-wrong announcements avoided
vs. useful announcements retained.

## 10. Change log (keep appending)

- **2026-07-14** — initial disclosure. Documented: reliability-gated monocular
  distance (§4.1), nearest-obstacle clear-path with Stop + door exclusion
  (§4.2), pulse-count haptic (§4.5), clock-default + camera-frame caveat (§4.6),
  unified core (§4.4). Reduction-to-practice: 100 Python / 89 Dart tests. Prior
  design decisions (object memory §4.3, sonar, offline voice) folded in from
  earlier project work. See `CLAUDE.md` "Final-checklist pass (2026-07-14)".
- **2026-07-14 (update)** — added offline OCR text reader (§4.4a) and on-demand
  object counting (§4.4b) to the voice-command surface; both broaden the
  "integrated multi-function offline assistant" combination case. Dropped the
  favorites-beacon feature (user preference) — not in the codebase. Applied
  code-level fixes from an implementation-critique pass (native handle disposal,
  surfaced detector-init failure, haptic pulse-train guard). Reduction-to-
  practice updated to **107 Python / 96 Dart** tests.
- **2026-07-15** — architecture pivot to **laptop-tethered remote inference**
  (remote-primary, user decision): on-device TFLite measured ~2.5 s/inference
  on the S20 FE (GPU and NNAPI delegates both — yolov8 head partitions badly),
  so the phone now ships raw YUV420 planes to `infer_server.py` (yolov8s +
  door model, ~140 ms) over Wi-Fi and keeps sonar/haptics/voice/OCR native.
  UDP auto-discovery removes per-session IP configuration. Not itself a
  novelty claim (edge offload is known), but it preserves the sub-second
  guidance loop the other claims assume.
- **2026-07-15 (update)** — **fail-safe absence/negative distinction**, a
  direct extension of the §9 "selective abstention" thesis to the TRANSPORT
  layer: a failed remote frame returns null (no data), never an empty
  detection list, because downstream an empty list is a *verified-clear*
  scene — acting on it silences sonar (silence = "path clear"), resets walk
  escalation, and lets find mode claim "not visible" during a Wi-Fi blip.
  On no-data the engine PAUSES (guidance skipped, sonar muted) and the state
  is spoken ("Connection lost, guidance paused" / "Guidance restored") — the
  system never converts its own outage into a confident wrong answer for a
  user who cannot visually double-check. Also this pass: speech priority
  (user-requested read-outs protected from routine interruptions, safety
  escalations still cut through), portrait lock + wakelock/lifecycle
  hardening, TalkBack liveRegion + custom actions, voice stop/repeat/sonar/
  mute + plural grammar (mirrored Python/Dart). Reduction-to-practice
  updated to **121 Python / 112 Dart** tests.
- **2026-07-16** — **remote pipeline verified live end-to-end** on the
  S20 FE + hotspot: discovery, /health, streamed /infer, detections spoken.
  Two changes landed:
  (1) **Multi-target discovery broadcast** — Android hotspot mode routes the
  255.255.255.255 limited broadcast out the CELLULAR interface, so a phone
  that IS the access point never reaches its own clients with it. Fix:
  enumerate the phone's interfaces and ping each one's /24 DIRECTED broadcast
  (e.g. 10.250.253.255) alongside 255.255.255.255. This is the piece that
  makes zero-config discovery work when the assistive device itself provides
  the network — a deployment mode specific to this architecture.
  (2) **Find-as-task semantics** (user field feedback): announcing the
  target's position once IS the search result — the engine speaks it and
  auto-returns to walk mode instead of re-announcing while the target stays
  in view (which users read as "still searching"). Re-asking starts a new
  search. Mirrored Python/Dart.
  Measured: server compute ~750 ms/frame at imgsz 640 (yolov8s 516 +
  custom 231) on the tether laptop, ~1 FPS at the phone with occasional
  1.2 s-timeout drops; `--imgsz 480` server knob added (~470 ms/frame) as
  the field latency lever. Reduction-to-practice now **122 Python /
  113 Dart** tests. **[SUPERSEDED 2026-07-30 — these were CPU-only figures;
  the tether laptop's CUDA GPU was unused. Corrected numbers in the
  2026-07-30 GPU entry below. Do not cite 750 ms / 470 ms / `--imgsz 480`
  in any filing or preprint.]**
- **2026-07-30** — **dialogue-layer abstention** added as §4.7: a
  tool-mediated voice agent in which a local offline LLM may SELECT a
  capability but never author spoken content, with routing abstention on any
  validation failure. This completes the §9 thesis across four layers
  (perception §4.1, planning §4.2, transport §4.3-changelog, dialogue §4.7) —
  one principle, four layer-specific criteria, which is the framing the paper
  now leads with. Also this pass: a single capability registry replacing
  branches duplicated across four sites (the drift was real — `webapp.py`
  silently dropped read/sonar/stop/repeat/mute), `capabilities.json` as the
  committed cross-site contract, trigger-word open dictation via local
  Whisper, and POST /agent on both servers. **Research paper started** in
  `paper/`: draft, a protocol frozen BEFORE the router was implemented, and a
  200-utterance labelled routing set. Measured keyword baseline (set sha256
  e4eeca83): canonical 100 %, paraphrase 0 %, multi-intent 0 %, out-of-scope
  abstention 95 %, tier-0 routing p50 5 µs, authority-boundary leaks 0/200.
  Reduction-to-practice **199 Python** tests.
  ⚠ The paper is intended for arXiv — see §8a, that is a disclosure.
- **2026-07-30 (same day, handset)** — §4.7 extended with mechanism 6, the
  **network tier boundary**: the Dart agent client keeps tier 0 on the phone
  and re-validates the server's reply against the mirrored closed registry
  before executing it, so containment survives a compromised or merely buggy
  transport. Adds the whole-reply rejection rule (one unusable action voids the
  reply) and reuses §4.3's no-data-vs-abstention distinction on the dialogue
  path. Reduction to practice: `lib/logic/agent_actions.dart`,
  `lib/agent_client.dart`, **131 Dart tests** (was 113), of which the registry
  contract test asserts the Dart table against the Python-generated
  `capabilities.json` — this is what makes the C4 "enforced consistency across
  sites" claim true in both languages rather than only in Python.
- **2026-07-30 (same day, handset dictation)** — mechanism 5 gains its
  second implementation: **dual-recognizer open dictation on the phone**, no
  server and no extra model. The trigger word swaps the grammar recognizer for
  an open one over the same loaded 40 MB model, captures one utterance, and
  swaps back; a lead-in discards the spoken acknowledgement so the device's own
  TTS is not transcribed as the question, and every exit path restores command
  recognition. Claim-relevant because it removes the last dependency in the
  dialogue layer: free speech now reaches the router with the tether switched
  off, which is what lets §4.7's "fully offline" framing hold on the device the
  user actually carries rather than only on the laptop. Reduction to practice:
  `lib/voice_listener.dart`, `triggerWords` in `lib/logic/voice_commands.dart`
  (parsed LAST, mirroring `voice.py`), **133 Dart tests**.
- **2026-07-30 (measurement correction — read before filing or posting)** —
  every server-side latency figure previously recorded in this disclosure was
  measured with a **CPU-only PyTorch build on a machine whose CUDA GPU was
  never used**. `venv/` held `torch 2.8.0+cpu`, so `torch.cuda.is_available()`
  was `False`; a default `pip install torch` yields a CPU wheel and no log
  reports the idle GPU. Corrected on an RTX 3050 Laptop GPU (4 GB) via a
  separate `venv-gpu/` (torch 2.6.0+cu124), both arms run inside that one env
  so the comparison isolates CUDA rather than a torch version change:
  **21.2 ms/frame for both models at imgsz 640** (yolov8s 11.3 + custom 9.9),
  against 256.5 ms for the identical code path on CPU — a 12x difference, and
  ~35x against the 750 ms previously recorded. Median of 12 frames from
  `eval_a.mp4`, warmup excluded, `cuda.synchronize()` before each stop.
  Claim-relevant consequences: (1) the `--imgsz 480` reduced-resolution mode is
  **retired** — 2 ms saved on GPU for an accuracy cost — and half precision is
  likewise not adopted (0.4 ms), because at this model size inference is
  kernel-launch-bound, not compute-bound; (2) the §8 open question "a latency
  claim needs on-device measurement" is now answered for the tether laptop, but
  the bottleneck has **moved to the transport path** — YUV420→BGR
  reconstruction, rotation, and JSON now dominate, so any future latency claim
  should be stated per-stage rather than as one round-trip number; (3) the
  remote-primary architecture is unaffected in substance, since the phone's
  ~2.5 s on-device figure is independent of the laptop's torch build — only its
  justification numbers change; (4) ~3 GB VRAM remains free alongside both
  detectors, which is what makes a local tier-1 router model practical on
  commodity hardware and supports the "fully offline" framing of §4.7.
  **Methodological note worth keeping in the paper:** this is a case where a
  silent environment misconfiguration, not the algorithm, set a published
  performance number — an argument for reporting per-stage timings and the
  device/build under which they were taken.

- **2026-07-31** — **first hardware walk of the agent build, and the two
  changes it forced.** The dictation path (trigger word → open recognizer →
  router) ran on the handset for the first time: 10 `/agent` round trips in a
  three-minute walk with no loss of speech recognition, which closes the "the
  recognizer swap cannot be unit-tested" open item in §8 for the on-device
  path. Detection was healthy (464 of 612 frames carried detections) and the
  GPU server sustained ~305 ms/frame end-to-end at 720x480.
  Two design changes came directly out of the walk, both now in Python and Dart
  with mirrored tests (**219 Python / 157 Dart**):
  1. **Attention budget (new §4.8).** The user's report — "it keeps saying all
     the objects, it's too much of a cluster" — is the predicted failure of an
     over-full continuous channel. Walk warnings now fire only at *close* or
     nearer, and the removed information is available on demand through a new
     deterministic **directional query** ("is there anything in front of me")
     that answers from the same ordinal core. Push is now hazard-only; pull
     carries inventory. This is the thesis in its cleanest form and should
     probably lead the paper's motivation section rather than sit as a feature.
  2. **The authority boundary narrowed (§4.7 point 7).** At the user's
     instruction the local model may now author a *conversational reply* and
     nothing else, so the claim becomes "no **guidance** token originates in
     the model" — enforced by a separate reply channel the executor cannot
     route through a capability, with grounding, length capping and a flag that
     restores the absolute rule for the ablation. This is a genuine weakening
     of the strongest version of the claim and the paper must say so plainly;
     the compensating argument is that the split is structural rather than
     prompt-based, and that the safety-critical surface is unchanged.
  Tier 1 is now real rather than projected: `llama3.2:3b` under Ollama, on the
  laptop already used for detection, routing paraphrases at ~1.0-1.6 s and
  answering chat at ~2 s, with ~3 GB VRAM free alongside both detectors. Two
  hardware-observed model failures are pinned as regression tests (see §4.7.7).
  Also: the handset UI dropped its entire control row in favour of gesture +
  voice with a swipe-up reference page, and the app now greets the user by name
  at launch — the greeting doubles as the "it started" signal for a user with
  no splash screen, which is a small but real accessibility point worth a line
  in the paper's system description.
- **2026-08-01 (paper completed to submission quality; NO new mechanism)** —
  this entry records evidence and disclosure hygiene, not invention. The paper
  in `paper/` was taken from draft to a state intended for submission, which
  matters here for one reason: **it is the disclosure**, and §8a's warning
  applies to everything now in it.
  1. **All four evaluation configurations re-run** against the current harness
     (set sha256 `e4eeca83070e2d66`, `llama3.2:3b`). The previously committed
     run reports were unusable as evidence: they predated the fix that stops a
     conversational reply being scored as an authority-boundary leak, so they
     carried literal "AUTHORITY BOUNDARY LEAK — investigate before publishing"
     blocks describing designed behaviour, and their latency figures did not
     reproduce. **The re-run reports `boundary leaks 0` for all three routed
     configurations** — this is the reduction to practice for §4.7's central
     claim and it is now backed by artifacts that say so.
  2. **One claim withdrawn.** The draft asserted that two-tier's tier-1 median
     latency was well below LLM-only's, with an explanation. The re-run gives
     1188 vs 1172 ms — no gap. The claim and its explanation are deleted. The
     surviving and correct form of the C3 argument is that per-call cost is
     identical and tiering wins by **not making the call** for 30 % of traffic.
     Do not cite the withdrawn figure in a filing.
  3. `llm_only` overall accuracy 45.5 % → **45.0 %** (paraphrase 50.0 % →
     48.6 %). `keyword` and `two_tier` unchanged in every accuracy and
     over-trigger cell. Free-text fabrication reproduced exactly at
     **85/200 (42.5 %)**, including the "walking in front of you, my cane
     tapping on the ground" sample, which is the single most useful piece of
     evidence in the file for why §4.7 exists.
  4. **Clip-evaluation numbers now carry denominators.** "100 % of reviewed
     keyframes" became **31/31 announcements correct on direction, 0/31
     phantom, 6/31 wrong class name with warning behaviour still correct**. A
     percentage without an n is not evidence; these are small numbers and are
     labelled as an author-reviewed sanity check on the deterministic core.
  5. **Prior-art list extended into the abstention literature**, which §7 did
     not previously cover and which a searcher would hit first: classification
     with a reject option (Chow 1970), selective prediction / SelectiveNet,
     learning to defer, OOD-confidence baselines and calibration; plus the
     containment line — tool use (Toolformer, ReAct, ToolLLM) and constrained
     decoding (PICARD, guided generation). The §4.7 novelty argument must be
     framed against these: the mechanism is not novel, the **application to a
     channel whose consumer cannot verify the output** is what is argued.
     Also add the reliance literature (Parasuraman & Riley; Wickens & Dixon's
     reliability crossover) — it supports §4.8's "an unheeded warning has
     negative value" as an established result rather than an assertion.
  6. Paper artifacts: `paper/references.bib` (53 entries, all cited),
     `paper/main.tex` rebuilt as a self-contained ACM `acmart` submission with
     corrected figures, and a new ethics/positionality/availability section.
     ⚠ **The bibliography was assembled from memory and is not
     machine-verified**; it carries no DOIs deliberately. Verify every entry
     before a preprint goes up, for the obvious reason that this is a paper
     about not stating what you cannot check.
  Reduction to practice unchanged this session: **221 Python / 159 Dart** tests.
- **2026-08-01 (night) — the spoken-input evaluation. THE STRONGEST EVIDENCE IN
  THIS FILE FOR THE §9 THESIS, and it arrived as a negative result.**
  Two volunteer speakers read the 60-utterance sheet; transcripts came from the
  handset's own open-dictation configuration (Vosk, grammar removed). Matched
  comparison over the same 59 records, written text vs 107 real transcripts:

  | | keyword text | keyword spoken | two-tier text | two-tier spoken |
  |---|---|---|---|---|
  | overall accuracy | 37.3 | 34.6 | 44.1 | 35.5 |
  | out-of-scope abstention | 91.7 | 91.3 | 41.7 | 30.4 |
  | over-trigger | 8.3 | 8.7 | 58.3 | 69.6 |

  1. **Claim-relevant finding.** The deterministic tier is nearly ASR-invariant
     (over-trigger 8.3 -> 8.7) while the model tier's abstention *degrades under
     degraded input* (41.7 -> 30.4 abstention, 58.3 -> 69.6 over-trigger). A
     garbled utterance is not a signal to a language model that it should
     decline; it is additional room for interpretation. **Abstention by
     construction survives noise; abstention by judgement does not.** That is
     the §9 thesis measured rather than argued, and it is the best available
     support for why §4.1-4.3 and §4.8 gate on layer-specific *structural*
     criteria instead of on a confidence score.
  2. **Claim-limiting finding, and it must be disclosed.** The agent layer's
     accuracy advantage over the keyword baseline falls from **+6.8 points on
     written text to +0.9 points on the same utterances spoken**. §4.7's value
     proposition is paraphrase coverage, and paraphrases are long with open
     vocabulary — exactly what a 40 MB recogniser transcribes worst. Any
     claim framed around routing accuracy is weak on real speech. The claim
     that survives is the *containment* one (boundary leaks 0 in every run,
     including both spoken runs), not the coverage one. Do not draft a claim
     that rests on the agent improving task success from speech input without
     this data in front of the drafter.
  3. **Method, because it can bias the number.** Silence-splitting was tried and
     rejected: it cannot be validated by segment count, since one merge plus one
     over-split cancels out while shifting every label between them. The
     condition uses forced alignment of the recognised word stream to the known
     script (`asr_collect.py align`), and DROPS any utterance where under a
     third of the script words aligned rather than pairing it with an untrusted
     transcript — the §4.3 absence-vs-negative rule applied to our own
     measurement. That gate removes the worst-recognised utterances, so the
     reported degradation is a **floor**, not an estimate. Stated in the paper.
  4. Reduction to practice: `asr_collect.py align`, `tools/aac_to_wav.ps1`
     (WinRT Media Foundation decode, nothing downloaded), `eval_agent.py
     --asr-subset` for the matched baseline. Eval set hash moves from
     `e4eeca83070e2d66` to `f9e775b6a65279a4`; only the `asr` arrays differ.
  5. Paper also now ships as a Word/PDF build (`paper/build_docx.py`, 6 pages)
     in addition to `main.tex`. ⚠ Both are disclosures — §8a applies to
     whichever goes out first, and the .docx is the one most likely to be
     emailed casually.
