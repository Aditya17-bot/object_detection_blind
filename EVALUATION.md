# BlindAssist — Phase 5 Evaluation Report

*Date: 2026-07-11 · Model: YOLOv8s (COCO), confidence ≥ 0.6 · Dev laptop,
Windows 11, CPU inference · Pipeline: camera → YOLOv8s → position analysis
(3×3 grid + proximity) → decision logic → TTS*

## 1. What was evaluated and how

Three layers of testing, per the agreed protocol:

1. **Unit tests (no camera)** — 40 tests across `test_position.py` (13),
   `test_decision.py` (23), `test_speech.py` (4). **All pass.**
2. **Recorded-video tests** — 7 phone clips run through the reproducible
   harness (`phase3_detect.py --headless`, video-time clock so results are
   identical on every run/machine). Announcement logs in `test_output/*.log`.
3. **Keyframe review** — every announcement saves an annotated frame; each
   was checked by eye against what is actually in the picture.

Still pending for a complete Phase 5: the **live protocol test** (objects at
known positions, walking with the phone camera streaming) — needs a live
session.

## 2. Headline numbers

| Metric | Result |
|---|---|
| Unit tests | 40 / 40 pass |
| Direction (zone) accuracy | **100 %** of reviewed announcement keyframes — every "left/ahead/right, top/bottom" matched the image (consistent with the full phase-2 clip review) |
| Proximity bucket accuracy | 100 % of reviewed keyframes plausible (e.g. escalates to "very close" exactly as the wardrobe fills the frame) |
| Object-name accuracy | The main weakness — see §4. Wrong names in ~6 announcements across 7 clips, **but in every case the warning behaviour was still correct** |
| False (phantom) announcements | 0 — the 2-frame persistence filter suppressed all one-frame misdetections |
| Missed obstacles that mattered | 1 known: upside-down chair on a table, dark blurry clip (also missed by the raw model) |
| Inference speed | 172 ms/frame avg = **5.8 FPS** (min 129, max 227; measured over 110 frames of eval_a) |
| Announcement latency | ≈ 0.35–0.5 s from first sighting (2-frame persistence at ~6 FPS) + TTS startup; speech itself never blocks the camera loop |
| Announcement discipline | e.g. bedroom clip: **8 announcements in 471 frames**; spacing always ≥ 1.5 s, same message never repeated within 3 s |

## 3. Per-clip results

| Clip | Scenario | Mode | Outcome |
|---|---|---|---|
| bedroom walkthrough | room tour | walk | ✅ Bed correctly dominates (chair/bottle/laptop present but outranked); sensible dodge advice as camera circles it |
| bedroom walkthrough | bottle search | find | ✅ "Not visible" once → live location updates → "not visible" once when it exits. Exactly per spec |
| couch | approach couch | walk | ✅ "Couch ahead" → escalates "very close, move slightly right" |
| dustbin | approach dustbin | walk | ⚠️ Warned correctly, but named it "toilet" (dustbin is not a COCO class) |
| dark room | dark + motion blur | walk | ⚠️ Big dark cupboard warned as "refrigerator very close on left" — right warning, wrong word |
| eval_a | walk toward / between obstacles | walk | ✅ Star result: chairs tracked left/right as camera weaves; at the two-chairs-plus-wardrobe moment the side chairs (medium, out of path) stay **silent** and only the center wardrobe is announced, then escalates with dodge advice. ⚠️ wardrobe named "refrigerator", desk once named "chair" |
| eval_b | find the dark thermos | find | ✅ "Not visible" → "center ahead, medium" → "close" as camera approaches. Notable: this same dark flask was **missed entirely** in the 07-09 dim-room test — in good light it detects fine |
| eval_c | cluttered desk, multi-object | walk | ✅ Correctly silent — bottle/laptop are find-classes, bed too far. No false obstacle warnings in heavy clutter |
| eval_c | bottle among clutter | find | ✅ Picks the real water bottle out of ~10 objects, tracks it center → right |
| eval_c | scene summary | describe | ⚠️ Mixed: "A laptop ahead, a tv ahead, a bottle on your right" — bottle ✅, "laptop" is a notebook, "tv" is the dark window; backpack and bed missed at conf 0.6 |

## 4. Where it shines

- **Spatial correctness.** Direction and proximity — the safety-critical part —
  were right in every reviewed announcement across all 7 clips. If it speaks,
  the *where* is trustworthy.
