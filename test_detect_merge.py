"""Tests for cross-model detection merging.

The bug: infer_server concatenated yolov8s and the custom door/dustbin model's
detections with no dedup at all, so one object came back under two names.
"""
import unittest

from detect_merge import iou, merge_detections, merge_report

FLOORS = {"door": 0.4, "dustbin": 0.4}
COCO_FLOOR = 0.6


def det(name, conf, x1, y1, x2, y2, renamed=False):
    d = {"name": name, "conf": conf, "x1": x1, "y1": y1, "x2": x2, "y2": y2}
    if renamed:
        d["yolo_name"] = "something else"
    return d


class IouTest(unittest.TestCase):
    def test_identical_boxes(self):
        a = det("a", 0.9, 0, 0, 1, 1)
        self.assertAlmostEqual(iou(a, a), 1.0)

    def test_disjoint_boxes(self):
        self.assertEqual(iou(det("a", 0.9, 0, 0, 0.2, 0.2),
                             det("b", 0.9, 0.8, 0.8, 1, 1)), 0.0)

    def test_a_small_box_inside_a_big_one_scores_LOW(self):
        """The property the whole design rests on.

        Containment would score this ~1.0 and suppress the inner box. Measured
        on the user's room clip, that pair is 'person inside bed' — a person
        standing in front of a bed. IoU keeps them apart, which is why overlap
        is measured this way and not by containment.
        """
        big = det("bed", 0.9, 0.0, 0.0, 1.0, 1.0)
        small = det("person", 0.8, 0.4, 0.4, 0.6, 0.6)
        self.assertLess(iou(big, small), 0.1)


class MergeTest(unittest.TestCase):
    def test_nothing_to_do(self):
        dets = [det("chair", 0.9, 0, 0, 0.2, 0.2),
                det("bottle", 0.8, 0.8, 0.8, 1, 1)]
        self.assertEqual(len(merge_detections(dets)), 2)

    def test_same_class_duplicates_collapse(self):
        """The field log had three dustbin boxes on one object; each model
        NMSes only its own output, so near-duplicates survive."""
        dets = [det("dustbin", 0.81, 0.30, 0.30, 0.60, 0.70),
                det("dustbin", 0.70, 0.32, 0.31, 0.62, 0.71),
                det("dustbin", 0.46, 0.31, 0.32, 0.59, 0.69)]
        kept = merge_detections(dets, FLOORS, COCO_FLOOR)
        self.assertEqual(len(kept), 1)
        self.assertAlmostEqual(kept[0]["conf"], 0.81)

    def test_the_reported_bug_one_object_two_names(self):
        """'my suitcase is shown as both dustbin and suitcase'.

        Same region, two models, two names. The winner is decided by margin
        above each model's OWN floor, because 0.55 from the custom model
        (floor 0.4) and 0.88 from COCO (floor 0.6) are not comparable raw.
        """
        suitcase = det("suitcase", 0.88, 0.30, 0.30, 0.70, 0.75)
        dustbin = det("dustbin", 0.55, 0.31, 0.32, 0.69, 0.74)
        kept = merge_detections([suitcase, dustbin], FLOORS, COCO_FLOOR)
        self.assertEqual([d["name"] for d in kept], ["suitcase"])

    def test_a_confident_custom_detection_beats_a_marginal_coco_one(self):
        """The rule must not simply prefer COCO. A door at 0.91 against its
        0.4 floor is far stronger evidence than a refrigerator at 0.62
        against 0.6, and the wardrobe/door confusion is a real case."""
        fridge = det("refrigerator", 0.62, 0.20, 0.10, 0.60, 0.95)
        door = det("door", 0.91, 0.21, 0.11, 0.61, 0.94)
        kept = merge_detections([fridge, door], FLOORS, COCO_FLOOR)
        self.assertEqual([d["name"] for d in kept], ["door"])

    def test_a_person_is_never_suppressed(self):
        """A person overlapping furniture must survive whatever the scores."""
        bed = det("bed", 0.95, 0.0, 0.0, 1.0, 1.0)
        person = det("person", 0.62, 0.02, 0.02, 0.98, 0.98)
        kept = merge_detections([bed, person], FLOORS, COCO_FLOOR)
        self.assertIn("person", [d["name"] for d in kept])

    def test_nested_objects_are_left_alone(self):
        """A bottle on a table is two objects, not one seen twice."""
        table = det("dining table", 0.9, 0.0, 0.4, 1.0, 1.0)
        bottle = det("bottle", 0.8, 0.45, 0.42, 0.55, 0.58)
        kept = merge_detections([table, bottle], FLOORS, COCO_FLOOR)
        self.assertEqual(len(kept), 2)

    def test_a_committed_rename_outranks_both_models(self):
        """The naming head is the only calibrated namer in the pipeline."""
        raw = det("refrigerator", 0.95, 0.2, 0.1, 0.6, 0.95)
        renamed = det("wardrobe", 0.55, 0.21, 0.11, 0.61, 0.94, renamed=True)
        kept = merge_detections([raw, renamed], FLOORS, COCO_FLOOR)
        self.assertEqual([d["name"] for d in kept], ["wardrobe"])

    def test_partial_overlap_below_threshold_keeps_both(self):
        a = det("chair", 0.9, 0.0, 0.0, 0.50, 1.0)
        b = det("couch", 0.9, 0.42, 0.0, 1.0, 1.0)
        self.assertEqual(len(merge_detections([a, b], FLOORS, COCO_FLOOR)), 2)

    def test_order_is_preserved_for_survivors(self):
        dets = [det("chair", 0.9, 0.0, 0.0, 0.2, 0.2),
                det("dustbin", 0.5, 0.30, 0.30, 0.60, 0.70),
                det("dustbin", 0.8, 0.31, 0.31, 0.61, 0.71),
                det("bottle", 0.9, 0.8, 0.8, 1.0, 1.0)]
        kept = merge_detections(dets, FLOORS, COCO_FLOOR)
        self.assertEqual([d["name"] for d in kept],
                         ["chair", "dustbin", "bottle"])

    def test_empty_and_single(self):
        self.assertEqual(merge_detections([]), [])
        one = [det("chair", 0.9, 0, 0, 1, 1)]
        self.assertEqual(len(merge_detections(one)), 1)


class ReportTest(unittest.TestCase):
    def test_silent_when_nothing_merged(self):
        dets = [det("chair", 0.9, 0, 0, 0.2, 0.2)]
        self.assertEqual(merge_report(dets, dets), "")

    def test_names_what_it_dropped(self):
        """A dedup nobody can audit from the field log is a dedup nobody can
        trust."""
        a = det("suitcase", 0.88, 0.3, 0.3, 0.7, 0.75)
        b = det("dustbin", 0.55, 0.31, 0.32, 0.69, 0.74)
        kept = merge_detections([a, b], FLOORS, COCO_FLOOR)
        self.assertIn("dustbin", merge_report([a, b], kept))


if __name__ == "__main__":
    unittest.main()
