"""Tests for infer_server.py — fake YOLO models, no real weights loaded
(same philosophy as test_webapp.py's fake engine)."""
import io
import json
import socket
import unittest

import numpy as np

from infer_server import (DISCOVER_MSG, REPLY_PREFIX, build_app,
                          start_discovery_responder, yuv420_to_bgr)


class _FakeBox:
    def __init__(self, cls, conf, xyxyn):
        self.cls = cls
        self.conf = conf
        self.xyxyn = [xyxyn]


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class FakeYOLO:
    """Mimics the slice of the ultralytics API the server touches."""

    def __init__(self, names, boxes=()):
        self.names = names
        self._boxes = list(boxes)
        self.seen_shapes = []

    def predict(self, frame, conf=0.25, verbose=False):
        self.seen_shapes.append(np.asarray(frame).shape)
        return [_FakeResult(self._boxes)]


def _gray_planes(w, h, y_stride=None, uv_stride=None, uv_pixel_stride=1):
    """Solid mid-gray YUV frame: Y=128, U=V=128 -> BGR ~(128,128,128)."""
    y_stride = y_stride or w
    uv_stride = uv_stride or (w // 2)
    y = bytes([128] * (h * y_stride))
    uv = bytes([128] * ((h // 2) * uv_stride * uv_pixel_stride))
    return y, uv, uv


class YuvTest(unittest.TestCase):
    def test_solid_gray_roundtrip(self):
        y, u, v = _gray_planes(8, 8)
        bgr = yuv420_to_bgr(y, u, v, 8, 8, 8, 4, 1)
        self.assertEqual(bgr.shape, (8, 8, 3))
        self.assertTrue(np.all(np.abs(bgr.astype(int) - 128) <= 1))

    def test_unpadded_last_row_does_not_crash(self):
        # Android commonly ships (h-1)*stride + w bytes for Y — the last row
        # unpadded. This exact layout used to crash the reshape.
        w, h, stride = 6, 4, 8
        full = bytes([128] * (h * stride))
        short = full[:(h - 1) * stride + w]
        _, u, v = _gray_planes(w, h, uv_stride=3)
        bgr_full = yuv420_to_bgr(full, u, v, w, h, stride, 3, 1)
        bgr_short = yuv420_to_bgr(short, u, v, w, h, stride, 3, 1)
        np.testing.assert_array_equal(bgr_full, bgr_short)


class ServerTest(unittest.TestCase):
    def _client(self, coco_boxes=(), custom=None):
        # custom=None -> explicitly NO custom model (build_app only
        # auto-loads the real .pt when custom_model is left unset)
        coco = FakeYOLO({0: "person", 39: "bottle", 62: "tv"}, coco_boxes)
        app = build_app(coco_model=coco, custom_model=custom)
        return app.test_client(), coco

    def _post(self, client, w=8, h=8, rotation=0):
        y, u, v = _gray_planes(w, h)
        return client.post("/infer", data={
            "width": str(w), "height": str(h),
            "yStride": str(w), "uvStride": str(w // 2),
            "uvPixelStride": "1", "rotation": str(rotation),
            "y": (io.BytesIO(y), "y"),
            "u": (io.BytesIO(u), "u"),
            "v": (io.BytesIO(v), "v"),
        }, content_type="multipart/form-data")

    def test_health_reports_custom_flag(self):
        client, _ = self._client()
        data = json.loads(client.get("/health").data)
        self.assertEqual(data, {"ok": True, "custom": False})
        client2, _ = self._client(custom=FakeYOLO({0: "door"}))
        data2 = json.loads(client2.get("/health").data)
        self.assertTrue(data2["custom"])

    def test_infer_returns_target_detection(self):
        client, _ = self._client(
            coco_boxes=[_FakeBox(0, 0.9, (0.1, 0.2, 0.3, 0.4))])
        data = json.loads(self._post(client).data)
        self.assertEqual(len(data["detections"]), 1)
        d = data["detections"][0]
        self.assertEqual(d["name"], "person")
        self.assertAlmostEqual(d["conf"], 0.9)
        self.assertAlmostEqual(d["x1"], 0.1)
        self.assertAlmostEqual(d["y2"], 0.4)

    def test_infer_filters_low_conf_and_non_target(self):
        client, _ = self._client(coco_boxes=[
            _FakeBox(0, 0.5, (0, 0, 1, 1)),    # person below COCO_CONF 0.6
            _FakeBox(62, 0.9, (0, 0, 1, 1)),   # tv IS a target -> kept
        ])
        names = [d["name"] for d in
                 json.loads(self._post(client).data)["detections"]]
        self.assertEqual(names, ["tv"])

    def test_custom_model_low_floor(self):
        custom = FakeYOLO({0: "door"},
                          [_FakeBox(0, 0.45, (0.0, 0.0, 0.5, 1.0))])
        client, _ = self._client(custom=custom)
        names = [d["name"] for d in
                 json.loads(self._post(client).data)["detections"]]
        # 0.45 passes the door floor (0.4) even though COCO_CONF is 0.6
        self.assertEqual(names, ["door"])

    def test_rotation_swaps_frame_shape(self):
        client, coco = self._client()
        self._post(client, w=8, h=6, rotation=90)
        # warmup call is seen_shapes[0]; the request frame must be rotated
        self.assertEqual(coco.seen_shapes[-1], (8, 6, 3))  # 6x8 -> rot90 -> 8x6

    def test_warmup_runs_at_startup(self):
        _, coco = self._client()
        self.assertEqual(coco.seen_shapes, [(640, 640, 3)])


class DiscoveryTest(unittest.TestCase):
    def test_responder_replies_with_http_port(self):
        server_sock = start_discovery_responder(5001, port=0)
        port = server_sock.getsockname()[1]
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(2)
        try:
            client.sendto(DISCOVER_MSG, ("127.0.0.1", port))
            data, _ = client.recvfrom(64)
            self.assertEqual(data, REPLY_PREFIX + b"5001")
            # garbage must be ignored, not crash the thread
            client.sendto(b"garbage", ("127.0.0.1", port))
            client.sendto(DISCOVER_MSG, ("127.0.0.1", port))
            data2, _ = client.recvfrom(64)
            self.assertEqual(data2, REPLY_PREFIX + b"5001")
        finally:
            client.close()
            server_sock.close()


if __name__ == "__main__":
    unittest.main()
