"""BlindAssist — Phase 4: speech output.

pyttsx3 blocks while speaking, so Speaker runs it on its own daemon thread
and the camera loop never stalls. Only the LATEST pending message is kept:
guidance goes stale fast, so a new announcement arriving while the engine is
busy REPLACES whatever was waiting instead of queueing behind it.

The engine factory is injectable so the queueing behaviour is unit-testable
without making sound (see test_speech.py).
"""

import threading
import time


class Speaker:
    def __init__(self, rate=175, volume=1.0, engine_factory=None):
        if engine_factory is None:
            import pyttsx3
            engine_factory = pyttsx3.init
        self._engine_factory = engine_factory
        self._rate = rate
        self._volume = volume
        self._cond = threading.Condition()
        self._pending = None
        self._speaking = False
        self._closing = False
        self._thread = threading.Thread(target=self._worker, daemon=True,
                                        name="blindassist-tts")
        self._thread.start()

    def say(self, message):
        """Hand a message to the speech thread; replaces any message that is
        still waiting (latest wins), never blocks the caller."""
        with self._cond:
            self._pending = message
            self._cond.notify_all()

    def wait_until_idle(self, timeout=10.0):
        """Block until nothing is pending or being spoken (demo shutdown /
        tests). Returns True if idle was reached within the timeout."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._pending is not None or self._speaking:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
        return True

    def close(self, timeout=5.0):
        """Finish the current utterance and stop the thread."""
        with self._cond:
            self._closing = True
            self._cond.notify_all()
        self._thread.join(timeout)

    def _worker(self):
        # pyttsx3 engines are not thread-safe: create the engine on the
        # thread that uses it, not in __init__.
        engine = self._engine_factory()
        engine.setProperty("rate", self._rate)
        engine.setProperty("volume", self._volume)
        while True:
            with self._cond:
                while self._pending is None and not self._closing:
                    self._cond.wait()
                if self._pending is None:  # closing with nothing left to say
                    return
                message = self._pending
                self._pending = None
                self._speaking = True
            try:
                engine.say(message)
                engine.runAndWait()  # blocks HERE, not in the camera loop
            finally:
                with self._cond:
                    self._speaking = False
                    self._cond.notify_all()
