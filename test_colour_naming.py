"""Tests for colour naming and room brightness.

The abstention cases matter most: a user matching a shirt to trousers acts on
the answer and cannot check it, so a confidently wrong colour is worse than
"I can't tell".
"""
import unittest

from colour_naming import (colour_message, light_message, name_colour,
                           rgb_to_hsv)


class HsvTest(unittest.TestCase):
    def test_primaries(self):
        for rgb, hue in (((255, 0, 0), 0), ((0, 255, 0), 120),
                         ((0, 0, 255), 240)):
            h, s, v = rgb_to_hsv(*rgb)
            self.assertAlmostEqual(h, hue, places=3)
            self.assertAlmostEqual(s, 1.0, places=3)
            self.assertAlmostEqual(v, 1.0, places=3)

    def test_grey_has_no_hue_and_no_saturation(self):
        _, s, v = rgb_to_hsv(128, 128, 128)
        self.assertAlmostEqual(s, 0.0)
        self.assertAlmostEqual(v, 128 / 255, places=3)

    def test_black(self):
        h, s, v = rgb_to_hsv(0, 0, 0)
        self.assertEqual((h, s, v), (0.0, 0.0, 0.0))


class NameColourTest(unittest.TestCase):
    def test_saturated_hues(self):
        cases = {
            (230, 30, 30): "red",
            (240, 150, 20): "orange",
            (240, 230, 40): "yellow",
            (40, 190, 60): "green",
            (40, 200, 200): "turquoise",
            (40, 70, 220): "blue",
            (140, 50, 200): "purple",
            (230, 60, 170): "pink",
        }
        for rgb, want in cases.items():
            self.assertEqual(name_colour(*rgb), want, str(rgb))

    def test_greys_by_brightness(self):
        self.assertEqual(name_colour(20, 20, 22), "black")
        self.assertEqual(name_colour(90, 90, 92), "dark grey")
        self.assertEqual(name_colour(160, 160, 162), "grey")
        self.assertEqual(name_colour(240, 240, 240), "white")

    def test_brown_is_not_reported_as_orange(self):
        """A common clothing colour a pure hue lookup gets wrong -- and
        'orange trousers' vs 'brown trousers' is a different garment."""
        self.assertEqual(name_colour(110, 70, 30), "brown")
        self.assertEqual(name_colour(90, 60, 25), "brown")

    def test_dark_and_light_qualifiers(self):
        self.assertEqual(name_colour(20, 30, 70), "dark blue")
        self.assertEqual(name_colour(170, 190, 250), "light blue")

    def test_abstains_when_too_dark_to_judge(self):
        """An unlit patch and a black jumper look identical to a sensor, so
        the honest answer is that it cannot be told -- not 'black'."""
        self.assertIsNone(name_colour(6, 6, 6))
        self.assertIsNone(name_colour(0, 0, 0))

    def test_abstains_on_a_blown_highlight(self):
        """Overexposure is not evidence of a white object."""
        self.assertIsNone(name_colour(253, 253, 254))

    def test_a_dark_but_readable_patch_is_still_named(self):
        """Abstention must not swallow genuinely dark colours."""
        self.assertEqual(name_colour(25, 25, 26), "black")


class MessageTest(unittest.TestCase):
    def test_capitalised_for_speech(self):
        self.assertEqual(colour_message(40, 70, 220), "Blue")
        self.assertEqual(colour_message(20, 30, 70), "Dark blue")

    def test_abstention_says_what_to_do_about_it(self):
        msg = colour_message(3, 3, 3)
        self.assertIn("can't tell", msg)
        self.assertIn("light", msg.lower())


class LightTest(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(light_message(0.02), "It's dark here")
        self.assertEqual(light_message(0.15), "It's dim here")
        self.assertEqual(light_message(0.40), "It's bright here")
        self.assertEqual(light_message(0.90), "It's very bright here")

    def test_never_claims_to_know_about_a_switch(self):
        """The camera cannot tell a bulb from a window, so no message may
        assert that a light is on or off."""
        for luma in (0.0, 0.1, 0.3, 0.5, 0.8, 1.0):
            msg = light_message(luma).lower()
            self.assertNotIn("light is on", msg)
            self.assertNotIn("light is off", msg)
            self.assertNotIn("switch", msg)

    def test_monotonic(self):
        order = ["It's dark here", "It's dim here", "It's bright here",
                 "It's very bright here"]
        seen = [light_message(x / 20) for x in range(21)]
        idx = [order.index(m) for m in seen]
        self.assertEqual(idx, sorted(idx), "brightness bands must not go back")


if __name__ == "__main__":
    unittest.main()
