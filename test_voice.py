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

    def test_clear_path_finder(self):
        self.assertEqual(parse_command("clear path"), ("path", None))
        self.assertEqual(parse_command("which way"), ("path", None))

    def test_count_query(self):
        self.assertEqual(parse_command("how many chairs"), ("count", "chair"))
        self.assertEqual(parse_command("how many bottles are there"),
                         ("count", "bottle"))

    def test_read_ocr(self):
        self.assertEqual(parse_command("read"), ("read", None))
        self.assertEqual(parse_command("read text"), ("read", None))

    def test_recall_where_is(self):
        self.assertEqual(parse_command("where is the cup"), ("recall", "cup"))
        self.assertEqual(parse_command("where is my phone"),
                         ("recall", "cell phone"))

    def test_stop_and_repeat(self):
        self.assertEqual(parse_command("stop"), ("stop", None))
        self.assertEqual(parse_command("repeat"), ("repeat", None))
        self.assertEqual(parse_command("say again"), ("repeat", None))

    def test_sonar_toggle(self):
        self.assertEqual(parse_command("sonar"), ("sonar", None))
        self.assertEqual(parse_command("sonar on"), ("sonar", "on"))
        self.assertEqual(parse_command("turn sonar off"), ("sonar", "off"))

    def test_mute_unmute(self):
        self.assertEqual(parse_command("mute"), ("mute", "on"))
        self.assertEqual(parse_command("unmute"), ("mute", "off"))

    def test_plurals(self):
        # "how many chairs" is what people actually say
        self.assertEqual(parse_command("how many chairs"), ("count", "chair"))
        self.assertEqual(parse_command("how many people"), ("count", "person"))
        self.assertEqual(parse_command("how many couches"),
                         ("count", "couch"))
        self.assertEqual(parse_command("find bottles"), ("find", "bottle"))

    def test_direction_queries(self):
        for text in ("is there anything in front of me", "what is ahead",
                     "anything in front of me", "check ahead"):
            self.assertEqual(parse_command(text), ("check", "ahead"), text)
        self.assertEqual(parse_command("what is on my left"),
                         ("check", "left"))
        self.assertEqual(parse_command("is there anything on my right"),
                         ("check", "right"))

    def test_direction_never_steals_an_existing_command(self):
        # a direction word inside another command must not become a query
        self.assertEqual(parse_command("find the door on my left"),
                         ("find", "door"))
        self.assertEqual(parse_command("where is the cup on my right"),
                         ("recall", "cup"))
        self.assertEqual(parse_command("which way is clear"), ("path", None))
        # a bare direction with no question word is not a query either
        self.assertIsNone(parse_command("left"))

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
