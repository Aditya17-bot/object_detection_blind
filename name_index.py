"""BlindAssist — embedding-based naming head.

The problem it solves
---------------------
YOLO is good at *where* and bad at *what*. COCO has 80 words and none of them
is "wardrobe", "dustbin" or "window", so the detector makes a forced choice and
picks the nearest word it owns — the user's dustbin comes back as "toilet" at
0.94 confidence. The gate meant to catch that (decision.NAME_CONFIDENCE: say
the generic word "obstacle" below 0.8) rests on a probe claiming misnames score
0.65-0.75 and correct names >=0.85. Re-measured 2026-08-02, those bands
OVERLAP, so no threshold separates them and "Toilet ahead" gets spoken.
Confidence is not a signal for "is this word right".

So: keep YOLO's box, re-decide the name from an embedding of the crop matched
against a small set of user-labelled examples, and — the point of the whole
exercise — use the *distance* to that match as an abstention signal that is
calibrated on this layer's own failure mode.

Design rules
------------
* **Abstain by default.** A rename happens only when the nearest labelled
  example is close AND clearly closer than the best competing label. Otherwise
  YOLO's name survives untouched. Being unsure must cost nothing.
* **_ignore is a first-class label.** Crops the user marked as "not a thing we
  name" (wall texture, reflections, junk boxes) are in the index precisely so a
  query landing among them fails the margin test instead of snapping to the
  nearest real class.
* **Hysteresis is mandatory.** GuidanceEngine._streaks requires the same name on
  2 consecutive frames before speaking, so a namer that flip-flops between
  "toilet" and "dustbin" makes the app *quieter*, not better. `NameSmoother`
  tracks boxes across frames and only commits a change once it repeats.
* **The embedder is injected**, so everything here is unit-testable with plain
  numpy vectors and no ultralytics import.

Vocabulary constraint: labels that leave here should be in
position.TARGET_CLASSES, or downstream failures are SILENT — an unknown name
gets person-sized proximity thresholds, no metre estimate, and is never
walk-warned. `unknown_labels()` reports violations; build_name_index.py refuses
to build without --allow-unknown.
"""
import numpy as np

# --- abstention thresholds --------------------------------------------------
# Cosine similarity to the nearest labelled crop. Below this the query looks
# like nothing we were taught, so YOLO's name stands.
MIN_SIM = 0.62
# How much closer the winning label must be than the best *other* label. This
# is the real safety knob: two labels tied at 0.9 means the crop is ambiguous,
# and renaming on a coin-flip is exactly the failure the stairs class shipped
# (0.072 recall with 0.68-0.91 confidence false positives).
#
# TUNED 2026-08-02 from the leave-one-out sweep over the user's 280 labelled
# crops (report: test_output/name_index_report.md). 0.15 is the highest-
# coverage setting with ZERO wrong names: 49 crops named, 0 errors, versus 10
# errors at the old 0.05. Both defect classes survive it (dustbin 3/5,
# wardrobe 7/16). The sweep also showed MIN_SIM is inert anywhere in
# 0.50-0.65 on this data — margin does all the separating — so 0.62 is kept
# only as a floor against a query unrelated to anything labelled. Re-run
# build_name_index.py and re-read the sweep after adding crops; do not carry
# these numbers to a differently-labelled index.
MIN_MARGIN = 0.15

# Label meaning "do not name this". Present in the index on purpose.
IGNORE_LABEL = "_ignore"

# Detections carrying this key are never renamed. It is set for boxes from the
# dedicated custom model (door / dustbin): those classes exist precisely
# BECAUSE COCO had no word for them, so there is no forced-choice error to fix,
# and the 6.2 MB custom model beats yolov8s on exactly those objects (door at
# 0.91). Verified necessary: without it the namer relabelled a real door as
# "wardrobe" 3x on eval_a, both being large flat rectangles.
TRUSTED_KEY = "trusted_name"

# Consecutive agreeing frames before a tracked box's name is allowed to change.
HYSTERESIS_FRAMES = 2
# IoU above which a box in this frame is considered the same object as a box in
# the previous frame.
TRACK_IOU = 0.4


