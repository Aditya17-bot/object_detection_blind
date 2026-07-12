/// Class-name tables for the two TFLite models. Order MUST match training.
library;

/// COCO-80, the classes of yolov8n.
const List<String> cocoLabels = [
  'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train',
  'truck', 'boat', 'traffic light', 'fire hydrant', 'stop sign',
  'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
  'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag',
  'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball', 'kite',
  'baseball bat', 'baseball glove', 'skateboard', 'surfboard',
  'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon',
  'bowl', 'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot',
  'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch', 'potted plant',
  'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote',
  'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
  'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear',
  'hair drier', 'toothbrush',
];

/// The user's custom Colab-trained model (door_dustbin_stairs.pt).
/// NOTE: "stairs" stays listed here (index order must match the model) but
/// is filtered out downstream — it is not in targetClasses (0.072 recall).
const List<String> customLabels = ['door', 'dustbin', 'stairs'];
