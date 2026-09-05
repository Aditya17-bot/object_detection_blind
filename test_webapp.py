"""Web frontend tests: routes + validation against a fake engine.

No camera, no YOLO, no sound — webapp.create_app() takes any object with the
engine's small read/control surface, so these run as fast as the other suites.
"""

import unittest

from webapp import AssistantEngine, create_app


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


class VoiceDispatchTest(unittest.TestCase):
    """The real AssistantEngine's voice dispatch, with no camera and no model.

    __init__ deliberately does no heavy imports (they live in start()), so the
    dispatch can be exercised directly — which is the only way to regression-
    test the bug this rewrite fixes."""

    def setUp(self):
        self.engine = AssistantEngine(voice=False, muted=True)

    def say(self, action, target=None):
        self.engine._on_voice_command((action, target))
        return [a["text"] for a in self.engine.snapshot()["announcements"]]

    def test_mode_commands_still_work(self):
        self.assertEqual(self.say("find", "bottle")[-1], "Finding bottle")
        self.assertEqual(self.engine.snapshot()["target"], "bottle")
        self.assertEqual(self.say("walk")[-1], "Walk mode")

    def test_clock_and_zone_toggles_still_work(self):
        self.assertEqual(self.say("zones")[-1], "Zone mode")
        self.assertEqual(self.say("clock")[-1], "Clock mode")

    def test_sonar_mute_and_repeat_now_do_something(self):
        """Regression: the old hand-written dispatch silently dropped
        sonar/mute/stop/repeat/read, so five voice commands were dead."""
        self.say("sonar", "off")
        self.assertFalse(self.engine.snapshot()["sonar_on"])
        self.say("sonar", "on")
        self.assertTrue(self.engine.snapshot()["sonar_on"])

        self.say("mute", "on")
        self.assertTrue(self.engine.muted)
        self.assertEqual(self.say("mute", "off")[-1], "Voice on")
        self.assertFalse(self.engine.muted)

        self.say("describe")
        self.assertEqual(self.say("repeat")[-1], "Nothing detected")

    def test_unwired_capability_says_so_instead_of_nothing(self):
        # OCR is a phone capability; the web UI must not silently no-op
        self.assertIn("isn't available", self.say("read")[-1])

    def test_unknown_action_never_raises(self):
        # an exception here kills the VoiceListener thread for the session
        self.engine._on_voice_command(("teleport", None))
        self.engine._on_voice_command(("find", None))

    def test_agent_route_is_tier_zero_without_a_model(self):
        result = self.engine.route("find the cup")
        self.assertEqual(result.source, "grammar")
        self.assertEqual(self.engine.run_route(result), ["Finding cup"])

    def test_agent_endpoint_is_registered(self):
        client = create_app(self.engine).test_client()
        body = client.post("/agent", json={"text": "describe"}).get_json()
        self.assertEqual(body["source"], "grammar")
        self.assertEqual(body["spoken"], ["Nothing detected"])

    def test_agent_endpoint_abstains_on_out_of_scope(self):
        client = create_app(self.engine).test_client()
        body = client.post("/agent",
                           json={"text": "what's the weather"}).get_json()
        self.assertEqual(body["source"], "abstain")
        self.assertEqual(body["actions"], [])


if __name__ == "__main__":
    unittest.main()
