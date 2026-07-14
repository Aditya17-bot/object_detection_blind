#!/bin/bash
# Export both models to TFLite — uses ultralytics < 8.4.83 (classic onnx2tf
# path; the new litert-torch converter is incompatible with our torch).
set -e
source ~/yolo_env/bin/activate
pip install -q "ultralytics<8.4.83" onnx onnx2tf onnxslim onnx_graphsurgeon sng4onnx onnxruntime
cd "/mnt/c/Users/rober/OneDrive/Desktop/object_detection_blind"
for model in yolov8n.pt door_dustbin_stairs.pt; do
  echo "=== exporting $model ==="
  # 640, NOT 416: the 416 export cost ~0.2 conf per detection and the app's
  # 0.6 threshold then filtered nearly everything out (fixed 2026-07-13).
  yolo export model="$model" format=tflite half=True imgsz=640
done
echo "=== done, tflite files: ==="
find . -maxdepth 2 -name "*.tflite"
