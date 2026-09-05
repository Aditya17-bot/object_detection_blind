"""Tests for speech_policy.py — focus arbitration and the input floor.

Every case here is a thing that actually happened on the 2026-08-02 field walk
or a rule stated in the module docstring. Pure numbers: no audio, no TTS.
"""
import unittest

from speech_policy import (CONFIRM, INFORMATIONAL, RESPONSE, ROUTINE, SAFETY,
                           STEERING, SpeechPolicy, is_plausible_request)


class FocusTest(unittest.TestCase):
    def setUp(self):
        self.p = SpeechPolicy(focus_seconds=6.0)

    def test_nothing_is_gated_when_no_task_holds_focus(self):
        for action in list(STEERING) + list(INFORMATIONAL):
            self.assertTrue(self.p.allow_command(action, 0.0))
        for pri in (ROUTINE, CONFIRM, RESPONSE, SAFETY):
            self.assertTrue(self.p.allow_speech(pri, "anything", 0.0))

    def test_the_reported_bug_an_unrequested_readout_during_a_find(self):
        """user: 'find the bottle' -> app: 'Nothing on your right'."""
        self.p.begin("find:bottle", 0.0)
        self.assertFalse(self.p.allow_command("check", 1.0))
        self.assertFalse(self.p.allow_speech(RESPONSE, "check", 1.0,
                                             solicited=False))

    def test_routine_walk_chatter_waits_for_the_task_the_user_asked_for(self):
        self.p.begin("describe", 0.0, seconds=6.0)
        self.assertFalse(self.p.allow_speech(ROUTINE, "walk", 1.0))

    def test_safety_is_never_gated(self):
        self.p.begin("read", 0.0)
        self.assertTrue(self.p.allow_speech(SAFETY, "walk", 1.0))
        self.assertTrue(self.p.allow_speech(SAFETY, "link", 1.0,
                                            solicited=False))

    def test_the_focused_task_may_keep_talking(self):
        self.p.begin("find:bottle", 0.0)
        self.assertTrue(self.p.allow_speech(RESPONSE, "find:bottle", 1.0))
        self.assertTrue(self.p.allow_command("find", 1.0))

    def test_a_user_may_always_steer_out_of_a_task(self):
        # being unable to interrupt is how an assistive device becomes
        # frightening — mode changes, stop and mute must never be swallowed
        self.p.begin("find:bottle", 0.0)
        for action in ("walk", "stop", "mute", "sonar", "repeat", "ask"):
            self.assertTrue(self.p.allow_command(action, 1.0, solicited=True),
                            action)

    def test_but_a_GUESSED_steering_command_does_not_interrupt(self):
        # unsolicited = the parser failed and the router guessed; a guess must
        # not be able to change mode mid-task
        self.p.begin("find:bottle", 0.0)
        for action in ("walk", "stop", "mute"):
            self.assertFalse(self.p.allow_command(action, 1.0,
                                                  solicited=False), action)

    def test_a_deliberate_request_takes_the_channel_over(self):
        self.p.begin("find:bottle", 0.0)
        self.assertTrue(self.p.allow_speech(RESPONSE, "describe", 1.0,
                                            solicited=True))

    def test_focus_expires_so_a_missed_release_is_not_permanent_silence(self):
        self.p.begin("describe", 0.0, seconds=6.0)
        self.assertFalse(self.p.allow_speech(ROUTINE, "walk", 5.9))
        self.assertTrue(self.p.allow_speech(ROUTINE, "walk", 6.1))

    def test_an_open_ended_hold_is_still_capped(self):
        p = SpeechPolicy(max_hold_seconds=90.0)
        p.begin("find:bottle", 0.0)          # seconds=None -> open ended
        self.assertTrue(p.focused(89.0))
        self.assertFalse(p.focused(91.0))

    def test_an_explicit_span_longer_than_the_cap_is_clamped(self):
        p = SpeechPolicy(max_hold_seconds=90.0)
        p.begin("read", 0.0, seconds=1000.0)
        self.assertFalse(p.focused(91.0))

    def test_extend_covers_the_time_a_sentence_takes_to_say(self):
        # the find bug: the engine auto-returns to walk the instant it
        # announces the target, so the channel went free before the user had
        # heard the answer and the next warning cut it off mid-word
        self.p.begin("find:bottle", 0.0, seconds=0.1)
        self.p.extend("find:bottle", 0.0, 3.0)
        self.assertFalse(self.p.allow_speech(ROUTINE, "walk", 2.0))
        self.assertTrue(self.p.allow_speech(ROUTINE, "walk", 3.5))

    def test_extend_never_shortens_an_existing_hold(self):
        self.p.begin("find:bottle", 0.0)           # open ended, 90 s
        self.p.extend("find:bottle", 0.0, 3.0)
        self.assertTrue(self.p.focused(50.0))

    def test_a_finished_task_cannot_extend_its_successors_hold(self):
        self.p.begin("describe", 0.0, seconds=6.0)
        self.p.begin("find:bottle", 1.0, seconds=2.0)
        self.p.extend("describe", 1.0, 60.0)       # late, wrong tag: no-op
        self.assertFalse(self.p.focused(4.0))

    def test_end_releases_the_channel(self):
        self.p.begin("find:bottle", 0.0)
        self.p.end("find:bottle", 1.0)
        self.assertTrue(self.p.allow_command("check", 1.0))
        self.assertIsNone(self.p.active_tag(1.0))

    def test_a_late_release_cannot_cancel_the_task_that_replaced_it(self):
        self.p.begin("describe", 0.0, seconds=6.0)
        self.p.begin("find:bottle", 1.0)
        self.p.end("describe", 2.0)          # describe finished late
        self.assertEqual(self.p.active_tag(2.0), "find:bottle")

    def test_two_finds_for_different_objects_are_different_tasks(self):
        self.p.begin("find:bottle", 0.0)
        self.p.end("find:cup", 1.0)          # wrong target: no-op
        self.assertEqual(self.p.active_tag(1.0), "find:bottle")

    def test_the_action_matches_its_tag_even_with_an_argument(self):
        # 'find:bottle' holds focus; a second 'find' is the same task type and
        # must not be blocked by its own hold
        self.p.begin("find:bottle", 0.0)
        self.assertTrue(self.p.allow_command("find", 1.0, solicited=False))

    def test_active_tag_is_none_once_focus_has_expired(self):
        self.p.begin("describe", 0.0, seconds=2.0)
        self.assertEqual(self.p.active_tag(1.0), "describe")
        self.assertIsNone(self.p.active_tag(3.0))


