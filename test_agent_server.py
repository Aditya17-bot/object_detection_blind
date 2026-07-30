"""POST /agent endpoint tests — fake router, fake transcriber, bare Flask app.

No cv2, no ultralytics, no Whisper weights: the endpoint lives in its own
module precisely so it can be tested where the servers that host it cannot be.
"""

import io
import unittest

from flask import Flask

from agent import ASK_TEMPLATES, AgentRouter
from agent_server import register_agent_routes


class FakeTranscriber:
    def __init__(self, text="find the bottle", error=None):
        self.text = text
        self.error = error
        self.calls = 0

    def transcribe_file(self, stream):
        self.calls += 1
        return self.text


def client(router=None, transcriber=None, execute=None, get_state=None):
    app = Flask(__name__)
    register_agent_routes(app, router or AgentRouter(llm=None), transcriber,
                          execute, get_state)
    return app.test_client()


class TextPathTest(unittest.TestCase):
    def test_typed_utterance_routes_at_tier_zero(self):
        body = client().post("/agent", json={"text": "find the bottle"}).get_json()
        self.assertEqual(body["source"], "grammar")
        self.assertEqual(body["actions"], [{"tool": "find", "arg": "bottle"}])
        self.assertIsNone(body["transcript"])

    def test_form_encoded_text_also_works(self):
        body = client().post("/agent", data={"text": "walk mode"}).get_json()
        self.assertEqual(body["actions"], [{"tool": "walk", "arg": None}])

    def test_unroutable_text_abstains_with_a_template(self):
        body = client().post("/agent",
                             json={"text": "what's the weather"}).get_json()
        self.assertEqual(body["source"], "abstain")
        self.assertEqual(body["actions"], [])
        self.assertEqual(body["message"], ASK_TEMPLATES["unknown"])

    def test_missing_text_is_rejected(self):
        self.assertEqual(client().post("/agent", json={}).status_code, 400)
        self.assertEqual(
            client().post("/agent", json={"text": "  "}).status_code, 400)

    def test_execute_callback_reports_what_was_spoken(self):
        c = client(execute=lambda result: ["Walk mode"])
        self.assertEqual(
            c.post("/agent", json={"text": "walk"}).get_json()["spoken"],
            ["Walk mode"])

    def test_state_callback_is_consulted(self):
        seen = []

        class Recorder:
            def route(self, text, state_text, tool_list):
                seen.append(state_text)
                return {"actions": [{"tool": "describe"}]}

        c = client(router=AgentRouter(llm=Recorder()),
                   get_state=lambda: {"mode": "find", "target": "cup",
                                      "visible": [], "remembered": []})
        c.post("/agent", json={"text": "what about it"})
        self.assertIn("cup", seen[0])


class AudioPathTest(unittest.TestCase):
    def _post_wav(self, c, data=b"RIFFfake"):
        return c.post("/agent", data={"audio": (io.BytesIO(data), "clip.wav")},
                      content_type="multipart/form-data")

    def test_upload_is_transcribed_then_routed(self):
        fake = FakeTranscriber("find the bottle")
        body = self._post_wav(client(transcriber=fake)).get_json()
        self.assertEqual(fake.calls, 1)
        self.assertEqual(body["transcript"], "find the bottle")
        self.assertEqual(body["actions"], [{"tool": "find", "arg": "bottle"}])

    def test_upload_without_a_transcriber_is_503(self):
        self.assertEqual(self._post_wav(client()).status_code, 503)

    def test_silence_is_refused_not_routed(self):
        """Empty audio must not be routed as an empty utterance — refusing
        beats matching '' against whatever tool comes first."""
        fake = FakeTranscriber(None, error="nothing heard")
        response = self._post_wav(client(transcriber=fake))
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(response.get_json()["transcript"])


if __name__ == "__main__":
    unittest.main()
