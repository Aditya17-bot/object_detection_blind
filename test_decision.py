"""Unit tests for decision.py — run with:  python -m unittest test_decision -v"""

import unittest

from decision import (GuidanceEngine, check_direction, clear_path,
                      count_message, find_message, find_target, pick_obstacle,
                      recall_message, summarize_scene, walk_message)
from position import ObjectInfo, analyze_box, direction_phrase

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

    def test_medium_is_silent_even_dead_ahead(self):
        # 2026-07-31: walk mode used to announce a medium obstacle in the
        # centre. Field feedback was that continuous naming became noise, so
        # the line moved to WALK_MIN_PROXIMITY ("close"). The full inventory
        # is still available on demand through describe() / check().
        self.assertIsNone(pick_obstacle([info("chair", "left",
                                              proximity="medium")]))
        self.assertIsNone(pick_obstacle([info("chair", "center",
                                              proximity="medium")]))

    def test_close_and_very_close_still_announced(self):
        close = info("chair", "left", proximity="close")
        self.assertIs(pick_obstacle([close]), close)
        vc = info("chair", "right", proximity="very close")
        self.assertIs(pick_obstacle([vc]), vc)

    def test_find_classes_never_obstacles(self):
        bottle = info("bottle", "center", proximity="very close")
        self.assertIsNone(pick_obstacle([bottle]))


class TestWalkMessage(unittest.TestCase):
    # hand-built infos have distance_m=None, so the proximity BUCKET is
    # appended ("close"); real analyze_box infos would say "about N meters"
    # for medium/far. See TestDistanceMessages for the metric path.
    def test_side_and_center_wording(self):
        self.assertEqual(walk_message(info("chair", "right")),
                         "Chair on right, close")
        self.assertEqual(walk_message(info("person", "center")),
                         "Person ahead, close")

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
                         "Obstacle on right, close")
        # 0.75 sits in the observed misname band (wardrobe->"refrigerator"
        # scored 0.72-0.75) — threshold 0.8 catches it too
        self.assertEqual(walk_message(info("refrigerator", "left", conf=0.75)),
                         "Obstacle on left, close")
        vc = info("refrigerator", "left", proximity="very close", conf=0.62)
        self.assertEqual(walk_message(vc),
                         "Obstacle very close on left, move slightly right")

    def test_confident_detection_keeps_its_name(self):
        self.assertEqual(walk_message(info("chair", "right", conf=0.85)),
                         "Chair on right, close")

    def test_custom_model_classes_named_below_threshold(self):
        # door/dustbin come from the DEDICATED model (no COCO lookalike), so
        # they keep their name even at 0.5 conf — never spoken as "obstacle".
        self.assertEqual(walk_message(info("door", "center", conf=0.5)),
                         "Door ahead, close")
        self.assertEqual(walk_message(info("dustbin", "left", conf=0.55)),
                         "Dustbin on left, close")