class Decision:
    """Outcome of naming one crop. `name is None` means abstain."""

    __slots__ = ("name", "score", "margin", "runner_up", "reason")

    def __init__(self, name, score, margin, runner_up, reason):
        self.name = name
        self.score = score            # cosine similarity to the best label
        self.margin = margin          # best label's lead over the runner-up
        self.runner_up = runner_up    # label that came second (may be None)
        self.reason = reason          # why we abstained, for logging/eval

    def __repr__(self):  # pragma: no cover — debugging aid
        return (f"Decision(name={self.name!r}, score={self.score:.3f}, "
                f"margin={self.margin:.3f}, reason={self.reason!r})")


def l2_normalize(matrix):
    """Row-wise L2 normalization. YOLO.embed() does NOT normalize."""
    m = np.asarray(matrix, dtype=np.float32)
    if m.ndim == 1:
        m = m[None, :]
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.maximum(norms, 1e-8)


class NameIndex:
    """Nearest-neighbour namer over labelled crop embeddings.

    Not a training run: adding a class means adding crops and rebuilding, which
    takes seconds and cannot overfit in the way a fine-tune can.
    """

    def __init__(self, vectors, labels, embedder=None, min_sim=MIN_SIM,
                 min_margin=MIN_MARGIN, embed_imgsz=224, device=0,
                 model_name=""):
        self.vectors = l2_normalize(vectors) if len(labels) else \
            np.zeros((0, 1), np.float32)
        self.labels = list(labels)
        self.classes = sorted(set(self.labels))
        self.embedder = embedder
        self.min_sim = min_sim
        self.min_margin = min_margin
        self.embed_imgsz = embed_imgsz
        self.device = device
        # Which weights produced these vectors. Embeddings from a different
        # backbone are not comparable — every similarity would be meaningless
        # but nothing would crash, so the check has to be explicit.
        self.model_name = model_name

    # -- persistence -------------------------------------------------------

    @classmethod
    def load(cls, path, embedder=None, **kw):
        data = np.load(path, allow_pickle=False)
        return cls(data["vectors"], [str(s) for s in data["labels"]],
                   embedder=embedder,
                   embed_imgsz=int(data["embed_imgsz"]) if "embed_imgsz"
                   in data else 224,
                   model_name=str(data["model_name"]) if "model_name" in data
                   else "", **kw)

    def save(self, path):
        np.savez_compressed(path, vectors=self.vectors,
                            labels=np.array(self.labels),
                            embed_imgsz=np.array(self.embed_imgsz),
                            model_name=np.array(self.model_name))

    # -- classification ----------------------------------------------------

    def classify_vectors(self, queries):
        """Decisions for pre-computed (unnormalized is fine) query vectors."""
        if not self.labels:
            return [Decision(None, 0.0, 0.0, None, "empty index")
                    for _ in range(len(np.atleast_2d(queries)))]
        q = l2_normalize(queries)
        sims = q @ self.vectors.T                     # (n_queries, n_examples)
        out = []
        for row in sims:
            # best similarity achieved by each label — max, not mean: one good
            # match of the right view is the evidence, and averaging would
            # punish a class the user labelled from many different angles.
            best = {}
            for lab, s in zip(self.labels, row):
                s = float(s)
                if s > best.get(lab, -2.0):
                    best[lab] = s
            ranked = sorted(best.items(), key=lambda kv: -kv[1])
            top_label, top_sim = ranked[0]
            runner_up, runner_sim = (ranked[1] if len(ranked) > 1
                                     else (None, -1.0))
            margin = top_sim - runner_sim if runner_up is not None else top_sim
            if top_sim < self.min_sim:
                out.append(Decision(None, top_sim, margin, runner_up,
                                    "below min_sim"))
            elif margin < self.min_margin:
                out.append(Decision(None, top_sim, margin, runner_up,
                                    "ambiguous"))
            elif top_label == IGNORE_LABEL:
                out.append(Decision(None, top_sim, margin, runner_up,
                                    "matched _ignore"))
            else:
                out.append(Decision(top_label, top_sim, margin, runner_up,
                                    "match"))
        return out

    def classify_crops(self, crops):
        """Decisions for BGR image crops. Requires an embedder."""
        if not crops:
            return []
        if self.embedder is None:
            raise RuntimeError("NameIndex has no embedder — pass one to "
                               "load()/__init__ to classify images")
        vecs = self.embedder.embed(crops, imgsz=self.embed_imgsz,
                                   device=self.device, verbose=False)
        arr = np.stack([v.detach().float().cpu().numpy() if hasattr(v, "detach")
                        else np.asarray(v) for v in vecs])
        return self.classify_vectors(arr)

    # -- vocabulary guard --------------------------------------------------

    def unknown_labels(self, vocabulary):
        """Labels this index can emit that the rest of the app doesn't know.

        Downstream failures for an unknown name are silent, not loud, which is
        why this is checked at build time rather than discovered in the field.
        """
        return sorted(l for l in self.classes
                      if l != IGNORE_LABEL and l not in vocabulary)


