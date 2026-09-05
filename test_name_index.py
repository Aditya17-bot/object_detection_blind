"""Tests for name_index.py — the embedding naming head.

No ultralytics, no weights, no images: the embedder is injected, so every rule
that matters (abstain when unsure, abstain when ambiguous, abstain on _ignore,
refuse names the app has no vocabulary for, don't flip-flop) is testable with
plain vectors.
"""
import unittest

import numpy as np

from name_index import (IGNORE_LABEL, TRUSTED_KEY, Decision, NameIndex,
                        NameSmoother, Namer, crop_for, l2_normalize)


def unit(*vals):
    return np.array(vals, dtype=np.float32)


class FakeEmbedder:
    """Returns a queued vector per crop, mimicking YOLO.embed()'s list-of-
    tensors shape closely enough (plain ndarrays; classify_crops accepts both)."""

    def __init__(self, vectors):
        self.queue = list(vectors)
        self.calls = []

    def embed(self, crops, imgsz=224, device=0, verbose=False):
        self.calls.append(len(crops))
        out = [self.queue.pop(0) for _ in crops]
        return out


# three orthogonal directions = three unmistakable "classes"
DUSTBIN = unit(1, 0, 0)
CHAIR = unit(0, 1, 0)
JUNK = unit(0, 0, 1)


def simple_index(**kw):
    return NameIndex(np.stack([DUSTBIN, CHAIR, JUNK]),
                     ["dustbin", "chair", IGNORE_LABEL], **kw)


class ClassifyTest(unittest.TestCase):
    def test_exact_match_names_it(self):
        dec = simple_index().classify_vectors([DUSTBIN])[0]
        self.assertEqual(dec.name, "dustbin")
        self.assertAlmostEqual(dec.score, 1.0, places=5)

    def test_unnormalized_query_is_fine(self):
        # YOLO.embed() does NOT normalize; a longer vector must not score
        # differently from its unit version.
        dec = simple_index().classify_vectors([DUSTBIN * 7.3])[0]
        self.assertEqual(dec.name, "dustbin")
        self.assertAlmostEqual(dec.score, 1.0, places=5)

    def test_far_from_everything_abstains(self):
        # equidistant from all three, similarity ~0.577 — below MIN_SIM
        dec = simple_index().classify_vectors([unit(1, 1, 1)])[0]
        self.assertIsNone(dec.name)
        self.assertEqual(dec.reason, "below min_sim")

    def test_ambiguous_between_two_classes_abstains(self):
        # right between dustbin and chair: close to both, so no margin
        dec = simple_index().classify_vectors([unit(1, 1, 0)])[0]
        self.assertIsNone(dec.name)
        self.assertEqual(dec.reason, "ambiguous")
        self.assertLess(dec.margin, 0.05)

    def test_matching_ignore_abstains_rather_than_naming(self):
        """_ignore is in the index precisely so junk fails the test instead of
        snapping to whatever real class happens to be nearest."""
        dec = simple_index().classify_vectors([JUNK])[0]
        self.assertIsNone(dec.name)
        self.assertEqual(dec.reason, "matched _ignore")

    def test_empty_index_abstains_for_every_query(self):
        idx = NameIndex(np.zeros((0, 3), np.float32), [])
        decs = idx.classify_vectors([DUSTBIN, CHAIR])
        self.assertEqual([d.name for d in decs], [None, None])

    def test_best_match_per_label_not_average(self):
        """A class labelled from many angles must not be punished for it: one
        good match is the evidence, an average would dilute it."""
        vecs = np.stack([DUSTBIN, unit(0.3, 0.95, 0.1), unit(0.2, 0.9, 0.4),
                         CHAIR])
        idx = NameIndex(vecs, ["dustbin", "dustbin", "dustbin", "chair"])
        dec = idx.classify_vectors([DUSTBIN])[0]
        self.assertEqual(dec.name, "dustbin")

    def test_thresholds_are_configurable(self):
        # sim to dustbin is 1/sqrt(1.25) = 0.894 — a good match by default,
        # rejected once min_sim is raised above it
        query = [unit(1, 0.5, 0)]
        self.assertEqual(simple_index().classify_vectors(query)[0].name,
                         "dustbin")
        self.assertIsNone(
            simple_index(min_sim=0.95).classify_vectors(query)[0].name)

    def test_unknown_labels_reports_out_of_vocabulary(self):
        idx = NameIndex(np.stack([DUSTBIN, CHAIR]), ["dustbin", "wombat"])
        self.assertEqual(idx.unknown_labels({"dustbin", "chair"}), ["wombat"])

    def test_ignore_is_never_an_unknown_label(self):
        idx = NameIndex(np.stack([DUSTBIN]), [IGNORE_LABEL])
        self.assertEqual(idx.unknown_labels({"dustbin"}), [])

    def test_classify_crops_requires_an_embedder(self):
        with self.assertRaises(RuntimeError):
            simple_index().classify_crops([np.zeros((4, 4, 3), np.uint8)])

    def test_classify_crops_uses_the_embedder(self):
        idx = simple_index(embedder=FakeEmbedder([DUSTBIN]))
        dec = idx.classify_crops([np.zeros((4, 4, 3), np.uint8)])[0]
        self.assertEqual(dec.name, "dustbin")