- **Announcement discipline.** It says one thing, briefly, at the right
  moment, and then shuts up: persistence filter kills flickers, cooldowns
  kill spam, and the escalation override still speaks instantly when an
  obstacle gets closer. This is what makes it usable rather than noisy.
- **Path-relevance filtering.** Obstacles at medium distance off to the side
  are correctly ignored (eval_a: two flanking chairs silent, center wardrobe
  announced). It warns about what you'd actually hit.
- **The obstacle/find class split absorbs model errors.** A notebook misread
  as "laptop" can never trigger a false obstacle warning, because laptop is a
  find-only class. Several model mistakes became harmless by design.
- **Find Mode UX.** Found → location updates → "not visible" exactly once;
  picks the most visible match among many (eval_c clutter).
- **Robust engineering.** Decision and speech layers are pure logic with
  injected clocks/engines — 40 fast unit tests, reproducible clip runs, TTS
  on its own thread so vision never stalls.

## 5. Where it lacks

- **Object names, not object warnings.** Anything COCO doesn't know gets its
  nearest lookalike: dustbin → "toilet", wardrobe/cupboard → "refrigerator",
  desk → "chair", notebook → "laptop". Warnings still fire correctly, but a
  blind user hearing "toilet ahead" in a hallway loses trust. *Fix path:
  the planned door/dustbin fine-tune (deferred by decision), or renaming
  low-confidence obstacles to just "obstacle".*
- **Low light and motion blur.** The dark clip missed an upside-down chair
  entirely and misread a suitcase; the same thermos that's found easily in
  good light was invisible in dim light. Detection quality is strongly
  lighting-dependent — must be stated as an operating constraint.
- **Recall in clutter at conf 0.6.** On the busy desk, backpack and bed fell
  below threshold. The high threshold is why there are zero false alarms —
  it trades recall for precision. Reasonable for a warning system, but the
  scene summary feels incomplete because of it.
- **Scene summary inherits every model error** ("a tv ahead" from a dark
  window). It's the feature most exposed to raw detection quality.
- **~6 FPS on the dev laptop (CPU).** Fine for walking pace with the
  persistence/cooldown design, but latency would matter for fast motion;
  a phone GPU port or yolov8n fallback (`--model yolov8n.pt`) trades
  accuracy for speed.
- **Proximity is relative, not metric.** Box-area buckets ("close") are
  deliberate prototype scope — no depth in meters, and a very wide-but-far
  object can look closer than it is.
- **No doors** (not a COCO class) — the #1 requested unsupported object;
  documented as future work pending the fine-tune decision.

## 6. Remaining work / recommendations

1. **Live protocol test** (completes Phase 5): objects at known positions
   left/center/right × near/far, walk toward them with the phone stream,
   log spoken output vs ground truth. Needs ~15 min with the phone.
2. ⚠️ **RETRACTED 2026-08-02 — the confidence gate does not work.**
   Implemented 2026-07-11: obstacle warnings below
   `decision.NAME_CONFIDENCE` say generic **"obstacle"** instead of the
   class name, with the threshold set to 0.8 on the strength of a clip
   probe recorded here claiming misnames scored 0.65–0.75
   (dustbin→toilet 0.65–0.72, wardrobe→refrigerator 0.72–0.75) while
   correct names scored ≥ 0.85.

   **Re-measured on the same clips (14 sampled frames, conf 0.6, GPU), those
   numbers do not hold:**

   | | claimed 2026-07-11 | measured 2026-08-02 |
   |---|---|---|
   | dustbin → "toilet" | 0.65–0.72 | **peak 0.94**, mean 0.80 |
   | wardrobe → "refrigerator" | 0.72–0.75 | **peak 0.82** |
   | correct "chair" | ≥ 0.85 | 0.92 |

   The bands **overlap**, so no threshold separates them: at 0.8 the
   dustbin is still announced as "Toilet ahead" — which
   `test_output/phase3_WhatsApp Video 2026-07-09 at 10.14.53 PM (2)_walk.log:1`
   shows happening. The original probe was too small a sample and was read
   as a separation that was never there.

   **Confidence is not a signal for "is this word right."** It reports how
   sure the detector is about the box, over a vocabulary that contains no
   word for a wardrobe — a forced choice between 80 words can be made with
   total certainty and still be wrong. The gate is left in place (it costs
   nothing and does catch genuinely weak detections) but it is NOT the
   mechanism that fixes naming.

   **Replacement, measured 2026-08-02**: `name_index.py`, an embedding-distance
   naming head — keep YOLO's box, re-decide the word from a nearest-neighbour
   match against user-labelled crops, and abstain when the match is not clearly
   closest. Unlike confidence, that distance IS separable. Built from 280 crops
   the user labelled into 17 classes:

   - Leave-one-out over the index: at `min_margin` **0.15** it names 49/280
     crops with **49/49 correct — zero wrong names**, versus 10 errors at the
     untuned 0.05. A clean operating point exists, which is precisely what
     §6.2's confidence gate could not offer at any threshold. Full grid in
     `test_output/name_index_report.md`.
   - The separating axis is the **margin over the runner-up label**, not the
     similarity: `min_sim` is inert anywhere in 0.50-0.65 on this data.
   - Clips at stride 1 (`verify_namer.py`, 8 clips, ~2000 frames): **105
     renames in 8 distinct patterns, all inspected by eye, 104 correct**. Five
     are errors this report previously recorded as unfixable COCO-vocabulary
     limits — `refrigerator -> wardrobe` (31x, §3 dark-room row),
     `toilet -> dustbin` (23x, §3 dustbin row), `laptop -> book` (28x, the
     notebook from §3's eval_c summary row), `cell phone -> suitcase` (11x, the
     maroon suitcase of the appendix dark-clip note), and `person -> chair`
     (4x, a blanket draped over a chair that YOLO read as a person). The single
     arguable case is `bench -> suitcase` (1x) on a box holding a bench with a
     suitcase on it; both are obstacle classes, so the warning is unchanged in
     kind.
   - **Zero renames on the 2 clips containing none of the labelled objects** —
     the false-positive bar the stairs class failed.

   Note the asymmetry this buys, and why it is the point: the gate in §6.2
   could only ever downgrade a name to the generic word "obstacle". The naming
   head can produce the *right* word, and abstains — leaving YOLO's word in
   place — whenever it cannot.