class TestEngineWalk(unittest.TestCase):
    # these pin the anti-spam LOGIC, so they force zone wording (use_clock=
    # False) and use hand-built infos (distance_m=None -> bucket "close").
    def test_persistence_blocks_one_frame_flicker(self):
        e = GuidanceEngine(use_clock=False)
        chair = info("chair", "right")
        self.assertIsNone(e.update([chair], 0.0))          # 1st frame: wait
        self.assertEqual(e.update([chair], 0.1), "Chair on right, close")

    def test_flicker_then_gone_stays_silent(self):
        e = GuidanceEngine(use_clock=False)
        self.assertIsNone(e.update([info("tv", "left")], 0.0))
        self.assertIsNone(e.update([], 0.1))               # misdetection gone

    def test_only_top_priority_spoken(self):
        e = GuidanceEngine(use_clock=False)
        scene = [info("person", "center"), info("chair", "right")]
        e.update(scene, 0.0)
        self.assertEqual(e.update(scene, 0.1), "Person ahead, close")

    def test_repeat_cooldown(self):
        e = GuidanceEngine(use_clock=False)
        chair = info("chair", "right")
        e.update([chair], 0.0)
        self.assertEqual(e.update([chair], 0.1), "Chair on right, close")
        self.assertIsNone(e.update([chair], 1.0))          # too soon to repeat
        self.assertEqual(e.update([chair], 3.5), "Chair on right, close")

    def test_min_gap_between_different_messages(self):
        e = GuidanceEngine(use_clock=False)
        chair = info("chair", "right")
        person = info("person", "center")
        e.update([chair], 0.0)
        self.assertEqual(e.update([chair], 0.1), "Chair on right, close")
        # person walks in: higher priority, but 0.3s after last message
        self.assertIsNone(e.update([chair, person], 0.2))
        self.assertIsNone(e.update([chair, person], 0.3))
        self.assertEqual(e.update([chair, person], 1.7), "Person ahead, close")

    def test_escalation_bypasses_cooldown(self):
        e = GuidanceEngine(use_clock=False)
        chair = info("chair", "right", proximity="close")
        e.update([chair], 0.0)
        self.assertEqual(e.update([chair], 0.1), "Chair on right, close")
        closer = info("chair", "right", proximity="very close")
        self.assertEqual(e.update([closer], 0.3),
                         "Chair very close on right, move slightly left")


class TestEngineFind(unittest.TestCase):
    def test_biggest_match_wins(self):
        small = info("bottle", "left", area=0.01)
        big = info("bottle", "right", area=0.04)
        self.assertIs(find_target([small, big], "bottle"), big)

    def test_found_message(self):
        e = GuidanceEngine("find", "bottle", use_clock=False)
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

    def test_reminder_keeps_firing_until_target_found(self):
        e = GuidanceEngine("find", "bottle", use_clock=False)
        e.update([], 0.0)
        self.assertEqual(e.update([], 0.1), "Bottle not visible")
        self.assertIsNone(e.update([], 5.0))
        self.assertEqual(e.update([], 10.2), "Still looking for bottle")
        bottle = info("bottle", "left", proximity="medium", area=0.005)
        e.update([bottle], 15.0)
        self.assertEqual(e.update([bottle], 15.1), "Bottle left, medium")

    def test_found_completes_search(self):
        # user decision 2026-07-16: announcing the position once IS the find
        # result — the engine must drop back to walk mode, not keep repeating
        e = GuidanceEngine("find", "bottle", use_clock=False)
        bottle = info("bottle", "left", proximity="medium", area=0.005)
        e.update([bottle], 0.0)
        self.assertEqual(e.update([bottle], 0.1), "Bottle left, medium")
        self.assertEqual(e.mode, "walk")
        # bottle is a FIND class -> silent in walk mode, no more repeats
        self.assertIsNone(e.update([bottle], 5.0))
        self.assertIsNone(e.update([bottle], 10.0))

    def test_new_search_after_completion(self):
        e = GuidanceEngine("find", "bottle", use_clock=False)
        bottle = info("bottle", "left", proximity="medium", area=0.005)
        e.update([bottle], 0.0)
        self.assertEqual(e.update([bottle], 0.1), "Bottle left, medium")
        # asking again starts a fresh search that reports again (the bottle's
        # persistence streak is already met — it never left the frame)
        e.set_mode("find", "bottle")
        self.assertEqual(e.update([bottle], 5.0), "Bottle left, medium")
        self.assertEqual(e.mode, "walk")

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
    # info() maps left->0.15, center->0.5, right->0.85. At the corrected
    # 65-degree field of view those are -22.8, 0.0 and +22.8 degrees, i.e.
    # 11, 12 and 1 o'clock. The old expectations (10 / 12 / 2) came from a
    # mapping that spread 120 degrees across a 65-degree camera and so
    # roughly doubled every bearing — see test_position.TestClockHour.
    def test_find_message_clock(self):
        bottle = info("bottle", "right", v_zone="top", proximity="close",
                      area=0.02)
        self.assertEqual(find_message(bottle, "bottle", use_clock=True),
                         "Bottle at 1 o'clock, close")

    def test_walk_message_clock(self):
        chair = info("chair", "left", proximity="close")
        self.assertEqual(walk_message(chair, use_clock=True),
                         "Chair at 11 o'clock, close")

    def test_walk_message_clock_center_ahead(self):
        person = info("person", "center", proximity="close")
        self.assertEqual(walk_message(person, use_clock=True),
                         "Person at 12 o'clock, close")

    def test_clock_is_the_default(self):
        # user decision 2026-07-14: clock bearings are the default wording
        e = GuidanceEngine("walk")
        chair = info("chair", "right", proximity="close")
        e.update([chair], 0.0)
        self.assertEqual(e.update([chair], 0.1), "Chair at 1 o'clock, close")

    def test_engine_toggle_switches_wording(self):
        e = GuidanceEngine("walk", use_clock=False)
        chair = info("chair", "right", proximity="close")
        e.update([chair], 0.0)
        self.assertEqual(e.update([chair], 0.1), "Chair on right, close")
        e.set_clock(True)
        # same obstacle, new phrasing -> not a repeat, speaks immediately
        self.assertEqual(e.update([chair], 2.0), "Chair at 1 o'clock, close")


