"""Tests for the long-term object memory.

The staleness behaviour matters most. A remembered location is a claim about
the past that the user acts on in the present, and things move; if the age is
not prominent the memory sends someone on a wasted trip with full confidence.
"""
import unittest

from object_memory import (MAX_ENTRIES, ObjectMemory, Sighting, ago_phrase,
                           recall_sentence)
from position import ObjectInfo

HOUR = 3600.0


def info(name, cx=0.5, cy=0.5, area=0.05, h_zone="center"):
    return ObjectInfo(name=name, confidence=0.9, h_zone=h_zone,
                      v_zone="middle", proximity="medium", area=area,
                      center_x=cx, phrase=h_zone, center_y=cy)


class AgoPhraseTest(unittest.TestCase):
    def test_scales_from_seconds_to_days(self):
        self.assertEqual(ago_phrase(0), "just now")
        self.assertEqual(ago_phrase(1), "just now")
        self.assertEqual(ago_phrase(20), "20 seconds ago")
        self.assertEqual(ago_phrase(60), "1 minute ago")
        self.assertEqual(ago_phrase(600), "10 minutes ago")
        self.assertEqual(ago_phrase(2 * HOUR), "about 2 hours ago")
        self.assertEqual(ago_phrase(26 * HOUR), "yesterday")
        self.assertEqual(ago_phrase(72 * HOUR), "3 days ago")

    def test_never_negative(self):
        self.assertEqual(ago_phrase(-5), "just now")

    def test_hours_are_vague_on_purpose(self):
        """Precision here would be false confidence: what the user needs is
        whether it is fresh enough to trust, not the exact minute."""
        self.assertIn("about", ago_phrase(3 * HOUR + 400))


class RememberTest(unittest.TestCase):
    def test_stores_the_biggest_sighting_of_each_class(self):
        m = ObjectMemory()
        m.remember([info("bottle", area=0.01, cx=0.2),
                    info("bottle", area=0.05, cx=0.8)], at=1000.0)
        s = m.get("bottle", 1000.0)
        self.assertAlmostEqual(s.center_x, 0.8)

    def test_records_what_the_object_was_near(self):
        """'near a table' is what makes a memory actionable an hour later —
        a frame position is meaningless once the user has moved."""
        m = ObjectMemory()
        m.remember([info("cell phone", cx=0.50, cy=0.50, area=0.01),
                    info("dining table", cx=0.55, cy=0.55, area=0.30)],
                   at=1000.0)
        self.assertIn("dining table", m.get("cell phone", 1000.0).near)

    def test_distant_objects_are_context_not_near(self):
        m = ObjectMemory()
        m.remember([info("cell phone", cx=0.1, cy=0.1, area=0.01),
                    info("bed", cx=0.9, cy=0.9, area=0.4)], at=1000.0)
        s = m.get("cell phone", 1000.0)
        self.assertEqual(s.near, ())
        self.assertIn("bed", s.context)

    def test_an_object_is_never_near_itself(self):
        m = ObjectMemory()
        m.remember([info("chair", cx=0.5, area=0.1),
                    info("chair", cx=0.52, area=0.2)], at=1000.0)
        s = m.get("chair", 1000.0)
        self.assertNotIn("chair", s.near)
        self.assertNotIn("chair", s.context)

    def test_empty_frame_changes_nothing(self):
        m = ObjectMemory()
        m.remember([info("bottle")], at=1000.0)
        m.remember([], at=2000.0)
        self.assertIsNotNone(m.get("bottle", 2000.0))


class ExpiryTest(unittest.TestCase):
    def test_remembers_for_hours_not_seconds(self):
        """The engine's own 30-second memory answers a different question.
        'Where are my keys' means hours ago."""
        m = ObjectMemory()
        m.remember([info("cell phone")], at=0.0)
        self.assertIsNotNone(m.get("cell phone", 6 * HOUR))

    def test_expires_past_the_ttl(self):
        m = ObjectMemory(ttl=HOUR)
        m.remember([info("cell phone")], at=0.0)
        self.assertIsNone(m.get("cell phone", 2 * HOUR))

    def test_capacity_is_bounded_and_drops_the_oldest(self):
        m = ObjectMemory(max_entries=3)
        for n, name in enumerate(["a", "b", "c", "d", "e"]):
            m.remember([info(name)], at=1000.0 + n)
        self.assertLessEqual(len(m.known(1010.0)), 3)
        self.assertIn("e", m.known(1010.0))
        self.assertNotIn("a", m.known(1010.0))


