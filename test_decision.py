"""Unit tests for decision.py — run with:  python -m unittest test_decision -v"""

import unittest

from decision import (GuidanceEngine, find_message, find_target,
                      pick_obstacle, recall_message, summarize_scene,
                      walk_message)
from position import ObjectInfo, direction_phrase

_CENTER_X = {"left": 0.15, "center": 0.5, "right": 0.85}


def info(name, h_zone="center", v_zone="middle", proximity="close",
         area=0.2, center_x=None, conf=0.9):
    """Hand-built ObjectInfo, as if analyze_box had produced it."""
    cx = _CENTER_X[h_zone] if center_x is None else center_x
    return ObjectInfo(name, conf, h_zone, v_zone, proximity, area,
                      cx, direction_phrase(h_zone, v_zone))


class TestPickObstacle(unittest.TestCase):
    def test_closer_beats_more_central(self):
        vc_side = info("chair", "right", proximity="very close")
        close_center = info("person", "center", proximity="close")
        self.assertIs(pick_obstacle([close_center, vc_side]), vc_side)

    def test_same_proximity_center_wins(self):
        side = info("chair", "left", proximity="close")
        center = info("person", "center", proximity="close")
        self.assertIs(pick_obstacle([side, center]), center)

    def test_far_never_announced(self):
        self.assertIsNone(pick_obstacle([info("chair", proximity="far")]))

    def test_medium_only_matters_in_center(self):
        self.assertIsNone(pick_obstacle([info("chair", "left",
                                              proximity="medium")]))
        center = info("chair", "center", proximity="medium")
        self.assertIs(pick_obstacle([center]), center)

    def test_find_classes_never_obstacles(self):
        bottle = info("bottle", "center", proximity="very close")
        self.assertIsNone(pick_obstacle([bottle]))


class TestWalkMessage(unittest.TestCase):
    def test_side_and_center_wording(self):
        self.assertEqual(walk_message(info("chair", "right")), "Chair on right")
        self.assertEqual(walk_message(info("person", "center")), "Person ahead")

    def test_very_close_side_says_dodge_other_way(self):
        msg = walk_message(info("chair", "left", proximity="very close"))
        self.assertEqual(msg, "Chair very close on left, move slightly right")

    def test_very_close_center_dodges_to_freer_side(self):
        person = info("person", "center", proximity="very close")
        chair_right = info("chair", "right", proximity="close", area=0.2)
        msg = walk_message(person, [person, chair_right])
        self.assertEqual(msg, "Person very close ahead, move slightly left")

    def test_low_confidence_becomes_generic_obstacle(self):
        # a 0.65 "toilet" is probably a dustbin: warn, but don't name it
        self.assertEqual(walk_message(info("toilet", "right", conf=0.65)),
                         "Obstacle on right")
        # 0.75 sits in the observed misname band (wardrobe->"refrigerator"
        # scored 0.72-0.75) — threshold 0.8 catches it too
        self.assertEqual(walk_message(info("refrigerator", "left", conf=0.75)),
                         "Obstacle on left")
        vc = info("refrigerator", "left", proximity="very close", conf=0.62)
        self.assertEqual(walk_message(vc),
                         "Obstacle very close on left, move slightly right")

    def test_confident_detection_keeps_its_name(self):
        self.assertEqual(walk_message(info("chair", "right", conf=0.85)),
                         "Chair on right")


class TestEngineWalk(unittest.TestCase):
    def test_persistence_blocks_one_frame_flicker(self):
        e = GuidanceEngine()
        chair = info("chair", "right")
        self.assertIsNone(e.update([chair], 0.0))          # 1st frame: wait
        self.assertEqual(e.update([chair], 0.1), "Chair on right")

    def test_flicker_then_gone_stays_silent(self):
        e = GuidanceEngine()
        self.assertIsNone(e.update([info("tv", "left")], 0.0))
        self.assertIsNone(e.update([], 0.1))               # misdetection gone

    def test_only_top_priority_spoken(self):
        e = GuidanceEngine()
        scene = [info("person", "center"), info("chair", "right")]
        e.update(scene, 0.0)
        self.assertEqual(e.update(scene, 0.1), "Person ahead")

    def test_repeat_cooldown(self):
        e = GuidanceEngine()
        chair = info("chair", "right")
        e.update([chair], 0.0)
        self.assertEqual(e.update([chair], 0.1), "Chair on right")
        self.assertIsNone(e.update([chair], 1.0))          # too soon to repeat
        self.assertEqual(e.update([chair], 3.5), "Chair on right")

    def test_min_gap_between_different_messages(self):
        e = GuidanceEngine()
        chair = info("chair", "right")
        person = info("person", "center")
        e.update([chair], 0.0)
        self.assertEqual(e.update([chair], 0.1), "Chair on right")
        # person walks in: higher priority, but 0.3s after last message
        self.assertIsNone(e.update([chair, person], 0.2))
        self.assertIsNone(e.update([chair, person], 0.3))
        self.assertEqual(e.update([chair, person], 1.7), "Person ahead")

    def test_escalation_bypasses_cooldown(self):
        e = GuidanceEngine()
        chair = info("chair", "right", proximity="close")
        e.update([chair], 0.0)
        self.assertEqual(e.update([chair], 0.1), "Chair on right")
        closer = info("chair", "right", proximity="very close")
        self.assertEqual(e.update([closer], 0.3),
                         "Chair very close on right, move slightly left")