class TestObjectMemory(unittest.TestCase):
    def test_recall_message_zone(self):
        cup = info("cup", "right", proximity="close", area=0.02)
        self.assertEqual(recall_message(cup, 5, "cup"),
                         "Cup last seen on your right, 5 seconds ago")

    def test_recall_message_clock(self):
        cup = info("cup", "left", proximity="close", area=0.02)
        self.assertEqual(recall_message(cup, 1, "cup", use_clock=True),
                         "Cup last seen at 11 o'clock, a moment ago")

    def test_recall_no_memory(self):
        self.assertEqual(recall_message(None, 0, "apple"),
                         "No memory of an apple")

    def test_engine_recall_after_object_leaves(self):
        e = GuidanceEngine("walk", use_clock=False)
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


class TestDistanceMessages(unittest.TestCase):
    # real analyze_box infos carry a metric estimate; medium/far speak meters.
    def _person_at(self, height_frac, width=0.1, cx=0.5):
        # a person box height_frac tall and `width` wide, centered at cx.
        # height drives the metric distance; area (width*height) drives bucket.
        return analyze_box("person", 0.9, cx - width / 2, 0.5 - height_frac / 2,
                           cx + width / 2, 0.5 + height_frac / 2, 1.0, 1.0)

    def test_far_person_speaks_meters(self):
        # small box -> far -> metric. 1.7 * 0.85 / 0.2 ~= 7 m
        p = self._person_at(0.2)
        self.assertEqual(p.proximity, "far")
        self.assertIn("meter", find_message(p, "person"))

    def test_near_person_keeps_bucket(self):
        # big box -> close/very close -> no meters, bucket word instead
        p = self._person_at(0.9, width=0.6)
        self.assertIn(p.proximity, ("close", "very close"))
        self.assertNotIn("meter", find_message(p, "person"))

    def test_meters_value_is_reasonable(self):
        p = self._person_at(0.2)  # ~7 m
        self.assertRegex(find_message(p, "person"), r"about \d+ meters")

    def test_meters_are_find_mode_only_not_walk(self):
        # walk stays bucket-based even for a metric-capable far/medium object
        p = self._person_at(0.2)
        self.assertNotIn("meter", walk_message(p))
        self.assertIn("far", walk_message(p))

    def test_clipped_box_suppresses_meters(self):
        # person box jammed against the bottom edge -> height untrustworthy
        p = analyze_box("person", 0.9, 0.45, 0.6, 0.55, 1.0, 1.0, 1.0)
        self.assertIsNone(p.distance_m)
        self.assertNotIn("meter", find_message(p, "person"))

    def test_low_confidence_suppresses_meters(self):
        # a low-conf class match could be a misdetection -> wrong real-height
        p = self._person_at(0.2, cx=0.5)
        low = ObjectInfo(p.name, 0.7, p.h_zone, p.v_zone, p.proximity, p.area,
                         p.center_x, p.phrase, p.distance_m)
        self.assertNotIn("meter", find_message(low, "person"))


