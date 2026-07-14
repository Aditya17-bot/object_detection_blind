"""Unit tests for position.py — run with:  python -m unittest test_position -v"""

import unittest

from position import (analyze_box, clock_hour, clock_phrase,
                      direction_phrase, distance_meters, proximity_bucket)

W, H = 1280, 720  # pretend frame size; logic must not care about actual size


def box_at(cx, cy, w=0.1, h=0.1):
    """Pixel box of given normalized size centered at normalized (cx, cy)."""
    return (W * (cx - w / 2), H * (cy - h / 2),
            W * (cx + w / 2), H * (cy + h / 2))


class TestZones(unittest.TestCase):
    def check(self, cx, cy, h_zone, v_zone):
        info = analyze_box("chair", 0.9, *box_at(cx, cy), W, H)
        self.assertEqual((info.h_zone, info.v_zone), (h_zone, v_zone))

    def test_left(self):
        self.check(0.10, 0.5, "left", "middle")

    def test_dead_center(self):
        self.check(0.50, 0.5, "center", "middle")

    def test_right(self):
        self.check(0.90, 0.5, "right", "middle")

    def test_top_right(self):
        self.check(0.85, 0.15, "right", "top")

    def test_bottom_left(self):
        self.check(0.15, 0.90, "left", "bottom")

    def test_boundary_first_third(self):
        # zone changes exactly at 1/3: just below is left, at 1/3 is center
        self.check(0.33, 0.5, "left", "middle")
        self.check(0.34, 0.5, "center", "middle")


class TestPhrases(unittest.TestCase):
    def test_middle_row_drops_vertical(self):
        self.assertEqual(direction_phrase("left", "middle"), "left")
        self.assertEqual(direction_phrase("center", "middle"), "center ahead")

    def test_vertical_mentioned_when_notable(self):
        self.assertEqual(direction_phrase("right", "top"), "top right")
        self.assertEqual(direction_phrase("center", "bottom"), "bottom center")


class TestProximity(unittest.TestCase):
    def test_person_buckets(self):
        self.assertEqual(proximity_bucket("person", 0.50), "very close")
        self.assertEqual(proximity_bucket("person", 0.20), "close")
        self.assertEqual(proximity_bucket("person", 0.08), "medium")
        self.assertEqual(proximity_bucket("person", 0.01), "far")

    def test_bottle_uses_smaller_thresholds(self):
        # 2% of the frame is a FAR person but a CLOSE bottle
        self.assertEqual(proximity_bucket("person", 0.02), "far")
        self.assertEqual(proximity_bucket("bottle", 0.02), "close")

    def test_unknown_class_falls_back(self):
        self.assertEqual(proximity_bucket("dog", 0.40), "very close")


class TestCustomModelClasses(unittest.TestCase):
    def test_custom_classes_are_obstacles_with_thresholds(self):
        # door/dustbin come from door_dustbin_stairs.pt, not COCO — they
        # must be first-class citizens of the position logic
        from position import OBSTACLE_CLASSES, _AREA_THRESHOLDS
        for name in ("door", "dustbin"):
            self.assertIn(name, OBSTACLE_CLASSES)
            self.assertIn(name, _AREA_THRESHOLDS)

    def test_stairs_skipped_until_retrained(self):
        # user decision 2026-07-11: stairs class recall too low (0.072) +
        # wall/ceiling false positives — must NOT reach the guidance layer
        from position import TARGET_CLASSES
        self.assertNotIn("stairs", TARGET_CLASSES)

    def test_door_proximity_sane(self):
        self.assertEqual(proximity_bucket("door", 0.50), "very close")
        self.assertEqual(proximity_bucket("door", 0.02), "far")


class TestAnalyzeBox(unittest.TestCase):
    def test_full_pipeline_one_box(self):
        # big centered person: half the frame wide/tall => area 0.25 => close
        info = analyze_box("person", 0.88, *box_at(0.5, 0.5, 0.5, 0.5), W, H)
        self.assertEqual(info.phrase, "center ahead")
        self.assertEqual(info.proximity, "close")
        self.assertAlmostEqual(info.area, 0.25, places=3)
        self.assertAlmostEqual(info.center_x, 0.5, places=3)

    def test_scale_invariance(self):
        # same normalized box must give identical results at any resolution
        a = analyze_box("chair", 0.9, 64, 36, 192, 108, 640, 360)
        b = analyze_box("chair", 0.9, 128, 72, 384, 216, 1280, 720)
        self.assertEqual((a.h_zone, a.v_zone, a.proximity),
                         (b.h_zone, b.v_zone, b.proximity))


class TestDistanceMeters(unittest.TestCase):
    def test_pinhole_estimate(self):
        # 1.7 m person filling half the frame height: 1.7 * 0.85 / 0.5 ~= 2.9 m
        self.assertAlmostEqual(distance_meters("person", 0.5), 2.9, places=1)

    def test_smaller_box_is_further(self):
        near = distance_meters("person", 0.5)
        far = distance_meters("person", 0.1)
        self.assertGreater(far, near)

    def test_unknown_class_has_no_distance(self):
        self.assertIsNone(distance_meters("dog", 0.5))

    def test_degenerate_box(self):
        self.assertIsNone(distance_meters("person", 0.0))

    def test_analyze_box_populates_distance(self):
        info = analyze_box("person", 0.9, *box_at(0.5, 0.5, 0.1, 0.5), W, H)
        self.assertIsNotNone(info.distance_m)


class TestClockHour(unittest.TestCase):
    def test_center_is_twelve(self):
        self.assertEqual(clock_hour(0.5), 12)

    def test_far_left_and_right(self):
        self.assertEqual(clock_hour(0.0), 10)
        self.assertEqual(clock_hour(0.99), 2)

    def test_bands_in_order(self):
        hours = [clock_hour(x) for x in (0.1, 0.3, 0.5, 0.7, 0.9)]
        self.assertEqual(hours, [10, 11, 12, 1, 2])

    def test_phrase(self):
        self.assertEqual(clock_phrase(0.85), "at 2 o'clock")


if __name__ == "__main__":
    unittest.main()