class PersistenceTest(unittest.TestCase):
    def test_roundtrip_keeps_labels_and_model_name(self):
        import tempfile
        import os
        idx = NameIndex(np.stack([DUSTBIN, CHAIR]), ["dustbin", "chair"],
                        model_name="yolov8s.pt", embed_imgsz=224)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "idx.npz")
            idx.save(path)
            back = NameIndex.load(path)
        self.assertEqual(back.labels, ["dustbin", "chair"])
        self.assertEqual(back.model_name, "yolov8s.pt")
        self.assertEqual(back.embed_imgsz, 224)
        self.assertEqual(back.classify_vectors([CHAIR])[0].name, "chair")


class SmootherTest(unittest.TestCase):
    """GuidanceEngine needs the same name on 2 consecutive frames before it
    speaks, so an unstable namer produces SILENCE, not wrong words. These
    tests are about the app not going quiet."""

    def test_first_sighting_is_not_committed_immediately(self):
        s = NameSmoother(frames=2)
        box = [(0.1, 0.1, 0.3, 0.3)]
        self.assertEqual(s.smooth(box, ["dustbin"]), [None])
        self.assertEqual(s.smooth(box, ["dustbin"]), ["dustbin"])

    def test_flapping_name_never_commits(self):
        s = NameSmoother(frames=2)
        box = [(0.1, 0.1, 0.3, 0.3)]
        got = [s.smooth(box, [n])[0]
               for n in ["dustbin", "toilet", "dustbin", "toilet"]]
        self.assertEqual(got, [None, None, None, None])

    def test_committed_name_survives_a_single_disagreement(self):
        s = NameSmoother(frames=2)
        box = [(0.1, 0.1, 0.3, 0.3)]
        s.smooth(box, ["dustbin"])
        s.smooth(box, ["dustbin"])                      # committed
        self.assertEqual(s.smooth(box, ["toilet"]), ["dustbin"])
        self.assertEqual(s.smooth(box, ["dustbin"]), ["dustbin"])

    def test_sustained_change_eventually_commits(self):
        s = NameSmoother(frames=2)
        box = [(0.1, 0.1, 0.3, 0.3)]
        s.smooth(box, ["dustbin"])
        s.smooth(box, ["dustbin"])
        s.smooth(box, ["chair"])
        self.assertEqual(s.smooth(box, ["chair"]), ["chair"])

    def test_moving_box_keeps_its_track(self):
        s = NameSmoother(frames=2)
        s.smooth([(0.10, 0.10, 0.40, 0.40)], ["dustbin"])
        # shifted but heavily overlapping -> same object
        self.assertEqual(s.smooth([(0.13, 0.12, 0.43, 0.42)], ["dustbin"]),
                         ["dustbin"])

    def test_jumped_box_is_a_new_object(self):
        s = NameSmoother(frames=2)
        s.smooth([(0.0, 0.0, 0.2, 0.2)], ["dustbin"])
        self.assertEqual(s.smooth([(0.7, 0.7, 0.9, 0.9)], ["dustbin"]), [None])

    def test_overlapping_boxes_from_two_models_keep_separate_tracks(self):
        """Both models detect the wardrobe: COCO calls it 'refrigerator', the
        custom model calls it 'door', and the boxes almost coincide. Without
        key matching the greedy IoU pairing steals the track and the rename is
        silently swallowed — which is exactly what happened on eval_a."""
        s = NameSmoother(frames=1)
        boxes = [(0.10, 0.10, 0.50, 0.90), (0.11, 0.10, 0.51, 0.90)]
        keys = ["refrigerator", "door"]
        self.assertEqual(s.smooth(boxes, ["wardrobe", None], keys),
                         ["wardrobe", None])
        self.assertEqual(s.smooth(boxes, ["wardrobe", None], keys),
                         ["wardrobe", None])

    def test_a_track_is_not_reused_across_different_keys(self):
        s = NameSmoother(frames=2)
        box = [(0.1, 0.1, 0.3, 0.3)]
        s.smooth(box, ["dustbin"], ["toilet"])
        # same place, different detector name -> a different object
        self.assertEqual(s.smooth(box, ["dustbin"], ["vase"]), [None])

    def test_abstention_does_not_erase_a_committed_name(self):
        s = NameSmoother(frames=2)
        box = [(0.1, 0.1, 0.3, 0.3)]
        s.smooth(box, ["dustbin"])
        s.smooth(box, ["dustbin"])
        self.assertEqual(s.smooth(box, [None]), ["dustbin"])

    def test_frames_one_commits_at_once(self):
        s = NameSmoother(frames=1)
        self.assertEqual(s.smooth([(0.1, 0.1, 0.3, 0.3)], ["dustbin"]),
                         ["dustbin"])