class TestClearPath(unittest.TestCase):
    def test_open_ahead_when_obstacles_on_sides(self):
        scene = [info("chair", "left", proximity="close", area=0.2),
                 info("chair", "right", proximity="close", area=0.2)]
        self.assertEqual(clear_path(scene), "Path clear ahead")

    def test_steers_away_from_center_block(self):
        scene = [info("person", "center", proximity="very close", area=0.4),
                 info("chair", "right", proximity="close", area=0.1)]
        self.assertEqual(clear_path(scene), "Clearest on your left")

    def test_far_obstacles_ignored(self):
        scene = [info("person", "center", proximity="far", area=0.01)]
        self.assertEqual(clear_path(scene), "Path clear ahead")

    def test_near_small_hazard_beats_far_bulk(self):
        # a small CLOSE stool ahead must be avoided in favour of a bulky but
        # only-MEDIUM couch to the side — proximity rank, not summed box area
        # (area-sum would wrongly pick the center as emptiest)
        scene = [info("chair", "center", proximity="close", area=0.05),
                 info("couch", "left", proximity="medium", area=0.4),
                 info("couch", "right", proximity="medium", area=0.4)]
        self.assertEqual(clear_path(scene), "Clearest on your left")

    def test_all_blocked_says_stop(self):
        scene = [info("chair", "left", proximity="close", area=0.1),
                 info("person", "center", proximity="close", area=0.1),
                 info("chair", "right", proximity="close", area=0.1)]
        self.assertEqual(clear_path(scene), "Stop, no clear path")

    def test_door_is_not_an_obstacle_for_path(self):
        # a doorway ahead is the thing to walk THROUGH, not around
        scene = [info("door", "center", proximity="close", area=0.3)]
        self.assertEqual(clear_path(scene), "Path clear ahead")

    def test_empty_scene_is_ahead(self):
        self.assertEqual(clear_path([]), "Path clear ahead")

    def test_engine_path_stamps_clock(self):
        e = GuidanceEngine("walk")
        # left + center blocked, right open
        scene = [info("chair", "left", proximity="close", area=0.2),
                 info("person", "center", proximity="very close", area=0.4)]
        self.assertEqual(e.path(scene, 0.0), "Clearest on your right")


class TestToothbrushFindable(unittest.TestCase):
    def test_toothbrush_is_a_find_class(self):
        from position import FIND_CLASSES, TARGET_CLASSES
        self.assertIn("toothbrush", FIND_CLASSES)
        self.assertIn("toothbrush", TARGET_CLASSES)


class TestCount(unittest.TestCase):
    def test_none(self):
        self.assertEqual(count_message([], "chair"), "No chairs")

    def test_one(self):
        self.assertEqual(count_message([info("chair")], "chair"), "1 chair")

    def test_many_counts_only_target(self):
        scene = [info("chair", "left"), info("chair", "right"),
                 info("person", "center")]
        self.assertEqual(count_message(scene, "chair"), "2 chairs")

    def test_person_plural(self):
        scene = [info("person"), info("person")]
        self.assertEqual(count_message(scene, "person"), "2 people")

    def test_engine_count_stamps_clock(self):
        e = GuidanceEngine()
        self.assertEqual(e.count([info("chair"), info("chair")], "chair", 0.0),
                         "2 chairs")


