"""Voice command parser tests — pure logic, no microphone, no vosk."""

import unittest

import voice
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

    def test_left_and_right_need_a_positional_lead_in(self):
        # found by the 2026-08-01 eval run, not by hand: "left" is an ordinary
        # English word and was turning an out-of-scope utterance into a query
        self.assertIsNone(parse_command("how much battery is left"))
        self.assertIsNone(parse_command("turn left at the corner"))
        # ...while "ahead"/"front"/"forward" have no non-spatial reading here
        self.assertEqual(parse_command("is anything ahead"), ("check", "ahead"))

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



class PhotoCommandTest(unittest.TestCase):
    """"take a picture" — the photo goes to the phone GALLERY, because the
    user cannot review it and the point is handing it to a sighted person."""

    def test_the_spoken_forms_parse(self):
        for text in ("take a picture", "take a photo", "photo",
                     "please take a picture"):
            self.assertEqual(parse_command(text), ("photo", None), text)

    def test_it_does_not_steal_an_object_query(self):
        # "picture" is checked before find/count, so a stray class word later
        # in the utterance must not drag it away — but a real find still wins
        self.assertEqual(parse_command("find the bottle"), ("find", "bottle"))
        self.assertEqual(parse_command("take a picture of the chair"),
                         ("photo", None))

    def test_read_still_wins_over_photo(self):
        # OCR is checked first: "read the text in the picture" is a read
        self.assertEqual(parse_command("read the text in the picture"),
                         ("read", None))

if __name__ == "__main__":
    unittest.main()


class GrammarForcedNoiseTest(unittest.TestCase):
    """From the 2026-09-07 field log. Every utterance here was produced by the
    recognizer from sound the user did not intend as a command, and every one
    arrived with ZERO `[unk]` tokens — words forced onto the grammar are not
    unplaceable, so the unknown-ratio floor cannot see them. One of them
    ("cupboard find dustbin") started a search for an object nobody named,
    which is the "why does it randomly find something" report."""

    FIELD_NOISE = (
        "cupboard find dustbin",
        "find dustbin toilets",
        "mobile photo person on anything on my left dining the",
    )

    def test_field_noise_is_rejected(self):
        for text in self.FIELD_NOISE:
            self.assertTrue(voice.names_multiple_objects(text), text)

    def test_real_requests_survive(self):
        for text in ("find the door", "find the cell phone", "how many chairs",
                     "find the door on my left", "where is the cup",
                     "take a photo of the chair", "what colour is this",
                     "is there anything in front of me"):
            self.assertFalse(voice.names_multiple_objects(text), text)

    def test_whole_words_only(self):
        """Substring matching looks equivalent and is not: "how many chairs"
        contains "man" and "cupboard" contains "cup", so a naive `in` test
        rejects ordinary single-object requests as noise."""
        self.assertEqual(voice.named_classes("how many chairs"), {"chair"})
        self.assertNotIn("cup", voice.named_classes("cupboard"))

    def test_find_takes_the_first_object_named(self):
        """"find dustbin toilets" resolved to `toilet` under longest-anywhere:
        neither what was said nor the first thing the sentence names."""
        self.assertEqual(voice.parse_command("find dustbin toilets"),
                         ("find", "dustbin"))
        self.assertEqual(voice.parse_command("find bottle chair"),
                         ("find", "bottle"))
        # length still breaks ties at the same position
        self.assertEqual(voice.parse_command("find the cell phone"),
                         ("find", "cell phone"))