# --- box cropping (shared by every call site) -------------------------------

def crop_for(frame, x1, y1, x2, y2, pad=0.06):
    """BGR crop for one NORMALIZED xyxy box, with a little context padding.

    Context matters: a bare dustbin rectangle and a bare toilet rectangle are
    both a pale blob; the surrounding floor and wall are part of what tells
    them apart. Returns None for a degenerate box.
    """
    h, w = frame.shape[:2]
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    a = int(max(0.0, x1 - px) * w)
    b = int(min(1.0, x2 + px) * w)
    c = int(max(0.0, y1 - py) * h)
    d = int(min(1.0, y2 + py) * h)
    if b - a < 2 or d - c < 2:
        return None
    return frame[c:d, a:b].copy()


# --- hysteresis -------------------------------------------------------------

def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


class NameSmoother:
    """Stops the namer flip-flopping between two words for one object.

    GuidanceEngine requires the same name on 2 consecutive frames before it
    speaks (decision.py `_streaks`), so an unstable namer does not produce
    wrong announcements — it produces SILENCE, which is worse, because the app
    looks dead while an obstacle is in front of the user.

    Boxes are matched to the previous frame by IoU AND by key — the key being
    the detector's own name for the box. IoU alone is not enough: two models
    run over the same frame produce near-identical boxes for one object (the
    COCO pass calls the wardrobe "refrigerator" while the custom pass calls it
    "door"), and a greedy IoU match happily pairs this frame's COCO box with
    last frame's custom track. That silently swallowed every rename on eval_a
    until keys were added.
    """

    def __init__(self, frames=HYSTERESIS_FRAMES, iou=TRACK_IOU):
        self.frames = frames
        self.iou = iou
        self._tracks = []   # [{"box", "key", "committed", "pending", "count"}]

    def smooth(self, boxes, proposals, keys=None):
        """boxes: normalized xyxy tuples. proposals: name or None per box.
        keys: per-box track identity (the detector's original name).

        Returns the committed name (or None) per box, in the same order.
        """
        out = []
        fresh = []
        used = set()
        if keys is None:
            keys = [None] * len(boxes)
        for box, proposed, key in zip(boxes, proposals, keys):
            best, best_iou = None, self.iou
            for i, tr in enumerate(self._tracks):
                if i in used or tr["key"] != key:
                    continue
                v = _iou(box, tr["box"])
                if v >= best_iou:
                    best, best_iou = i, v
            if best is None:
                # new object: a first sighting is not yet evidence, so hold the
                # rename back one frame rather than trusting a single view
                track = {"box": box, "key": key, "committed": None,
                         "pending": proposed, "count": 1}
                if self.frames <= 1:
                    track["committed"], track["pending"] = proposed, None
            else:
                used.add(best)
                track = self._tracks[best]
                track["box"] = box
                if proposed == track["committed"]:
                    track["pending"], track["count"] = None, 0
                elif proposed == track["pending"]:
                    track["count"] += 1
                    if track["count"] >= self.frames:
                        track["committed"], track["pending"] = proposed, None
                        track["count"] = 0
                else:
                    track["pending"], track["count"] = proposed, 1
            fresh.append(track)
            out.append(track["committed"])
        self._tracks = fresh
        return out

    def reset(self):
        self._tracks = []


# --- the whole hook in one object -------------------------------------------

