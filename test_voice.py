"""Voice command parser tests — pure logic, no microphone, no vosk."""

import unittest

from voice import grammar_phrases, parse_command


class TestParseCommand(unittest.TestCase):
    def test_walk(self):
        self.assertEqual(parse_command("walk mode"), ("walk", None))
        self.assertEqual(parse_command("walk"), ("walk", None))

    def test_find_simple(self):
        self.assertEqual(parse_command("find bottle"), ("find", "bottle"))

    def test_find_with_filler_words(self):
        self.assertEqual(parse_command("please find the bottle"),
                         ("find", "bottle"))

    def test_find_two_word_class(self):
        self.assertEqual(parse_command("find cell phone"),
                         ("find", "cell phone"))

    def test_find_synonyms_map_to_coco(self):
        self.assertEqual(parse_command("find phone"), ("find", "cell phone"))
        self.assertEqual(parse_command("find the fridge"),
                         ("find", "refrigerator"))
        self.assertEqual(parse_command("find sofa"), ("find", "couch"))
        self.assertEqual(parse_command("find table"),
                         ("find", "dining table"))

    def test_describe(self):
        self.assertEqual(parse_command("describe"), ("describe", None))
        self.assertEqual(parse_command("describe the scene"),
                         ("describe", None))

    def test_clock_and_zone_toggle(self):
        self.assertEqual(parse_command("clock mode"), ("clock", None))
        self.assertEqual(parse_command("zone mode"), ("zones", None))

    def test_recall_where_is(self):
        self.assertEqual(parse_command("where is the cup"), ("recall", "cup"))
        self.assertEqual(parse_command("where is my phone"),
                         ("recall", "cell phone"))

    def test_unknown_utterances_ignored(self):
        self.assertIsNone(parse_command("hello there"))
        self.assertIsNone(parse_command("find unicorn"))
        self.assertIsNone(parse_command("where is the unicorn"))
        self.assertIsNone(parse_command(""))

    def test_grammar_covers_all_commands(self):
        phrases = grammar_phrases()
        self.assertIn("walk mode", phrases)
        self.assertIn("find bottle", phrases)
        self.assertIn("find the fridge", phrases)
        self.assertIn("clock mode", phrases)
        self.assertIn("where is cup", phrases)
        # every grammar phrase must parse to a command (no dead phrases)
        for p in phrases:
            self.assertIsNotNone(parse_command(p), p)


if __name__ == "__main__":
    unittest.main()
