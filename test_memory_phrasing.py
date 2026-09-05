"""Tests for verified memory phrasing.

The design claim is that the model can only ever improve the sentence, never
change what is claimed. These tests are what makes that true rather than
aspirational: every way a model can smuggle a new fact into a sentence has to
end up back at the deterministic fallback.
"""
import unittest

from memory_phrasing import (MAX_CHARS, build_record, phrase_memory,
                             render_prompt, verify_sentence)

RECORD = build_record(
    "cell phone",
    {"near": ["dining table"], "context": ["bed", "chair"]},
    "about 2 hours ago",
    "Cell phone, about 2 hours ago, near a dining table",
)


class VerifyTest(unittest.TestCase):
    def test_accepts_a_faithful_rephrasing(self):
        self.assertTrue(verify_sentence(
            "The last time I saw your cell phone it was beside the dining "
            "table, about 2 hours ago.", RECORD))

    def test_rejects_upgrading_room_context_into_proximity(self):
        """The failure a live model actually produced, twice.

        For a record whose `near` was empty and whose `context` held a bed,
        llama3.2 wrote "Your backpack was beside the bed" -- turning "also in
        the room" into "beside". An earlier verifier accepted it because `bed`
        appeared somewhere in the record: it checked the nouns, not the
        relationship. `context` is now withheld from the model entirely, so
        naming one is proof the sentence was invented.
        """
        self.assertFalse(verify_sentence(
            "Your cell phone was near the dining table, with the bed in "
            "view, about 2 hours ago.", RECORD))

    def test_the_exact_sentences_the_models_produced(self):
        empty_near = build_record(
            "backpack", {"near": [], "context": ["bed", "wardrobe"]},
            "yesterday", "Backpack, yesterday, with a bed in view")
        for bad in ("I was holding my backpack beside the bed yesterday.",
                    "Your backpack was beside the bed, in the room, yesterday."):
            self.assertFalse(verify_sentence(bad, empty_near), bad)

    def test_a_record_with_nothing_beside_it_never_reaches_the_model(self):
        """There is no place to phrase, only an age, and the template already
        says that perfectly -- so the model is not asked, and cannot invent."""
        empty_near = build_record(
            "backpack", {"near": [], "context": ["bed"]},
            "yesterday", "Backpack, yesterday, with a bed in view")
        called = []

        def llm(_):
            called.append(1)
            return "Your backpack was beside the bed."

        text, how = phrase_memory(empty_near, llm=llm)
        self.assertEqual(called, [], "the model must not be consulted")
        self.assertEqual(how, "template")
        self.assertEqual(text, empty_near["fallback"])

    def test_rejects_an_object_that_was_never_there(self):
        """The failure that matters: a plausible sentence about a thing the
        camera never saw."""
        self.assertFalse(verify_sentence(
            "Your cell phone was on the couch, about 2 hours ago.", RECORD))
        self.assertFalse(verify_sentence(
            "Your cell phone was near the sink.", RECORD))

    def test_rejects_an_invented_number(self):
        self.assertFalse(verify_sentence(
            "Your cell phone was there about 5 hours ago.", RECORD))

    def test_rejects_an_invented_number_word(self):
        """'three hours ago' is a claim even without a digit in it."""
        self.assertFalse(verify_sentence(
            "I saw your cell phone near the dining table three hours ago.",
            RECORD))

    def test_accepts_the_right_number_spelled_out(self):
        """Numbers are compared by VALUE, not spelling.

        The age phrase is composed as "about 2 hours ago"; a model writing
        "about two hours ago" has restated the same fact in the form a spoken
        interface should use. An earlier version rejected it as invented, and
        that false rejection was the commonest outcome in the first live run
        against llama3.2 -- three of four rejections.
        """
        self.assertTrue(verify_sentence(
            "Your cell phone was beside the dining table about two hours ago.",
            RECORD))

    def test_accepts_a_number_that_came_from_the_age_phrase(self):
        self.assertTrue(verify_sentence(
            "Your cell phone, about 2 hours ago, by the dining table.",
            RECORD))

    def test_rejects_a_speech(self):
        long = ("Your cell phone was near the dining table and I want to "
                "reassure you that everything is fine and you should not "
                "worry about it at all because it is definitely still there.")
        self.assertGreater(len(long), MAX_CHARS)
        self.assertFalse(verify_sentence(long, RECORD))

    def test_rejects_empty(self):
        for bad in ("", "   ", None):
            self.assertFalse(verify_sentence(bad, RECORD))

    def test_a_record_with_no_context_permits_no_objects_but_its_own(self):
        bare = build_record("bottle", {}, "1 minute ago", "Bottle, 1 minute ago")
        self.assertTrue(verify_sentence("I saw your bottle 1 minute ago.", bare))
        self.assertFalse(verify_sentence(
            "Your bottle was near the chair.", bare))


