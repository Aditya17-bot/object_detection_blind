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
  `test_door_is_not_an_obstacle_for_path`, `test_near_small_hazard_beats_far_bulk`.
- Prior recorded-clip evaluation: `EVALUATION.md` (direction accuracy, FPS,
  false/missed-announcement counts).

## 7. Prior art to search before filing (starter list)

Be My Eyes AI, Microsoft Seeing AI, Envision AI, OrCam MyEye, Microsoft
Soundscape, Lookout by Google, Sunu Band, WeWALK cane, ultrasonic ETAs;
academic: monocular object-distance estimation, free-space detection for the
blind, sonification of obstacle proximity, wearable haptic direction belts.
Patents: search classes G06V (image/video recognition), A61H 3/06 (walking aids
for the blind), G08B (signalling), H04R (stereophonic).

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
  113 Dart** tests.