class SentenceTest(unittest.TestCase):
    def test_age_is_spoken_before_the_place(self):
        """The place is a claim about the past; the age is what tells the user
        how much to trust it. Buried at the end it arrives after they have
        already decided to walk somewhere."""
        s = Sighting("cell phone", "left", 0.2, 0.5, "medium",
                     near=("dining table",), at=0.0)
        out = recall_sentence(s, "cell phone", 2 * HOUR)
        self.assertLess(out.index("hours ago"), out.index("dining table"))

    def test_the_worked_example(self):
        s = Sighting("cell phone", "left", 0.2, 0.5, "medium",
                     near=("dining table",), context=("bed",), at=0.0)
        self.assertEqual(recall_sentence(s, "cell phone", 2 * HOUR),
                         "Cell phone, about 2 hours ago, near a dining table")

    def test_falls_back_to_room_context_when_nothing_was_near(self):
        s = Sighting("bottle", "left", 0.2, 0.5, "medium",
                     near=(), context=("bed", "chair"), at=0.0)
        out = recall_sentence(s, "bottle", 60.0)
        self.assertIn("in view", out)
        self.assertIn("bed", out)

    def test_says_only_the_age_when_there_is_no_context(self):
        s = Sighting("bottle", "left", 0.2, 0.5, "medium", at=0.0)
        self.assertEqual(recall_sentence(s, "bottle", 60.0),
                         "Bottle, 1 minute ago")

    def test_no_memory(self):
        self.assertEqual(recall_sentence(None, "bottle", 0.0),
                         "No memory of a bottle")
        self.assertEqual(recall_sentence(None, "umbrella", 0.0),
                         "No memory of an umbrella")

    def test_articles(self):
        s = Sighting("bottle", "left", 0.2, 0.5, "medium",
                     near=("dining table", "chair"), at=0.0)
        out = recall_sentence(s, "bottle", 10.0)
        self.assertIn("a dining table and a chair", out)


class PersistenceTest(unittest.TestCase):
    def test_round_trip(self):
        m = ObjectMemory()
        m.remember([info("cell phone", cx=0.3, cy=0.4),
                    info("dining table", cx=0.32, cy=0.42, area=0.3)],
                   at=1000.0)
        restored = ObjectMemory()
        restored.load_dict(m.to_dict())
        a, b = m.get("cell phone", 1000.0), restored.get("cell phone", 1000.0)
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_survives_a_restart_with_the_clock_intact(self):
        """Wall-clock timestamps are the whole reason this is separate from
        the engine's monotonic memory."""
        m = ObjectMemory()
        m.remember([info("cell phone")], at=1_700_000_000.0)
        restored = ObjectMemory()
        restored.load_dict(m.to_dict())
        out = restored.recall("cell phone", 1_700_000_000.0 + 2 * HOUR)
        self.assertIn("about 2 hours ago", out)

    def test_a_corrupt_file_does_not_stop_the_app(self):
        m = ObjectMemory()
        m.load_dict({"sightings": [{"nonsense": True}, None, 5]})
        m.load_dict("not a dict")
        m.load_dict({})
        self.assertEqual(m.known(0.0), [])

    def test_expired_entries_are_dropped_on_load(self):
        m = ObjectMemory(ttl=HOUR)
        m.remember([info("bottle")], at=0.0)
        restored = ObjectMemory(ttl=HOUR)
        restored.load_dict(m.to_dict(), at=5 * HOUR)
        self.assertEqual(restored.known(5 * HOUR), [])

    def test_default_capacity_is_sane(self):
        self.assertGreaterEqual(MAX_ENTRIES, 50)


if __name__ == "__main__":
    unittest.main()