class Namer:
    """Index + smoother: the thing the servers actually hold.

    `apply(frame, dets)` rewrites `d["name"]` in place for detections the index
    is confident about, and leaves the rest exactly as YOLO produced them.
    Every renamed detection keeps its original under `d["yolo_name"]` so logs
    and evaluation can tell what changed.
    """

    def __init__(self, index, smoother=None, vocabulary=None):
        self.index = index
        self.smoother = smoother if smoother is not None else NameSmoother()
        self.vocabulary = vocabulary
        self.renamed = 0
        self.abstained = 0

    @classmethod
    def load(cls, path, embedder, vocabulary=None, **kw):
        return cls(NameIndex.load(path, embedder=embedder, **kw),
                   vocabulary=vocabulary)

    @classmethod
    def maybe_load(cls, path, embedder, model_name, vocabulary=None):
        """Load the index if it exists, else return None — the app runs
        exactly as before without one. Prints what happened either way:
        a naming head that silently isn't running looks identical to one that
        is running and abstaining, and those need different fixes.
        """
        import os
        if not path or not os.path.exists(path):
            print(f"No naming index at {path} — YOLO names used as-is")
            return None
        namer = cls.load(path, embedder, vocabulary=vocabulary)
        idx = namer.index
        if idx.model_name and model_name and idx.model_name != model_name:
            # Comparing vectors across backbones produces confident nonsense,
            # not an error, so refuse rather than warn.
            print(f"Naming index was built with {idx.model_name} but this "
                  f"server embeds with {model_name} — vectors are not "
                  f"comparable. Index DISABLED; rebuild with "
                  f"build_name_index.py --model {model_name}")
            return None
        print(f"Naming index ON: {len(idx.labels)} crops, "
              f"{len(idx.classes)} labels {idx.classes}")
        return namer

    def apply(self, frame, dets):
        """Rename in place. Returns the per-detection Decision list."""
        if not dets:
            self.smoother.smooth([], [], [])
            return []
        # Track identity is the DETECTOR's name, captured before any rename —
        # it is what makes this frame's box the same object as last frame's.
        keys = [d["name"] for d in dets]
        boxes, crops, order = [], [], []
        for i, d in enumerate(dets):
            box = (d["x1"], d["y1"], d["x2"], d["y2"])
            boxes.append(box)
            if d.get(TRUSTED_KEY):
                continue          # not even embedded — nothing to decide
            crop = crop_for(frame, *box)
            if crop is not None:
                crops.append(crop)
                order.append(i)
        decisions = [Decision(None, 0.0, 0.0, None,
                              "trusted source" if d.get(TRUSTED_KEY)
                              else "degenerate box")
                     for d in dets]
        for i, dec in zip(order, self.index.classify_crops(crops)):
            decisions[i] = dec

        proposals = []
        for dec in decisions:
            name = dec.name
            # A name the rest of the app has never heard of fails SILENTLY
            # downstream (wrong proximity thresholds, no metres, never
            # walk-warned), so refuse it here where it is visible.
            if name is not None and self.vocabulary is not None \
                    and name not in self.vocabulary:
                dec.reason = "outside vocabulary"
                name = None
            proposals.append(name)

        for det, dec, committed in zip(
                dets, decisions,
                self.smoother.smooth(boxes, proposals, keys)):
            if committed and committed != det["name"]:
                det["yolo_name"] = det["name"]
                det["name"] = committed
                det["name_score"] = round(dec.score, 3)
                # A committed rename is TRUSTED, and the decision layer must be
                # told so. It cleared MIN_MARGIN against every competing label
                # and survived hysteresis — leave-one-out 49/49 correct, 104/105
                # correct over ~2000 clip frames. The detector's own confidence
                # is NOT a signal for "is this word right" (measured: a dustbin
                # called "toilet" peaks at 0.94, a correct "chair" at 0.92 — the
                # bands overlap, so no threshold separates them). Without this
                # flag decision.py's NAME_CONFIDENCE gate throws the naming
                # head's verdict away and speaks the generic "obstacle" for an
                # object we identified correctly.
                det[TRUSTED_KEY] = True
                self.renamed += 1
            elif dec.name is None:
                self.abstained += 1
        return decisions