class NamerTest(unittest.TestCase):
    def _frame(self):
        return np.zeros((100, 100, 3), np.uint8)

    def _det(self, name, box=(0.1, 0.1, 0.5, 0.5), conf=0.9):
        return {"name": name, "conf": conf, "x1": box[0], "y1": box[1],
                "x2": box[2], "y2": box[3]}

    def test_renames_and_records_the_original(self):
        namer = Namer(simple_index(embedder=FakeEmbedder([DUSTBIN, DUSTBIN])),
                      smoother=NameSmoother(frames=1),
                      vocabulary={"dustbin", "toilet"})
        det = self._det("toilet")
        namer.apply(self._frame(), [det])
        self.assertEqual(det["name"], "dustbin")
        self.assertEqual(det["yolo_name"], "toilet")
        self.assertEqual(namer.renamed, 1)

    def test_abstention_leaves_yolos_name_untouched(self):
        namer = Namer(simple_index(embedder=FakeEmbedder([unit(1, 1, 1)])),
                      smoother=NameSmoother(frames=1))
        det = self._det("toilet")
        namer.apply(self._frame(), [det])
        self.assertEqual(det["name"], "toilet")
        self.assertNotIn("yolo_name", det)

    def test_name_outside_vocabulary_is_refused(self):
        """An unknown name fails SILENTLY downstream — person-sized proximity,
        no metres, never walk-warned — so it is rejected here, loudly."""
        idx = NameIndex(np.stack([DUSTBIN]), ["wombat"],
                        embedder=FakeEmbedder([DUSTBIN]))
        namer = Namer(idx, smoother=NameSmoother(frames=1),
                      vocabulary={"dustbin", "chair"})
        det = self._det("toilet")
        decisions = namer.apply(self._frame(), [det])
        self.assertEqual(det["name"], "toilet")
        self.assertEqual(decisions[0].reason, "outside vocabulary")

    def test_no_vocabulary_means_no_vocabulary_check(self):
        idx = NameIndex(np.stack([DUSTBIN]), ["wombat"],
                        embedder=FakeEmbedder([DUSTBIN]))
        namer = Namer(idx, smoother=NameSmoother(frames=1))
        det = self._det("toilet")
        namer.apply(self._frame(), [det])
        self.assertEqual(det["name"], "wombat")

    def test_empty_detection_list_is_a_no_op(self):
        namer = Namer(simple_index(embedder=FakeEmbedder([])))
        self.assertEqual(namer.apply(self._frame(), []), [])

    def test_hysteresis_holds_the_rename_back_one_frame(self):
        namer = Namer(simple_index(embedder=FakeEmbedder([DUSTBIN] * 2)),
                      vocabulary={"dustbin", "toilet"})
        frame = self._frame()
        first = self._det("toilet")
        namer.apply(frame, [first])
        self.assertEqual(first["name"], "toilet")       # not yet trusted
        second = self._det("toilet")
        namer.apply(frame, [second])
        self.assertEqual(second["name"], "dustbin")

    def test_trusted_detection_is_never_renamed(self):
        """The custom model's door/dustbin classes exist BECAUSE COCO had no
        word for them, so there is no forced choice to correct. Without this
        the namer relabelled a real door as 'wardrobe' 3x on eval_a."""
        embedder = FakeEmbedder([])           # must not be consulted at all
        namer = Namer(simple_index(embedder=embedder),
                      smoother=NameSmoother(frames=1),
                      vocabulary={"dustbin", "door", "chair"})
        det = self._det("door")
        det[TRUSTED_KEY] = True
        decisions = namer.apply(self._frame(), [det])
        self.assertEqual(det["name"], "door")
        self.assertEqual(decisions[0].reason, "trusted source")
        self.assertEqual(embedder.calls, [])

    def test_trusted_and_untrusted_boxes_mix_correctly(self):
        embedder = FakeEmbedder([DUSTBIN])    # one crop only: the COCO box
        namer = Namer(simple_index(embedder=embedder),
                      smoother=NameSmoother(frames=1),
                      vocabulary={"dustbin", "door", "toilet"})
        door = self._det("door", box=(0.6, 0.6, 0.9, 0.9))
        door[TRUSTED_KEY] = True
        toilet = self._det("toilet")
        namer.apply(self._frame(), [door, toilet])
        self.assertEqual(door["name"], "door")
        self.assertEqual(toilet["name"], "dustbin")
        self.assertEqual(embedder.calls, [1])

    def test_degenerate_box_is_skipped_not_crashed(self):
        namer = Namer(simple_index(embedder=FakeEmbedder([])))
        det = self._det("toilet", box=(0.5, 0.5, 0.5, 0.5))
        decisions = namer.apply(self._frame(), [det])
        self.assertEqual(det["name"], "toilet")
        self.assertEqual(decisions[0].reason, "degenerate box")

    def test_only_the_cropped_boxes_are_embedded(self):
        embedder = FakeEmbedder([DUSTBIN])
        namer = Namer(simple_index(embedder=embedder),
                      smoother=NameSmoother(frames=1),
                      vocabulary={"dustbin", "toilet"})
        dets = [self._det("toilet", box=(0.5, 0.5, 0.5, 0.5)),  # degenerate
                self._det("toilet")]
        namer.apply(self._frame(), dets)
        self.assertEqual(embedder.calls, [1])
        self.assertEqual(dets[1]["name"], "dustbin")