class PhraseTest(unittest.TestCase):
    def test_no_model_is_the_old_behaviour_exactly(self):
        text, how = phrase_memory(RECORD, llm=None)
        self.assertEqual(text, RECORD["fallback"])
        self.assertEqual(how, "template")

    def test_a_good_model_reply_is_used(self):
        good = "I last saw your cell phone by the dining table, about 2 hours ago."
        text, how = phrase_memory(RECORD, llm=lambda _: good)
        self.assertEqual(text, good)
        self.assertEqual(how, "model")

    def test_a_hallucinated_reply_falls_back(self):
        text, how = phrase_memory(
            RECORD, llm=lambda _: "Your cell phone is on the couch in the hall.")
        self.assertEqual(text, RECORD["fallback"])
        self.assertEqual(how, "rejected")

    def test_a_model_that_raises_falls_back(self):
        def boom(_):
            raise RuntimeError("ollama is down")
        text, how = phrase_memory(RECORD, llm=boom)
        self.assertEqual(text, RECORD["fallback"])
        self.assertEqual(how, "template")

    def test_a_model_that_returns_junk_falls_back(self):
        for junk in (None, 42, {"tool": "find"}):
            text, how = phrase_memory(RECORD, llm=lambda _, j=junk: j)
            self.assertEqual(text, RECORD["fallback"])

    def test_only_the_first_line_is_taken(self):
        chatty = ('I last saw your cell phone by the dining table, 2 hours ago.\n'
                  'Would you like me to help with anything else?')
        text, how = phrase_memory(RECORD, llm=lambda _: chatty)
        self.assertEqual(how, "model")
        self.assertNotIn("anything else", text)

    def test_surrounding_quotes_are_stripped(self):
        quoted = '"Your cell phone was by the dining table, about 2 hours ago."'
        text, how = phrase_memory(RECORD, llm=lambda _: quoted)
        self.assertEqual(how, "model")
        self.assertFalse(text.startswith('"'))

    def test_the_model_can_never_make_the_answer_worse(self):
        """The design claim, stated as a test: whatever the model returns, the
        user hears either a verified sentence or the correct template."""
        replies = ["", "?!", "The couch, obviously.", "x" * 500,
                   "Your cell phone was near the dining table just now.",
                   "I saw it 47 minutes ago near the bed."]
        for r in replies:
            text, _ = phrase_memory(RECORD, llm=lambda _, rr=r: rr)
            self.assertTrue(text == RECORD["fallback"]
                            or verify_sentence(text, RECORD),
                            "unverified text reached the user: %r" % text)


class PromptTest(unittest.TestCase):
    def test_prompt_carries_only_the_record(self):
        p = render_prompt(RECORD)
        self.assertIn("cell phone", p)
        self.assertIn("dining table", p)
        self.assertIn("about 2 hours ago", p)

    def test_empty_fields_do_not_render_as_nothing(self):
        bare = build_record("bottle", {}, "just now", "Bottle, just now")
        self.assertIn("nothing recorded", render_prompt(bare))


if __name__ == "__main__":
    unittest.main()