class OneRequestFloorTest(unittest.TestCase):
    """The second half of the 2026-09-07 log, after the multi-object floor
    landed. Every utterance below was still accepted and RAN something the user
    had not asked for. All of them are grammar-forced noise with zero
    unplaceable tokens: the recognizer is certain about every word."""

    FIELD_NOISE = (
        ("describe light left", "describe"),
        ("the clock summary", "describe"),
        ("the clock mans light left", "clock"),
        ("the many where of me is there read walk", "read"),
        ("cupboard find dustbin", "find"),
        ("do laptops ahead laptop on my left bottle on here right", None),
        ("scene mobile is toilet window", "describe"),
        ("clock many toilet door toilet summarize", "clock"),
    )

    def test_field_noise_is_rejected(self):
        for text, _ in self.FIELD_NOISE:
            self.assertFalse(voice.looks_like_one_request(text), text)

    def test_real_requests_survive(self):
        for text in ("find the door", "how many chairs", "what is on my left",
                     "is there anything in front of me", "take a photo",
                     "read text", "summarise this", "what colour is this",
                     "is the light on", "clear path", "walk mode",
                     "say again", "sonar off", "what can you do",
                     "where is the cup", "find the door on my left",
                     "mute it", "on summarize"):
            self.assertTrue(voice.looks_like_one_request(text), text)

    def test_the_dictation_trigger_may_carry_a_request(self):
        """"assistant find the door" is a trigger plus a request BY DESIGN
        (voice.py parses the trigger LAST so no command loses precedence).
        Counting the trigger as a capability would reject the documented
        form."""
        self.assertTrue(voice.looks_like_one_request("assistant find the door"))
        self.assertEqual(voice.parse_command("assistant find the door"),
                         ("find", "door"))

    def test_a_direction_is_not_a_second_capability(self):
        """"left" is only a capability with a question word in front of it."""
        self.assertEqual(voice.named_capabilities("find the door on my left"),
                         {"find"})


class VocabularyTest(unittest.TestCase):
    """Every grammar phrase must be one the shipped model can actually hear.

    Vosk drops a word it has no pronunciation for and logs a warning nobody
    reads, so the phrase is not misheard — it is unhearable, exactly like one
    that was never added. That cost the user a walk: "unmute" is OOV in
    vosk-model-small-en-us-0.15, so on 2026-09-07 the app muted on request and
    had no spoken way back, and every command after that ran silently.

    Skipped where vosk or the model is not present, because the unit suite must
    run without them; it is the desktop check that keeps the list honest.
    """

    def test_no_grammar_word_is_out_of_vocabulary(self):
        import json
        import os
        import subprocess
        import sys
        model = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "vosk-model-small-en-us-0.15")
        if not os.path.isdir(model):
            self.skipTest("vosk model not present")
        try:
            import vosk  # noqa: F401
        except ImportError:
            self.skipTest("vosk not installed")
        import agent
        # A SUBPROCESS because the warning is written by the C library to the
        # process's stderr, which cannot be captured from inside Python.
        script = (
            "import json, sys;"
            f"sys.path.insert(0, {os.path.dirname(os.path.abspath(__file__))!r});"
            "import agent;"
            "from vosk import KaldiRecognizer, Model, SetLogLevel;"
            "SetLogLevel(-1);"
            f"m = Model({model!r});"
            "KaldiRecognizer(m, 16000,"
            " json.dumps(agent.grammar_phrases() + ['[unk]']))")
        out = subprocess.run([sys.executable, "-c", script],
                             capture_output=True, text=True, timeout=300)
        missing = sorted({line.rsplit("'", 2)[-2] for line in
                          out.stderr.splitlines()
                          if "missing in vocabulary" in line})
        self.assertEqual(missing, [], f"unhearable grammar words: {missing}")
        self.assertTrue(agent.grammar_phrases())

    def test_there_is_a_spoken_way_back_from_mute(self):
        """Muting by voice and un-muting by voice must both work, or the app
        can be silenced into a state the user cannot talk it out of."""
        self.assertEqual(parse_command("mute"), ("mute", "on"))
        grammar = set(grammar_phrases())
        back = [p for p in grammar if parse_command(p) == ("mute", "off")]
        self.assertTrue(back, "no hearable phrase un-mutes the app")