3. Door + dustbin (+ stairs) fine-tune — user started training a separate
   YOLOv8n model on Colab 2026-07-11 (see `finetune_handoff.md`); will be
   integrated as a second inference pass when the `.pt` arrives.
4. Innovation features: ✅ ALL THREE shipped. Scene summary (`describe`),
   sonar audio (web frontend, WebAudio stereo beeps — tracks the find
   target in Find Mode), and Vosk voice commands (`voice.py`, offline
   small-English model, grammar-constrained; user approved the ~40 MB
   model download 2026-07-11).

## Appendix: earlier clip logs (phases 2-3, moved from CLAUDE.md 2026-07-15)

### Recorded-video test results (2026-07-10, yolov8s @ conf 0.6)

Phase 2 run on the 4 clips in `test_output/`; annotated keyframes saved as
`test_output/clipN_frameXXXX.jpg`. **All zone + proximity labels visually
correct** — remaining errors are model classification, not position logic:
- Bedroom clip: bed/chair/suitcase/bottle/laptop all detected w/ correct zones.
  One misdetection: wall calendar labeled "laptop".
- Couch clip: couch "center ahead, close" — correct. Doors in frame ignored
  (expected, not COCO).
- Dustbin clip: blue dustbin consistently detected as **"toilet"** — dustbin is
  not a COCO class. Position/proximity still right, and "toilet" is in
  OBSTACLE_CLASSES so Walk Mode would still warn (wrong name, right behavior).
  Candidate for the same future fine-tune as doors (user confirmed 2026-07-10:
  fine-tuning deferred until after core phases).
- Dark/blurry clip: maroon suitcase misread as "cell phone, very close";
  upside-down chair on table missed entirely. Confirms lighting/motion-blur
  limits already noted — worth a sentence in the report.

### Phase 3 recorded-video results (2026-07-11, walk mode unless noted)

Announcement logs in `test_output/phase3_*.log`, one annotated jpg saved per
announcement. Behavior correct on all 4 clips — sparse, one-at-a-time,
sensible messages (e.g. bedroom clip: 8 announcements across 471 frames):
- Bedroom: bed tracked around the room, "Bed very close ahead, move slightly
  right" etc.; chair/bottle/laptop present but correctly outranked by the bed.
- Bedroom find-mode (`--target bottle`): "not visible" once → location updates
  as camera moves ("Bottle top right, close" → "left, medium") → "not
  visible" once when it exits. Exactly per spec.
- Couch: "Couch ahead" → escalates "very close, move slightly right".
- Dustbin: "Toilet ahead" (known COCO name limit; warning itself correct).
- Dark clip: big dark cupboard read as "refrigerator very close on left" —
  wrong name, correct warning (same story as dustbin; fine for prototype).
