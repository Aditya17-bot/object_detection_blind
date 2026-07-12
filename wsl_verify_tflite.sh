#!/bin/bash
# Verify TFLite exports detect the same things as the .pt originals.
set -e
source ~/yolo_env/bin/activate
cd "/mnt/c/Users/rober/OneDrive/Desktop/object_detection_blind"
python - <<'EOF'
from ultralytics import YOLO

def show(tag, results, conf):
    names = results[0].names
    dets = [(names[int(b.cls[0])], round(float(b.conf[0]), 2))
            for b in results[0].boxes if float(b.conf[0]) >= conf]
    print(f"{tag}: {sorted(dets, key=lambda d: -d[1])}")

# COCO model on bus.jpg — .pt baseline was 3-4 persons + bus
for tag, path in [("pt  ", "yolov8n.pt"),
                  ("tfl ", "yolov8n_saved_model/yolov8n_float16.tflite")]:
    m = YOLO(path, task="detect")
    show("coco " + tag, m.predict("bus.jpg", imgsz=416, verbose=False), 0.5)

# custom model on the couch-clip keyframe with the open doorway
img = "test_output/custom_3 PM (1)_f0025.jpg"
for tag, path in [("pt  ", "door_dustbin_stairs.pt"),
                  ("tfl ", "door_dustbin_stairs_saved_model/door_dustbin_stairs_float16.tflite")]:
    m = YOLO(path, task="detect")
    show("custom " + tag, m.predict(img, imgsz=416, verbose=False), 0.4)
EOF
