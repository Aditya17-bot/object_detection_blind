"""Chunking and resumption of spoken read-outs.

The behaviour under test is the one the user reported missing on 2026-09-08: a
read-out interrupted by a safety warning has to come BACK, and come back at a
sentence boundary rather than wherever the interruption happened to land.

Mirrored 1:1 by blindassist_app/test/speech_queue_test.dart.
"""

import unittest

from speech_queue import SpeechQueue, split_for_speech


class SplitTest(unittest.TestCase):
    def test_splits_at_sentence_boundaries_keeping_the_terminator(self):
        self.assertEqual(
            split_for_speech(
                "Your account is overdrawn. Contact the bank. Thanks."),
            ["Your account is overdrawn.", "Contact the bank.", "Thanks."])

    def test_short_message_stays_one_chunk(self):
        self.assertEqual(split_for_speech("Bottle on your right, close"),
                         ["Bottle on your right, close"])

    def test_empty_and_whitespace_produce_no_chunks(self):
        self.assertEqual(split_for_speech(""), [])
        self.assertEqual(split_for_speech("   "), [])
        self.assertEqual(split_for_speech(None), [])

    def test_long_sentence_splits_at_clauses_and_loses_nothing(self):
        long = ("The notice says the meeting has moved to the second floor, "
                "that attendance is required for all students on the course, "
                "and that the room will be open from nine in the morning.")
        chunks = split_for_speech(long, max_chars=80)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 80)
        self.assertEqual(" ".join(chunks).split(), long.split())

    def test_never_splits_mid_word(self):
        chunks = split_for_speech("a" * 40 + " " + "b" * 40, max_chars=30)
        self.assertEqual(chunks, ["a" * 40, "b" * 40])


class QueueTest(unittest.TestCase):
    def test_hands_out_chunks_in_order_then_reports_empty(self):
        q = SpeechQueue()
        self.assertEqual(q.load("One. Two. Three."), 3)
        self.assertEqual(q.take(), "One.")
        self.assertEqual(q.take(), "Two.")
        self.assertEqual(q.remaining, 1)
        self.assertEqual(q.take(), "Three.")
        self.assertFalse(q.has_more)
        self.assertIsNone(q.take())

    def test_rewind_repeats_the_interrupted_chunk(self):
        q = SpeechQueue()
        q.load("One. Two. Three.")
        self.assertEqual(q.take(), "One.")
        self.assertEqual(q.take(), "Two.")  # safety cuts in here
        q.rewind()
        self.assertEqual(q.take(), "Two.")  # said again in full
        self.assertEqual(q.take(), "Three.")

    def test_rewind_at_the_start_is_a_no_op(self):
        q = SpeechQueue()
        q.load("Only one.")
        q.rewind()
        self.assertEqual(q.take(), "Only one.")

    def test_loading_a_new_readout_abandons_the_previous_one(self):
        q = SpeechQueue()
        q.load("One. Two. Three.")
        q.take()
        q.load("Something else.")
        self.assertEqual(q.remaining, 1)
        self.assertEqual(q.take(), "Something else.")

    def test_a_readout_interrupted_too_long_ago_is_dropped(self):
        q = SpeechQueue(stale_after=90)
        q.load("One. Two. Three.", now=100)
        q.take()
        self.assertIsNone(q.resume_or_drop(191))
        self.assertFalse(q.has_more)

    def test_a_readout_interrupted_a_moment_ago_resumes(self):
        q = SpeechQueue(stale_after=90)
        q.load("One. Two. Three.", now=100)
        q.take()
        self.assertEqual(q.resume_or_drop(103), "Two.")

    def test_clear_drops_everything(self):
        q = SpeechQueue()
        q.load("One. Two. Three.")
        q.clear()
        self.assertFalse(q.has_more)
        self.assertEqual(q.remaining, 0)


if __name__ == "__main__":
    unittest.main()