class PlausibleRequestTest(unittest.TestCase):
    """The floor before the dialogue layer is consulted.

    The recognizer is grammar-constrained, so it emits its best match over the
    trained phrases for ANY audio. Word-soup made of glue words is what a
    passing conversation sounds like after being force-matched — not a request.
    """

    CLASSES = ("bottle", "door", "chair", "dustbin")

    def plausible(self, text):
        return is_plausible_request(text, self.CLASSES)

    def test_real_paraphrases_pass(self):
        for text in ("show me the door", "is the bottle near me",
                     "how far is the chair", "anything on my left"):
            self.assertTrue(self.plausible(text), text)

    def test_glue_word_soup_is_rejected(self):
        for text in ("the is my on", "a to the", "on my the it"):
            self.assertFalse(self.plausible(text), text)

    def test_a_single_token_is_never_a_request(self):
        self.assertFalse(self.plausible("bottle"))
        self.assertFalse(self.plausible("find"))

    def test_empty_and_none_are_rejected(self):
        self.assertFalse(is_plausible_request("", self.CLASSES))
        self.assertFalse(is_plausible_request(None, self.CLASSES))

    def test_class_names_are_injected_not_imported(self):
        # position.py is not a dependency of this module; the caller decides
        # what its object vocabulary is
        self.assertFalse(is_plausible_request("the wardrobe there", ()))
        self.assertTrue(is_plausible_request("the wardrobe there",
                                             ("wardrobe",)))

    def test_case_is_ignored_on_both_sides(self):
        self.assertTrue(is_plausible_request("Find The BOTTLE", ("Bottle",)))


if __name__ == "__main__":
    unittest.main()
