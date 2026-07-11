"""Web frontend tests: routes + validation against a fake engine.

No camera, no YOLO, no sound — webapp.create_app() takes any object with the
engine's small read/control surface, so these run as fast as the other suites.
"""

import unittest

from webapp import create_app


class FakeEngine:
    def __init__(self):
        self.mode = "walk"
        self.target = None
        self.muted = False
        self.rate = 175
        self.described = 0

    def snapshot(self):
        return {"mode": self.mode, "target": self.target, "muted": self.muted,
                "rate": self.rate, "fps": 5.0, "model": "yolov8s.pt",
                "source": "fake", "detections": [], "announcements": [],
                "sonar": {"level": 0, "pan": 0.0, "name": None},
                "voice": {"active": False, "last": None, "error": None},
                "error": None}

    def latest_jpeg(self):
        return b"notajpeg"

    def set_mode(self, mode, target=None):
        self.mode, self.target = mode, target

    def describe(self):
        self.described += 1
        return "Nothing detected"

    def set_rate(self, rate):
        self.rate = rate


class TestWebApp(unittest.TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.client = create_app(self.engine).test_client()

    def test_index_serves_page(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"BlindAssist", r.data)
        self.assertIn(b"bottle", r.data)  # find-target options rendered

    def test_state_returns_snapshot(self):
        r = self.client.get("/state")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["mode"], "walk")

    def test_mode_switch_to_find(self):
        r = self.client.post("/mode", json={"mode": "find", "target": "bottle"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((self.engine.mode, self.engine.target),
                         ("find", "bottle"))

    def test_mode_walk_ignores_target(self):
        self.client.post("/mode", json={"mode": "walk", "target": "bottle"})
        self.assertEqual((self.engine.mode, self.engine.target),
                         ("walk", None))

    def test_bad_mode_and_bad_target_rejected(self):
        self.assertEqual(
            self.client.post("/mode", json={"mode": "fly"}).status_code, 400)
        self.assertEqual(
            self.client.post("/mode", json={"mode": "find",
                                            "target": "unicorn"}).status_code,
            400)
        self.assertEqual(self.engine.mode, "walk")  # unchanged

    def test_describe_calls_engine(self):
        r = self.client.post("/describe")
        self.assertEqual(r.get_json()["summary"], "Nothing detected")
        self.assertEqual(self.engine.described, 1)

    def test_mute_toggle(self):
        self.client.post("/mute", json={"muted": True})
        self.assertTrue(self.engine.muted)
        self.client.post("/mute", json={"muted": False})
        self.assertFalse(self.engine.muted)

    def test_rate_validated(self):
        self.assertEqual(
            self.client.post("/rate", json={"rate": 999}).status_code, 400)
        self.assertEqual(
            self.client.post("/rate", json={"rate": "fast"}).status_code, 400)
        self.assertEqual(
            self.client.post("/rate", json={"rate": 200}).status_code, 200)
        self.assertEqual(self.engine.rate, 200)


if __name__ == "__main__":
    unittest.main()