class TestEngineFind(unittest.TestCase):
    def test_biggest_match_wins(self):
        small = info("bottle", "left", area=0.01)
        big = info("bottle", "right", area=0.04)
        self.assertIs(find_target([small, big], "bottle"), big)

    def test_found_message(self):
        e = GuidanceEngine("find", "bottle")
        bottle = info("bottle", "right", v_zone="top", proximity="close",
                      area=0.02)
        e.update([bottle], 0.0)
        self.assertEqual(e.update([bottle], 0.1), "Bottle top right, close")

    def test_not_visible_said_once_then_periodic_reminder(self):
        e = GuidanceEngine("find", "bottle")
        self.assertIsNone(e.update([], 0.0))               # absence persistence
        self.assertEqual(e.update([], 0.1), "Bottle not visible")
        self.assertIsNone(e.update([], 5.0))               # not repeated...
        # ...but after reminder_interval the engine says it is still trying
        self.assertEqual(e.update([], 10.2), "Still looking for bottle")
        self.assertIsNone(e.update([], 15.0))              # next one waits too
        self.assertEqual(e.update([], 20.3), "Still looking for bottle")

    def test_reminder_resets_when_target_found(self):
        e = GuidanceEngine("find", "bottle")
        e.update([], 0.0)
        self.assertEqual(e.update([], 0.1), "Bottle not visible")
        bottle = info("bottle", "left", proximity="medium", area=0.005)
        e.update([bottle], 5.0)
        self.assertEqual(e.update([bottle], 5.1), "Bottle left, medium")
        # gone again -> fresh "not visible" first (now enriched by object
        # memory since the bottle was just seen), reminder only later
        e.update([], 8.0)
        self.assertEqual(e.update([], 8.1),
                         "Bottle not visible, last seen on your left")
        self.assertIsNone(e.update([], 12.0))
        self.assertEqual(e.update([], 18.2), "Still looking for bottle")

    def test_reappearing_target_reported_again(self):
        e = GuidanceEngine("find", "bottle")
        e.update([], 0.0)
        self.assertEqual(e.update([], 0.1), "Bottle not visible")
        bottle = info("bottle", "left", proximity="medium", area=0.005)
        e.update([bottle], 5.0)
        self.assertEqual(e.update([bottle], 5.1), "Bottle left, medium")
        # gone again -> "not visible" is armed again (enriched by memory)
        e.update([], 10.0)
        self.assertEqual(e.update([], 10.1),
                         "Bottle not visible, last seen on your left")

    def test_find_mode_requires_target(self):
        with self.assertRaises(ValueError):
            GuidanceEngine("find")


class TestSummary(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(summarize_scene([]), "Nothing detected")

    def test_groups_counts_and_orders_center_first(self):
        scene = [
            info("chair", "left", area=0.10),
            info("chair", "left", area=0.12),
            info("dining table", "center", area=0.30),
            info("person", "right", area=0.20),
        ]
        self.assertEqual(
            summarize_scene(scene),
            "A dining table ahead, 2 chairs on your left, a person on your right")

    def test_person_plural(self):
        scene = [info("person", "right"), info("person", "right")]
        self.assertEqual(summarize_scene(scene), "2 people on your right")


class TestFindMessage(unittest.TestCase):
    def test_not_visible_wording(self):
        self.assertEqual(find_message(None, "cell phone"),
                         "Cell phone not visible")


class TestClockBearings(unittest.TestCase):
    # info() maps left->0.15, center->0.5, right->0.85 => 10, 12, 2 o'clock
    def test_find_message_clock(self):
        bottle = info("bottle", "right", v_zone="top", proximity="close",
                      area=0.02)
        self.assertEqual(find_message(bottle, "bottle", use_clock=True),
                         "Bottle at 2 o'clock, close")

    def test_walk_message_clock(self):
        chair = info("chair", "left", proximity="close")
        self.assertEqual(walk_message(chair, use_clock=True),
                         "Chair at 10 o'clock")

    def test_walk_message_clock_center_ahead(self):
        person = info("person", "center", proximity="close")
        self.assertEqual(walk_message(person, use_clock=True),
                         "Person at 12 o'clock")

    def test_engine_toggle_switches_wording(self):
        e = GuidanceEngine("walk")
        chair = info("chair", "right", proximity="close")
        e.update([chair], 0.0)
        self.assertEqual(e.update([chair], 0.1), "Chair on right")
        e.set_clock(True)
        # same obstacle, new phrasing -> not a repeat, speaks immediately
        self.assertEqual(e.update([chair], 2.0), "Chair at 2 o'clock")


class TestObjectMemory(unittest.TestCase):
    def test_recall_message_zone(self):
        cup = info("cup", "right", proximity="close", area=0.02)
        self.assertEqual(recall_message(cup, 5, "cup"),
                         "Cup last seen on your right, 5 seconds ago")

    def test_recall_message_clock(self):
        cup = info("cup", "left", proximity="close", area=0.02)
        self.assertEqual(recall_message(cup, 1, "cup", use_clock=True),
                         "Cup last seen at 10 o'clock, a moment ago")

    def test_recall_no_memory(self):
        self.assertEqual(recall_message(None, 0, "apple"),
                         "No memory of an apple")

    def test_engine_recall_after_object_leaves(self):
        e = GuidanceEngine("walk")
        cup = info("cup", "right", proximity="close", area=0.02)
        e.update([cup], 0.0)          # seen
        e.update([], 3.0)             # gone
        self.assertEqual(e.recall("cup", 3.0),
                         "Cup last seen on your right, 3 seconds ago")

    def test_engine_recall_expires(self):
        e = GuidanceEngine("walk", memory_ttl=10.0)
        cup = info("cup", "left", area=0.02)
        e.update([cup], 0.0)
        self.assertEqual(e.recall("cup", 100.0), "No memory of a cup")

    def test_engine_recall_unseen_class(self):
        e = GuidanceEngine("walk")
        self.assertEqual(e.recall("laptop", 1.0), "No memory of a laptop")


if __name__ == "__main__":
    unittest.main()