class CropTest(unittest.TestCase):
    def test_pad_expands_within_the_frame(self):
        frame = np.zeros((100, 100, 3), np.uint8)
        # pad is a fraction of the BOX, not the frame: 20px box + 10px each side
        crop = crop_for(frame, 0.2, 0.2, 0.4, 0.4, pad=0.5)
        self.assertEqual(crop.shape[:2], (40, 40))

    def test_pad_is_clamped_at_the_edges(self):
        frame = np.zeros((100, 100, 3), np.uint8)
        crop = crop_for(frame, 0.0, 0.0, 0.5, 0.5, pad=0.5)
        self.assertEqual(crop.shape[:2], (75, 75))

    def test_degenerate_box_returns_none(self):
        frame = np.zeros((100, 100, 3), np.uint8)
        self.assertIsNone(crop_for(frame, 0.5, 0.5, 0.5, 0.5))

    def test_crop_is_a_copy(self):
        frame = np.zeros((100, 100, 3), np.uint8)
        crop = crop_for(frame, 0.1, 0.1, 0.9, 0.9)
        crop[0, 0] = 255
        self.assertEqual(frame[10, 10, 0], 0)


class NormalizeTest(unittest.TestCase):
    def test_rows_become_unit_length(self):
        m = l2_normalize(np.array([[3.0, 4.0], [0.0, 2.0]]))
        np.testing.assert_allclose(np.linalg.norm(m, axis=1), [1.0, 1.0],
                                   rtol=1e-5)

    def test_zero_vector_does_not_divide_by_zero(self):
        m = l2_normalize(np.zeros((1, 3)))
        self.assertTrue(np.all(np.isfinite(m)))

    def test_single_vector_is_promoted_to_a_row(self):
        self.assertEqual(l2_normalize(np.array([3.0, 4.0])).shape, (1, 2))


