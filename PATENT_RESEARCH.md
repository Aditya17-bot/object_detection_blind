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

### 4.9 Embedding-distance naming head with a derived abstention criterion *(strong — the perception-layer instance of the §9 thesis, and it comes with a falsified predecessor)*
- **What:** the detector keeps the job it is good at — *where* — and the spoken
  **word** is re-decided by nearest-neighbour matching an embedding of the
  detected crop against a small set of user-labelled example crops of that
  user's own objects. The system speaks the matched label only when the nearest
  labelled example is both close enough and **clearly closer than the best
  competing label**; otherwise it abstains and leaves the detector's word alone.
  No training run: adding a class means adding crops and rebuilding an index in
  seconds. The embedding comes from the already-loaded detector backbone
  (`YOLO.embed()`), so there is no second model and no extra download.
- **The problem it solves:** COCO has 80 words and none of them is *wardrobe*,
  *dustbin* or *window*. The detector cannot decline to answer — it makes a
  forced choice over the vocabulary it has and returns the nearest available
  word. This is not a weak-model problem: a 2026-08-02 benchmark showed YOLO11
  still calling the dustbin "toilet" at 0.93, and the repo's own 6.2 MB custom
  nano model beating a 21.5 MB yolov8s on exactly the objects yolov8s misnames.
  It is a **vocabulary** problem, and no amount of model capacity fixes it.
- **The falsified predecessor — this is the valuable part.** The prior
  mechanism was a **confidence gate**: below `NAME_CONFIDENCE` speak the generic
  word "obstacle". Its threshold rested on a probe recording misnames at
  0.65–0.75 and correct names at ≥0.85. Re-measured on the same clips:

  | | claimed | measured 2026-08-02 |
  |---|---|---|
  | dustbin → "toilet" | 0.65–0.72 | **peak 0.94**, mean 0.80 |
  | wardrobe → "refrigerator" | 0.72–0.75 | **peak 0.82** |
  | correct "chair" | ≥0.85 | 0.92 |

  The bands overlap, so **no threshold exists**, and "Toilet ahead" was being
  spoken in the logs. Detection confidence answers *how sure am I this box holds
  one of my 80 classes* — a question asked over a vocabulary with no word for a
  wardrobe. A forced choice can be made with total certainty and still be wrong.
  **The quantity being thresholded was never the quantity of interest.**
- **Why that matters for the §9 thesis:** this is a clean, empirically
  demonstrated instance of the failure C1 predicts — an abstention criterion
  *borrowed from a neighbouring layer* rather than *derived from the failure
  mode of the layer it guards*. The replacement is derived: embedding distance
  to a labelled exemplar is a direct measure of "have I actually seen this thing
  before, and is it unambiguously this one thing", which is exactly the question
  naming poses. And unlike confidence, it is **separable**: a leave-one-out
  sweep over labelled crops (`build_name_index.py`) finds operating points with
  **zero wrong names retained**, printed as a grid so the claim is checkable
  rather than asserted. If the zero-error column were ever empty, the report
  says so in those words.
- **Second derived criterion — provenance beats similarity.** Detections from
  the dedicated door/dustbin model are marked trusted and are **never renamed**:
  those classes exist *because* COCO lacked a word for them, so there is no
  forced-choice error to correct. Discovered empirically — without the rule the
  namer relabelled a real door as "wardrobe" three times on `eval_a`, both being
  large flat rectangles. The general principle: a detector that owns a word
  outranks a similarity match on that word.