class TestCheckDirection(unittest.TestCase):
    def test_empty_direction_says_nothing_there(self):
        scene = [info("chair", "right")]
        self.assertEqual(check_direction(scene, "left"), "Nothing on your left")
        self.assertEqual(check_direction(scene, "ahead"), "Nothing ahead")

    def test_reports_what_is_there_with_bucket(self):
        scene = [info("chair", "left", proximity="close")]
        self.assertEqual(check_direction(scene, "left"),
                         "A chair close on your left")

    def test_ahead_maps_to_center_zone(self):
        scene = [info("door", "center", proximity="medium")]
        self.assertEqual(check_direction(scene, "ahead"),
                         "A door medium ahead")

    def test_closest_first_and_capped_at_two(self):
        scene = [info("chair", "right", proximity="far", area=0.4),
                 info("person", "right", proximity="very close"),
                 info("bottle", "right", proximity="medium")]
        msg = check_direction(scene, "right")
        self.assertEqual(msg,
                         "A person very close on your right, "
                         "and a bottle medium")
        self.assertNotIn("chair", msg)   # the third item is dropped, not read

    def test_find_classes_are_reported_too(self):
        # unlike walk mode, a query answers about anything detected: the user
        # asked, so a cup on the table is a legitimate answer
        self.assertEqual(check_direction([info("cup", "left")], "left"),
                         "A cup close on your left")

    def test_untrusted_name_becomes_obstacle(self):
        scene = [info("toilet", "left", conf=0.65)]
        self.assertEqual(check_direction(scene, "left"),
                         "An obstacle close on your left")

    def test_unknown_direction_returns_none(self):
        self.assertIsNone(check_direction([info("chair")], "behind"))

    def test_engine_check_stamps_clock_and_passes_none_through(self):
        e = GuidanceEngine()
        self.assertEqual(e.check([info("chair", "left")], "left", 0.0),
                         "A chair close on your left")
        self.assertIsNone(e.check([info("chair")], "behind", 1.0))




class TestTrustedName(unittest.TestCase):
    """A name vouched for by the naming head must be SPOKEN, not swallowed.

    The NAME_CONFIDENCE gate replaces a class name with the generic word
    "obstacle" below 0.8. Its stated basis is falsified (EVALUATION.md 6.2:
    a dustbin called "toilet" peaks at 0.94 while a correct "chair" sits at
    0.92 — overlapping bands), so it cannot be allowed to override the one
    signal that IS calibrated: an embedding rename that beat every competing
    label by MIN_MARGIN. Before this, the app identified a wardrobe correctly
    and then announced "Obstacle on left, close".
    """

    def _chair(self, conf, trusted):
        return ObjectInfo(name="wardrobe", confidence=conf, h_zone="left",
                          v_zone="middle", proximity="close", area=0.2,
                          center_x=0.15, phrase="left", trusted_name=trusted)

    def test_untrusted_low_confidence_says_obstacle(self):
        msg = walk_message(self._chair(0.72, False))
        self.assertIn("obstacle", msg.lower())
        self.assertNotIn("wardrobe", msg.lower())

    def test_trusted_low_confidence_says_the_name(self):
        msg = walk_message(self._chair(0.72, True))
        self.assertIn("wardrobe", msg.lower())
        self.assertNotIn("obstacle", msg.lower())

    def test_trust_does_not_depend_on_confidence_at_all(self):
        """The whole point: the flag, not the number, decides the word."""
        for conf in (0.30, 0.55, 0.72, 0.99):
            self.assertIn("wardrobe",
                          walk_message(self._chair(conf, True)).lower())

    def test_high_confidence_still_speaks_without_the_flag(self):
        self.assertIn("wardrobe", walk_message(self._chair(0.95, False)).lower())

    def test_default_is_untrusted(self):
        """A caller that forgets the flag gets the old, safe behaviour."""
        info = analyze_box("wardrobe", 0.72, 0, 0, 100, 100, 1000, 1000)
        self.assertFalse(info.trusted_name)


if __name__ == "__main__":
    unittest.main()
