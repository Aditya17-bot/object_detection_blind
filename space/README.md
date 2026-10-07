---
title: BlindAssist
emoji: 🦯
colorFrom: yellow
colorTo: gray
sdk: static
pinned: false
short_description: Camera assistant that says which obstacle matters and where
---

# BlindAssist demo

Browser demo of [BlindAssist](https://github.com/Aditya17-bot/object_detection_blind),
an Android app that helps visually impaired users move around indoors.

The same two models the phone runs (a COCO YOLOv8n and a fine-tune for doors,
which COCO lacks) run in the browser with ONNX Runtime Web, on WebGPU when
available and WebAssembly otherwise. No photo is uploaded anywhere.

Detections from both models are merged, each box becomes a clock bearing and a
proximity bucket, and the app's decision rules pick the one sentence worth
saying. The browser reads it aloud.

- **Walk**: warns about the obstacle in your way and which side is freer.
- **Find**: locates one object, e.g. a bottle.
- **Describe**: summarises everything in view.

## Files

- `logic.js` is a port of `position.py`, `decision.py` and `detect_merge.py`.
  `test_logic_parity.py` (in the GitHub repo) runs 2000 random scenes through
  both and requires identical output.
- `models/*.onnx` are exported from `yolov8n.pt` and `door_dustbin_stairs.pt`
  with `YOLO(...).export(format="onnx", imgsz=640, opset=17, simplify=True)`.
  They are not in the GitHub repo (`*.onnx` is gitignored); regenerate them with
  that command.