- **Third mechanism — hysteresis as a safety property, not a polish item.**
  `GuidanceEngine` requires the same name on two consecutive frames before it
  speaks, so an unstable namer does not produce *wrong* announcements, it
  produces **silence** — and an app that has gone quiet in front of an obstacle
  looks identical to an app that is working. The namer therefore carries its own
  IoU tracker and commits a name change only after it repeats. Tracks are keyed
  by the detector's original word as well as by overlap: two models detecting
  the same object give near-identical boxes (COCO's "refrigerator" and the
  custom model's "door" on one wardrobe), and greedy IoU matching alone let one
  steal the other's track, silently swallowing every rename on `eval_a` until
  keys were added.
- **Fourth — vocabulary containment.** A name outside the app's known class set
  fails *silently* downstream: person-sized proximity thresholds, no distance
  estimate, and never walk-warned. So the namer refuses any label outside the
  vocabulary at the point of decision, and the build script refuses to build an
  index containing one without an explicit override. Same containment shape as
  §4.7's tool-argument validation, applied to perception.
- **Non-obviousness angle:** the combination is (a) using the detector's *own*
  backbone as an embedder so personalisation costs no model and no training,
  (b) taking the abstention criterion from *retrieval distance* rather than
  classifier confidence, with a published falsification of the latter in the
  same system, and (c) provenance-based trust between a general and a dedicated
  detector. Personalised object recognition for blind users is prior art
  (teachable object recognisers); what is claimed here is the abstention
  criterion and its derivation, in a system where being wrong is spoken aloud
  as fact.
- **Evidence:** `name_index.py` (+ 33 unit tests in `test_name_index.py`),
  `harvest_crops.py` (+ `test_harvest_crops.py`), `build_name_index.py`,
  `verify_namer.py`. Built and calibrated on **280 crops the user labelled into
  17 classes** (2026-08-02):
  - leave-one-out at `min_margin` 0.15 names 49/280 with **49/49 correct, zero
    wrong names** (10 errors at the untuned 0.05) — the separable operating
    point the retracted confidence gate could not provide at any threshold;
  - the discriminating quantity is the **margin over the runner-up label**, not
    the distance: `min_sim` is inert across 0.50–0.65 on this data;
  - on the recorded clips at stride 1, **105 renames in 8 patterns, all
    eye-checked, 104 correct**, including five errors `EVALUATION.md` had
    recorded as unfixable COCO-vocabulary limits, and a hallucinated *person*
    (a blanket on a chair) corrected to *chair*;
  - **no renames at all on the clips containing none of the labelled objects** —
    the stairs-class bar (0.072 recall with 0.68–0.91 confidence false
    positives) that this project has failed once before and pulled a feature
    for.
- **Status:** wired into `infer_server.py` and `webapp.py`; the production index
  is built, tuned and committed (`name_index.npz`). Remaining: a walk with the
  phone to confirm names are stable rather than flickering.

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

### 4.10 Focus arbitration over a single speech channel, with a solicitation-typed abstention rule *(strong — the output-scheduling instance of the §9 thesis)*
- **What:** every spoken message carries a *class* (safety / response to an
  explicit request / state confirmation / routine guidance) and a *task tag*,
  and a task the user asked for **holds the channel** until it completes. While
  a task holds focus, routine guidance is DROPPED rather than queued,
  informational read-outs from any source wait, the user's own steering
  commands still pass, and safety speech is never gated. Holds are open-ended
  for tasks that run until an event (find) and timed for tasks that end when
  they have spoken, and **every hold expires**, so a missed release degrades to
  chatter rather than to silence.
- **The non-obvious half — `solicited`.** Each request is typed by *how the
  system came to believe the user wanted it*: deterministic parse or deliberate
  dictation (solicited) versus a language model's guess at audio the parser
  could not resolve (unsolicited). An unsolicited route may RUN a capability but
  may **never speak an abstention**, and may never interrupt a task in progress.
  The asymmetry is the point: "I can't do that" is a correct answer to a
  question and an intrusion in reply to a door closing, and the *same string*
  is one or the other depending only on provenance. Gating the COMMAND and not
  merely its speech matters too — an OCR read pauses the camera stream and a
  find changes mode, so a spurious trigger costs more than a spurious sentence.
- **The input floor.** A grammar-constrained recognizer cannot report "I did not
  understand": it returns its best match over the trained phrases for *any*
  audio. So the absence of a parse is NOT evidence of a paraphrase — it is
  weakly the opposite. A cheap lexical floor (≥2 words, ≥1 capability keyword or
  object name) must be cleared before a language model is consulted at all, plus
  an echo gate that ignores the recognizer while the device's own speaker is
  audible. Without those, the system converses with itself.
- **Why it is the §9 thesis:** *say less, never mislead* has so far been argued
  per layer (perception §4.9, planning §4.8, transport F2, dialogue §4.7). This
  is the layer that decides **whose turn it is**, and it shows the thesis has a
  scheduling form: an over-full channel is not merely annoying, it is less safe,
  because the one message that mattered arrives indistinguishable from four that
  did not.
- **Evidence / reduction to practice:** `speech_policy.py` +
  `lib/logic/speech_policy.dart` (hand-mirrored, 22 + 23 tests including a
  table-parity assertion). Prompted by a 2026-08-02 field walk in which the
  handset made 26 router calls in 2.5 minutes on unsolicited recognizer output.
  Both reported symptoms were then **reproduced deterministically** against the
  running server: glue-word soup `'the is my on'` caused the model to attempt
  `check(left)` — the unrequested directional read-out the user heard mid-find —
  and, once validation rejected it, produced the spoken abstention the user
  heard at random. A negative result worth keeping with the claim: the same
  system's measured 55% out-of-scope over-trigger rate (paper §7) is exactly
  what predicts this failure, so the arbitration layer is not defensive
  programming but a consequence of a published measurement.
- **Prior art to distinguish:** audio focus / ducking on mobile platforms
  arbitrates between *applications* by stream type; screen-reader speech queues
  arbitrate by recency and interruption class. Neither types a request by its
  *provenance*, and neither drops rather than queues on the grounds that late
  guidance is unsafe.

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

- **2026-08-02 — §4.9 added: embedding-distance naming head, and a mechanism
  RETRACTED.** Two things happened and the second is the more important one.
  1. **The confidence gate is falsified.** `decision.NAME_CONFIDENCE = 0.8`
     (speak the generic word "obstacle" below it) rested on a probe recorded in
     `EVALUATION.md` claiming misnames sit at 0.65-0.75 and correct names at
     >=0.85. Re-measured on the same clips: dustbin->"toilet" peaks at **0.94**,
     wardrobe->"refrigerator" at **0.82**, correct "chair" at 0.92. The bands
     overlap; no threshold exists; "Toilet ahead" is in the announcement logs.
     `EVALUATION.md` has been corrected in place rather than quietly amended,
     and the paper now reports it as a **negative result** (PAPER.md §7,
     main.tex §6, build_docx.py — the prose is duplicated across all three).
     A disclosure that claimed this gate worked would have been claiming
     something the system's own logs contradict.
  2. **Replacement: §4.9**, an embedding-distance naming head whose abstention
     criterion is derived from the naming layer's own failure mode rather than
     borrowed from the detector's. Keep YOLO for *where*, re-decide *what* by
     nearest-neighbour over user-labelled crops of the user's own objects, and
     abstain unless the match is unambiguous. `YOLO.embed()` on the loaded
     backbone, so no second model and no download. Sub-mechanisms worth claiming
     alongside: provenance trust (a dedicated detector that owns a word outranks
     a similarity match on it), name hysteresis keyed by detector word as well
     as box overlap, and vocabulary containment at the decision point.
  3. Reduction to practice: `name_index.py`, `harvest_crops.py`,
     `build_name_index.py`, `verify_namer.py`, `test_name_index.py` (30 tests).
     Test counts now **262 Python / 159 Dart**. On the recorded clips with a
     preliminary 4-label index: dustbin and wardrobe renamed correctly, and
     **zero renames on the clips containing neither** — the false-positive bar
     the stairs class failed.
  4. ~~⚠ The production index awaits the user's labelling pass~~ — **done the
     same day, see the next entry.** The *retraction* in item 1 never depended
     on it and stands on its own.
  5. **`laundry basket` added as a namer-only class** (same day, during
     labelling — user found crops of one and asked where to put them; 0.85 m
     tall, 0.3 m wide). Worth recording because it is the mechanism's intended
     workflow rather than a code change: the vocabulary is extended by the
     *user's own environment* at labelling time, and the containment rule turns
     that into a hard gate — `build_name_index.py` refuses to build on a label
     outside `TARGET_CLASSES`, so a new word cannot reach the speech layer
     without also acquiring an area threshold and a real-world height. The
     alternative outcomes were both worse and both silent: COCO calls one
     "handbag", which is not a target class and is therefore **dropped
     entirely** (the app is blind to a waist-high floor obstacle), or
     "suitcase", which warns correctly under a wrong word.

- **2026-08-02 (later) — §4.9 reduced to practice: the index is built and the
  abstention criterion is measured.** The user labelled all 280 crops into 17
  classes and the numbers are no longer preliminary.
  1. **A clean operating point exists.** Leave-one-out over the built index at
     `min_margin` 0.15 names 49/280 crops with **49/49 correct — zero wrong
     names** (10 errors at the untuned 0.05). This is the claim §4.9 rests on
     and the one the retracted confidence gate could not support at ANY
     threshold, because there the correct and incorrect bands overlapped.
     Report: `test_output/name_index_report.md`.
  2. **The discriminating quantity is the MARGIN, not the distance.**
     `min_sim` is inert anywhere in 0.50-0.65 on this data; every clean row is
     produced by the runner-up gap alone. Worth stating precisely in any claim
     language: the signal is *relative* separation between competing labels,
     not absolute proximity to a stored example. An absolute-distance
     formulation would read on far more prior art and would not, on this
     evidence, actually work.
  3. **Field evidence, 105 renames across 8 clips, every pattern eye-checked:
     104 correct, 1 arguable, and 0 renames on the clips containing none of the
     labelled objects.** Five of the corrected names are errors `EVALUATION.md`
     had recorded as unfixable vocabulary limits. One is worth singling out:
     `person -> chair` (4x) on a blanket draped over a chair. The detector did
     not merely pick the wrong word from its 80 — it announced a **person**
     where there was none, which for a blind user is a different and worse
     class of error than "toilet" for a dustbin. The naming head removed it
     without any change to the detector.
  4. **A measurement bug that hid the result, worth recording as a hazard of
     the method rather than an incident.** `leave_one_out` scored a predicted
     `_ignore` as a wrong name, when at runtime matching `_ignore` is an
     ABSTENTION. The report therefore charged the system for its safest
     possible outcome and concluded in print that "no setting reaches zero
     errors" — the exact opposite of the truth. The general lesson for any
     abstaining component: **the evaluation harness must mirror the runtime
     decision function exactly**, or it will misprice abstention and select the
     wrong operating point. Now enforced by a test that asserts
     decision-for-decision equality between the two across three settings.
  5. Data-integrity note with a safety edge: crop filenames were unique only
     within a guess-folder, and the labelling workflow flattens folders, so
     Windows Explorer silently replaced 3 crops on same-name moves — one a
     dustbin, a class with five examples. Recovered from the manifest (which
     stores clip + frame + box precisely so a crop is reproducible) and the
     naming scheme made globally unique. A user-labelling step is part of the
     mechanism, so its failure modes are part of the mechanism.

- **2026-08-02 (night) — §4.10 added: focus arbitration, and a failure the
  project's own published measurement predicted.** The first field walk with the
  naming index produced three complaints — an abstention spoken at random, an
  unrequested directional read-out landing mid-find, and "it's still a cluster".
  1. **Root cause, reproduced rather than argued.** The handset was posting
     every unparseable recognizer result to the router: 26 calls in 2.5 minutes.
     A grammar-constrained recognizer cannot say "I did not understand", so
     ambient sound arrives as trained-word soup. Replaying that soup at the
     running server reproduces both symptoms exactly: the model attempts
     `check(left)`, and the rejection surfaces as the spoken abstention. The
     paper already reports this model at **55% out-of-scope over-trigger**;
     feeding it unsolicited noise makes over-triggering the dominant behaviour.
     The measurement predicted the field failure — worth saying in the paper,
     because it is the strongest argument available that the eval measures
     something real.
  2. **§4.10** is the mechanism: message classes, task focus, drop-not-queue for
     routine guidance, and the `solicited` type that makes the SAME string a
     correct answer or an intrusion depending only on how the system came to
     believe it was wanted.
  3. Note for claim drafting: the abstention rule in §4.7 said *the model may
     never author a spoken token*; §4.10 refines the boundary again, this time
     on the output side — a validated abstention is a legitimate spoken token
     **only in reply to a request the user is known to have made**. Provenance,
     not content, decides.

- **2026-08-02 (night, second walk) — §4.11: ARGUMENT GROUNDING, and the
  sharpest single piece of evidence this project has produced.** The first fix
  added `/agent` utterance logging; the second walk immediately paid for it.
  The log shows `llama3.2:3b`, given the single word **"door"**, emitting
  `check(left)` — and the same for "the cup", "bag", "the person", "cup
  phones". The user heard *"Nothing on your left"* repeatedly having said no
  such thing.
  1. **Why every existing guard missed it.** `check` is a real capability and
     `left` is a valid member of the direction enum, so the action is
     *well formed*. Tool-name validation, enum validation and vocabulary
     containment all pass. The defect is not in the action's SHAPE but in its
     PROVENANCE: the argument is a fact about the user's request that
     originated in the model.
  2. **The rule:** *the model may choose a capability; it may not invent the
     capability's argument.* An argument must be grounded in the utterance.
  3. **The non-obvious part is where the rule does NOT apply.** Grounding is
     enforced for closed-set arguments whose members are also the words people
     say (directions, on/off) and deliberately NOT for class names, because
     class names are exactly where paraphrase lives — "the exit" means the
     door, "something to drink" means the bottle. Grounding those would delete
     the paraphrase capability the whole tier exists to provide (measured 0% ->
     47%). A naive "all arguments must appear verbatim" rule would have looked
     more rigorous and would have destroyed the feature. Required-vs-optional
     is handled asymmetrically too: an invented REQUIRED argument voids the
     action, an invented OPTIONAL one is simply dropped, so an unrequested
     "sonar off" degrades to a toggle rather than a silent state change.
  4. **Claim relationship.** §4.7 drew the boundary at *perceptual content*
     (the model may not author facts about the scene). §4.10 drew it at
     *provenance of the request* (an abstention is speech only if someone
     asked). §4.11 draws it at *provenance of the argument*. Same thesis, three
     surfaces — and each was found by a field failure, not by design review,
     which is itself worth saying in the paper.
  5. ⚠ **Consequence for the reported evaluation:** grounding changes what the
     router accepts, so the frozen T3-T6 tables no longer describe the shipped
     system. Over-trigger should improve — grounding rejects precisely the
     fabricated-argument class — but that must be MEASURED and recorded as a
     post-freeze amendment, not asserted.

### 2026-09-05 — Field-walk defect pass: a falsified gate retired, a wrong bearing corrected, and a transport that was breaking perception

Five defects found and fixed in one session, all from a single user report
("still not production ready"). Three of them are worth the disclosure because
they are each a case of a mechanism defeating the very thesis it was built to
serve.

1. **The naming head's verdict was being discarded by the falsified gate it
   replaced.** §4.9 established that embedding margin is a calibrated
   abstention signal and that detector confidence is NOT one (measured: a
   dustbin misnamed "toilet" peaks at 0.94, a correct "chair" at 0.92 —
   overlapping bands, so no threshold separates them). But `Namer.apply` never
   marked a committed rename as trusted, so `_spoken_name` re-gated it on the
   very confidence number §4.9 falsified. A wardrobe correctly identified at
   YOLO-confidence 0.72 was announced as the generic **"Obstacle"**. The system
   did the hard part and then threw the answer away. Fixed end to end —
   `trusted_name` now travels namer -> server JSON -> `Detection` ->
   `ObjectInfo` -> spoken word — and pinned by tests in both languages.
   *Lesson for the disclosure: a calibrated signal is only worth what the
   downstream consumer lets it be worth. The claim should describe the
   provenance flag, not just the classifier.*

2. **§4.6's clock bearings were about double the true angle, in the DEFAULT
   configuration.** The frame was mapped onto 10-11-12-1-2 — four hours, 120
   degrees — across a camera that sees ~65. The right frame edge sits at about
   +32 deg and was announced as "2 o'clock" (+60). Clock mode has been the
   default since 2026-07-14, so the users most able to *act* on a bearing (O&M
   trained) were the ones being systematically over-rotated; untrained users
   ignored the number and were unaffected. The mapping is now DERIVED from an
   explicit `CAMERA_FOV_DEG`, which at 65 deg yields 11-12-1 and nothing wider.
   ⚠ This **weakens §4.6 further**: at this field of view clock bearings cannot
   be finer than left/center/right — three hours, three zones. The feature's
   remaining value is the VOCABULARY a trained traveller already has, not
   angular resolution, and the earlier claim of extra resolution was part of
   the error. Keep §4.6 rated minor; do not claim precision.

3. **The transport layer was corrupting the perception layer.** The app posted
   RAW YUV420 planes: 506 KB/frame, measured at 320-510 ms to upload on the
   user's hotspot against ~171 ms for BOTH models plus the naming head, under a
   1.2 s frame timeout. Frames were being lost to the network, and a lost frame
   is not merely a slower app — it breaks `GuidanceEngine`'s two-frame
   persistence streak. The user-visible symptoms were "obstacles are weirdly
   said" and "it keeps no memory of the door": erratic announcements and an
   object that never accumulated enough sightings to enter the object memory
   of §4.3. Both looked like decision-layer bugs and were neither. Fixed with
   hardware JPEG encoding on the handset (measured 506 KB -> 26 KB, a 19x cut),
   with the raw path retained as an automatic fallback.
   *Lesson: §4.3 and §4.8 both assume a frame rate the transport was not
   delivering. Any claim that depends on temporal persistence should state the
   frame-delivery assumption explicitly.*

4. **The grammar path had no noise floor, while the free-speech path had
   three.** §4.10 added a plausibility floor, a rate limit and a solicitation
   type to *unmatched* speech before the router is consulted. A MATCHED command
   went straight to execution with none of them — yet the recognizer is
   grammar-constrained and therefore returns its best match for **any** audio,
   including a door closing. Worse, the grammar's explicit `[unk]` token — the
   recognizer's own statement that it could not place a sound — was being
   *stripped and discarded*, so "[unk] [unk] clock mode" arrived
   indistinguishable from a deliberate utterance. That is the user's "randomly
   says clock mode". The markers are now counted and weighed
   (`kMaxUnknownRatio` 0.5).
   *This is the same shape as items 1 and 3: a system possessed the evidence it
   needed and threw it away before the decision point. Three independent
   instances in one codebase suggests it is worth stating as a design
   principle in its own right — **preserve the uncertainty signal all the way
   to the actor** — rather than as three bug fixes.*

5. **Focus was released before the user had heard the answer** (the OCR case).
   §4.10's `extend()` fixed exactly this for find announcements; `_readText`
   bypassed `_say` entirely and so never held the channel at all, then released
   a hold it had not taken. A page of OCR text outlived the default 6 s focus
   and routine walk chatter cut into it. Fixed by routing the read-out through
   the same arbitration path as everything else. *Evidence that §4.10's
   mechanism is right and its enforcement was incomplete: an arbitration layer
   is only sound if every speech path is obliged to go through it.*

**Not fixed, and recorded honestly:** on the user's own room the naming head
made **0 renames over 424 sampled frames** — it abstained everywhere, almost
always as `ambiguous` (high similarity 0.75-0.90, but margins of 0.005-0.11
against `MIN_MARGIN` 0.15). The index was labelled from eight older clips and
this is a new room, so the crops are out of distribution. This is the DESIGNED
behaviour and the stairs precedent working as intended — it declined to guess
rather than inventing a confident wrong word — but it means §4.9's benefit is
**room-specific until labelled**, which is a real deployment limitation and
should be stated in any filing or paper rather than discovered by a reviewer.

### 2026-09-05 (later) — Asymmetric evidence, and two guards that were deaf in the direction that mattered

The second field walk turned up three faults that share one shape: a threshold
tuned for one cost was applied to a decision with the opposite cost.

1. **Find mode demanded symmetric evidence for asymmetric claims.** Announcing
   a target and denying one were both gated on `persistence = 2` consecutive
   frames. Those two claims do not cost the same. The user ASKED for the object,
   so a false "it is on your right" costs one wasted look; a false "not visible"
   about something in frame tells a blind user the system is broken, and they
   cannot check the screen to find out which happened. Measured on the user's
   room at the phone's real 2 FPS, detection runs were `[1,1,1,1,2,2]` frames:
   four of six sightings were never announced, and the engine said "not visible"
   and "still looking" with the person on screen. First correct answer: 19.5 s.
   Now presence needs ONE frame, absence needs 2.5 SECONDS of continuous
   non-detection, and streaks DECAY (0.5/frame) rather than resetting — so
   intermittent detection accumulates while a one-frame ghost still never
   reaches the walk threshold. Result: 12/12 classes answered on the first
   frame, zero false absences.
   *This sharpens §4.3 and the §9 thesis: "say less, never mislead" is not a
   single threshold. The evidence required should scale with the cost of the
   particular claim, and for an assistive device the costs of the two directions
   are rarely equal. Worth stating as a claim limitation: a persistence
   parameter expressed in FRAMES silently changes meaning with frame rate, and
   this system's frame rate is set by a network.*

2. **A noise floor that made the device deaf to its shortest commands.** The
   morning's fix rejected any recognizer result at least half composed of
   `[unk]`. "read", "walk", "stop" and "repeat" are single words, so one stray
   token put them exactly at the threshold. The floor is now set per command by
   the cost of error: settings toggles, whose spurious activation silently
   changes behaviour a blind user cannot observe, demand a clean recognition;
   actions, whose result the user hears at once and can simply repeat, are
   lenient. *Same principle as (1), applied to input rather than output.*

3. **Echo suppression that was purely temporal.** Blocking the microphone for
   the duration of every utterance plus a tail meant the device could not be
   interrupted while speaking — in walk mode, most of the time. Replaced with a
   content test: within the echo window, reject only text whose every word we
   just said. Guidance never contains a bare command word, so "read" survives
   while our own "Door at 11 o'clock" coming back does not. *Relevant to §4.10:
   an arbitration layer that cannot be interrupted is not merely inconvenient,
   it removes the user's authority over the device.*

**A prior claim is now settled by evidence rather than argument.** §4.7's
unsolicited routing path was retained on the explicit condition that the next
field log decide it. That log: two unsolicited router calls, both noise the
grammar had force-matched, both abstaining, both 6.8-8.0 s. It is disabled by
default. The trigger-word path — where the user deliberately opens a dictation
window — is untouched, which is the correct place for the capability to live and
strengthens rather than weakens the §4.7 claim.

**Measured constraint worth recording for any latency claim:** the router model
and the detectors share one 4 GB GPU. Tier 1 measures 485-1140 ms with the GPU
idle and **6766-8016 ms while frames stream**; detector compute rises from
~171 ms to 266-468 ms over the same transition. Any latency figure for this
architecture must state whether the dialogue and perception layers were
contending for the same accelerator.

### 2026-09-05 (night) — An arbitration layer that overrode the user, and a dedup rule that had to reject the obvious metric

Two entries worth the disclosure, both refinements of existing claims rather
than new ones.

1. **§4.10's focus arbitration was blocking the principal.** The mechanism was
   built to stop routine guidance and the dialogue layer's guesses from treading
   on a task the user asked for. As implemented it refused any non-steering
   capability while another held focus, including one the user had just spoken
   aloud, and the field log records it doing so: `dropped "describe"
   (focus=photo, solicited=true)`. The `solicited` flag already carried exactly
   the distinction needed and was consulted only for the steering subset. Fixed
   so that provenance, not category, decides: a guess is gated, an utterance is
   never gated. *This is the third time the same shape has appeared (see the
   2026-09-05 morning entry): a system holding the evidence it needed and not
   consulting it at the decision point. It is worth stating in the paper as a
   design failure mode of layered abstention — each layer's guard must be
   indexed by provenance, or it will eventually silence the very user it
   arbitrates for.*

2. **Cross-detector merging, and why the intuitive overlap metric is unsafe.**
   Two detectors over one frame with no shared NMS returned one object under two
   names. The obvious test for "a small box inside a big one" is containment
   (intersection over the smaller area), and it must be REJECTED: measured on
   real room footage, the pairs containment flags include a person standing in
   front of a bed, where the person's box is fully contained. Suppressing a
   person is a safety regression, and legitimate nesting (bottle on table,
   person in doorway) has the same signature. Mutual IoU is the correct test
   because it asserts the two boxes describe the same REGION, not merely that
   one lies within the other. The tie-break is also non-obvious: raw confidence
   is not comparable across detectors thresholded differently (0.6 vs 0.4), so
   the rule ranks by margin above each detector's own floor, with a committed
   embedding rename outranking both. *Supports §4.9: once a calibrated namer
   exists, it should win arbitration against uncalibrated ones, which is a
   different claim from simply using it to relabel.*

**Measured deployment limitation, restated with numbers.** The naming head
abstained on 100% of detections in a room it had not been labelled for, while
the same index scores 104/105 correct on the rooms it has seen. §4.9's benefit
is room-specific until labelled, and any claim about naming accuracy must say
which rooms are in the index.

### 2026-09-05 (late) — Verified generation: the model may choose words, never facts

Two capabilities added that let a language model produce user-facing prose for
the first time, under a mechanism that makes doing so compatible with the §9
thesis rather than a retreat from it.

**The mechanism.** Where §4.7 kept the model out of the speech channel and the
2026-08-03 work narrowed that to "no *guidance* token", this narrows it again
and more usefully: the model may write the SENTENCE, but every FACT in the
sentence is checked against the structured record it was given, and a reply
failing the check is discarded in favour of a deterministic template the caller
already holds. The asymmetry is the claim: the model can only improve the
phrasing, never change what is asserted, and a weak model, a timeout, an absent
server and a hallucination all produce the same output as having no model at
all. This is `argument_is_grounded` generalised from tool arguments to prose.

Instantiated twice, with different checkable invariants:

  * **Memory phrasing** — object names must be ones the object was actually
    beside; numbers must appear in the record. The vocabulary is closed, so
    this is decidable.
  * **Document summarising** — every number in the summary must appear in the
    source text. The vocabulary is NOT closed (the source is arbitrary), so
    nouns cannot be validated, and the limitation is stated in the module and
    mitigated by always offering the full text.

**Three findings that only appeared against real models, and that a reviewer
would ask about.** Each is now a regression test.

1. *The first verifier checked nouns, not relationships.* For a record whose
   "beside" list was empty and whose room context held a bed, both llama3.2:1b
   and 3b wrote "beside the bed", and the check passed it because `bed`
   appeared somewhere in the record. Fixed by withholding room context from the
   model entirely: a spoken sentence cannot reliably carry the beside/in-the-
   room distinction, so the model is never given the chance to blur it.
2. *Comparing numbers by spelling produced false rejections.* "about two hours
   ago" against a record of "about 2 hours ago" is the same fact in the form a
   spoken interface should use, and it was three of four rejections in the
   first run. Verification must normalise before comparing, or it punishes the
   correct behaviour.
3. *Length is not falsehood.* Rejecting long replies discarded a truthful
   prescription summary containing no figures at all. Verbosity is trimmed;
   only claims are rejected.

**A measured negative result worth reporting.** Model size is not monotonic
here. llama3.2:1b routes 20x faster than 3b under frame load (281 ms vs
6-8 s) and is unsafe at summarising: asked to summarise a real overdraft letter
it reported the account "has been closed" — a material fabrication containing no
number, which the figure check cannot catch by construction. The same check that
makes 3b's summaries safe is blind to 1b's characteristic error. Any claim of
the form "verification makes small models safe" must therefore be qualified:
verification bounds the class of error it can decide, and choosing that class
is a design decision about which errors matter.

**A deployment constraint for the latency claims.** The router and the
summariser cannot both be GPU-resident on a 4 GB card alongside two detectors;
two resident models thrash, taking routing from 281 ms to 5.9 s as each request
reloads what the last displaced. The summariser therefore runs CPU-only
(`num_gpu: 0`), which is affordable precisely because summarising is a
deliberate, stationary act with the camera paused. Any published latency figure
for a multi-model assistive pipeline should state the residency arrangement.

