"""Unit tests for speech.py — run with:  python -m unittest test_speech -v

Uses a fake engine so no sound is made; tests the threading/queue rules:
never block the caller, latest message wins, clean shutdown.
"""

import threading
import unittest

from speech import Speaker


class FakeEngine:
    """Stands in for pyttsx3: records what was 'spoken'. If `gate` is given,
    runAndWait() blocks on it — simulating a slow utterance."""

    def __init__(self, gate=None):
        self.spoken = []
        self.props = {}
        self.gate = gate
        self.started_speaking = threading.Event()
        self._current = None

    def setProperty(self, key, value):
        self.props[key] = value

    def say(self, text):
        self._current = text

    def runAndWait(self):
        self.started_speaking.set()
        if self.gate is not None:
            assert self.gate.wait(5), "test gate never opened"
        self.spoken.append(self._current)


class TestSpeaker(unittest.TestCase):
    def test_speaks_and_sets_properties(self):
        fake = FakeEngine()
        s = Speaker(rate=150, volume=0.8, engine_factory=lambda: fake)
        s.say("Chair on right")
        self.assertTrue(s.wait_until_idle(5))
        s.close()
        self.assertEqual(fake.spoken, ["Chair on right"])
        self.assertEqual(fake.props, {"rate": 150, "volume": 0.8})

    def test_latest_message_wins_while_busy(self):
        gate = threading.Event()
        fake = FakeEngine(gate=gate)
        s = Speaker(engine_factory=lambda: fake)
        s.say("first")
        # engine is now stuck 'speaking' the first message...
        self.assertTrue(fake.started_speaking.wait(5))
        s.say("second")          # waits...
        s.say("third")           # ...and is replaced before being spoken
        gate.set()
        self.assertTrue(s.wait_until_idle(5))
        s.close()
        self.assertEqual(fake.spoken, ["first", "third"])

    def test_say_never_blocks_caller(self):
        gate = threading.Event()
        fake = FakeEngine(gate=gate)
        s = Speaker(engine_factory=lambda: fake)
        s.say("one")
        self.assertTrue(fake.started_speaking.wait(5))
        s.say("two")             # must return instantly even though busy
        gate.set()
        self.assertTrue(s.wait_until_idle(5))
        s.close()

    def test_close_stops_thread(self):
        fake = FakeEngine()
        s = Speaker(engine_factory=lambda: fake)
        s.say("bye")
        self.assertTrue(s.wait_until_idle(5))
        s.close()
        self.assertFalse(s._thread.is_alive())


if __name__ == "__main__":
    unittest.main()
