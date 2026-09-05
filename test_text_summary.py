"""Tests for document summarising.

The figure check is the whole safety story: a summary of a bill or a medical
letter that invents an amount or a date is not a quality problem.
"""
import unittest

from text_summary import (FULL_TEXT_OFFER, MAX_CHARS, MIN_SOURCE_CHARS,
                          clean_reply, render_prompt, summarise,
                          trim_to_sentence,
                          verify_summary)

LETTER = (
    "Barclays Bank PLC. Account 40276639. Dear Mr Sharma, your account ended "
    "the period 14 March with an unarranged overdraft of 240 pounds. A fee of "
    "15 pounds has been applied. Please transfer funds by 28 March to avoid "
    "further charges. If you are experiencing financial difficulty please "
    "contact us on the number on the back of your card."
)


class VerifyTest(unittest.TestCase):
    def test_accepts_a_summary_using_the_page_s_own_figures(self):
        self.assertTrue(verify_summary(
            "A letter from Barclays about a 240 pound overdraft, with a 15 "
            "pound fee, asking you to pay by 28 March.", LETTER))

    def test_rejects_an_invented_amount(self):
        """The failure with real consequences."""
        self.assertFalse(verify_summary(
            "A letter from Barclays about a 340 pound overdraft.", LETTER))

    def test_rejects_an_invented_date(self):
        self.assertFalse(verify_summary(
            "Barclays want payment by 30 April.", LETTER))

    def test_rejects_a_spelled_out_invented_figure(self):
        """'three hundred pounds' is a claim without a digit in it."""
        self.assertFalse(verify_summary(
            "Barclays say you owe three hundred pounds.", LETTER))

    def test_accepts_a_summary_with_no_figures_at_all(self):
        self.assertTrue(verify_summary(
            "A letter from your bank about an overdraft, asking you to "
            "transfer funds.", LETTER))

    def test_length_is_trimmed_rather_than_rejected(self):
        """A wordy summary is not a false one.

        Rejecting on length threw away truthful summaries: a live llama3.2:3b
        summary of a prescription was refused for it, and the reply contained
        no figures at all. Verbosity is handled by trimming, which is what
        agent.clean_say already does for chat replies.
        """
        self.assertTrue(verify_summary("word " * 200, LETTER))
        self.assertLess(MAX_CHARS, 1000)

    def test_trim_cuts_at_a_sentence(self):
        long = ("A letter from your bank about an overdraft. " * 20)
        out = trim_to_sentence(long)
        self.assertLessEqual(len(out), MAX_CHARS)
        self.assertTrue(out.endswith("."), out[-40:])

    def test_trim_leaves_a_short_summary_alone(self):
        short = "A letter from your bank."
        self.assertEqual(trim_to_sentence(short), short)

    def test_a_wordy_reply_still_reaches_the_user(self):
        wordy = ("This document is a prescription for a patient and it "
                 "contains instructions about taking medication. " * 6)
        msg, how = summarise(LETTER, llm=lambda _: wordy)
        self.assertEqual(how, "model")
        self.assertLessEqual(len(msg), MAX_CHARS + len(FULL_TEXT_OFFER) + 2)

    def test_rejects_empty(self):
        for bad in ("", "   ", None):
            self.assertFalse(verify_summary(bad, LETTER))


class CleanReplyTest(unittest.TestCase):
    """Artifacts that are not FALSE, so verification will never catch them,
    and that a blind user should still not have read to them."""

    def test_strips_the_models_note_to_itself(self):
        # llama3.2:3b really ended a prescription summary this way
        out = clean_reply("This is a prescription. It has instructions. "
                          "(Note: I have followed the rules provided.)")
        self.assertNotIn("Note", out)
        self.assertIn("prescription", out)

    def test_drops_a_restatement_that_says_nothing_new(self):
        # small models merge their earlier sentences and add a conjunction,
        # so the test is content overlap rather than equality
        out = clean_reply(
            "This document is a prescription for a patient. It contains "
            "instructions. The document is a prescription for a patient, and "
            "it contains instructions.")
        self.assertEqual(out.count("prescription"), 1)

    def test_keeps_genuinely_new_sentences(self):
        text = ("A letter from Barclays about an overdraft. It asks you to "
                "transfer funds by 28 March.")
        self.assertEqual(clean_reply(text), text)

    def test_handles_empty(self):
        self.assertEqual(clean_reply(""), "")
        self.assertEqual(clean_reply(None), "")


class SummariseTest(unittest.TestCase):
    def test_too_little_text_is_not_summarised(self):
        """Asking a model to summarise three words is how you get a confident
        paragraph about a menu heading."""
        msg, how = summarise("Exit", llm=lambda _: "A detailed report.")
        self.assertEqual(how, "too_short")
        self.assertIn("not enough text", msg)
        self.assertGreater(MIN_SOURCE_CHARS, 20)

    def test_no_model_says_so_and_points_at_read(self):
        msg, how = summarise(LETTER, llm=None)
        self.assertEqual(how, "no_model")
        self.assertIn("read", msg.lower())

    def test_a_good_summary_is_spoken_with_the_full_text_offer(self):
        good = "A letter from Barclays about a 240 pound overdraft."
        msg, how = summarise(LETTER, llm=lambda _: good)
        self.assertEqual(how, "model")
        self.assertIn(good, msg)
        self.assertIn(FULL_TEXT_OFFER, msg)

    def test_an_invented_figure_is_refused_not_spoken(self):
        msg, how = summarise(
            LETTER, llm=lambda _: "Barclays want 999 pounds by 30 April.")
        self.assertEqual(how, "rejected")
        self.assertNotIn("999", msg)
        self.assertIn("read", msg.lower())

    def test_a_model_that_raises_degrades_to_read(self):
        def boom(_):
            raise RuntimeError("ollama down")
        msg, how = summarise(LETTER, llm=boom)
        self.assertEqual(how, "failed")
        self.assertIn("read", msg.lower())

    def test_a_model_that_returns_junk_degrades(self):
        for junk in (None, 7, ["a"]):
            _, how = summarise(LETTER, llm=lambda _, j=junk: j)
            self.assertEqual(how, "failed")

    def test_whitespace_and_quotes_are_normalised(self):
        noisy = '  "A letter\n\nfrom your bank about an overdraft."  '
        msg, how = summarise(LETTER, llm=lambda _: noisy)
        self.assertEqual(how, "model")
        self.assertNotIn("\n", msg)
        self.assertFalse(msg.startswith('"'))

    def test_the_user_is_always_offered_the_page_itself(self):
        """A summary is a triage aid, never a substitute: whatever happens, the
        user must be told the full text is available."""
        for llm in (None,
                    lambda _: "A letter from your bank.",
                    lambda _: "You owe 999 pounds.",
                    lambda _: None):
            msg, _ = summarise(LETTER, llm=llm)
            self.assertIn("read", msg.lower(), msg)


class PromptTest(unittest.TestCase):
    def test_carries_the_text(self):
        self.assertIn("Barclays", render_prompt(LETTER))

    def test_truncates_a_huge_page(self):
        p = render_prompt("x" * 50_000, max_source=100)
        self.assertLess(len(p), 1000)


if __name__ == "__main__":
    unittest.main()