class DecisionReprTest(unittest.TestCase):
    def test_repr_is_readable(self):
        self.assertIn("dustbin", repr(Decision("dustbin", 0.9, 0.2, "toilet",
                                               "match")))


class LeaveOneOutTest(unittest.TestCase):
    """build_name_index.leave_one_out must score what the RUNTIME does.

    It is the report that decides which thresholds ship, so any divergence
    between it and NameIndex.classify_vectors picks the wrong operating point.
    The 2026-08-02 build counted a predicted `_ignore` as a wrong name, which
    inflated the error count with the one outcome that is by definition safe
    (the detection simply keeps YOLO's word) and hid the fact that a clean
    setting existed at all.
    """

    def setUp(self):
        import build_name_index
        self.loo = build_name_index.leave_one_out

    def test_predicting_ignore_is_an_abstention_not_an_error(self):
        # two crops of a real class, two of _ignore, arranged so that leaving a
        # 'chair' out leaves _ignore as its nearest neighbour
        vectors = np.array([unit(1, 0, 0), unit(0, 1, 0), unit(0, 1, 0.02),
                            unit(0, 1, 0.04)])
        labels = ["chair", IGNORE_LABEL, "chair", IGNORE_LABEL]
        rows = self.loo(vectors, labels, min_sim=0.0, min_margin=0.0)
        for true, pred, _sim, _margin, reason in rows:
            self.assertNotEqual(pred, IGNORE_LABEL,
                                "_ignore must never be reported as a NAME")
            if reason == "matched _ignore":
                self.assertIsNone(pred)

    def test_a_junk_crop_named_as_a_real_class_still_counts_as_wrong(self):
        # the reverse direction is a genuine error: it puts a word in the ear
        vectors = np.array([unit(1, 0, 0), unit(1, 0, 0.01)])
        labels = ["chair", IGNORE_LABEL]
        rows = self.loo(vectors, labels, min_sim=0.0, min_margin=0.0)
        wrong = [r for r in rows if r[1] is not None and r[1] != r[0]]
        self.assertEqual([(r[0], r[1]) for r in wrong], [(IGNORE_LABEL,
                                                          "chair")])

    def test_it_matches_the_runtime_classifier_decision_for_decision(self):
        vectors = np.array([unit(1, 0, 0), unit(0.9, 0.3, 0), unit(0, 1, 0),
                            unit(0, 0.9, 0.3), unit(0, 0, 1)])
        labels = ["chair", "chair", "dustbin", "dustbin", IGNORE_LABEL]
        for min_sim, min_margin in ((0.0, 0.0), (0.62, 0.05), (0.62, 0.15)):
            rows = self.loo(vectors, labels, min_sim, min_margin)
            for i, (_true, pred, _s, _m, reason) in enumerate(rows):
                # rebuild the index without crop i, then classify crop i
                keep = [j for j in range(len(labels)) if j != i]
                idx = NameIndex(vectors[keep], [labels[j] for j in keep],
                                min_sim=min_sim, min_margin=min_margin)
                live = idx.classify_vectors(vectors[i:i + 1])[0]
                self.assertEqual(pred, live.name)
                self.assertEqual(reason, live.reason)


if __name__ == "__main__":
    unittest.main()
