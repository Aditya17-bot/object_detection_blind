// BlindAssist — on-device detection. Mirrors the laptop pipeline:
// camera frame -> both TFLite models -> merged, thresholded, NMS'd
// detections with normalized coordinates (0..1, portrait orientation).
//
// Same rules as webapp.py: COCO model at conf 0.6 (416 px), custom
// door/dustbin model at conf 0.5 (640 px — its training size; verified
// door@0.86 on the couch-clip keyframe at this size). "stairs" is dropped
// because it is not in targetClasses.
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:tflite_flutter/tflite_flutter.dart';

import 'logic/labels.dart';
import 'logic/position.dart';

const double kNmsIou = 0.45;

/// One detection in normalized portrait coordinates.
class Detection {
  final String name;
  final double confidence;
  final double x1, y1, x2, y2; // 0..1
  const Detection(this.name, this.confidence, this.x1, this.y1, this.x2, this.y2);
}

/// One loaded TFLite model plus its preprocessing buffer.
class _Model {
  final Interpreter interpreter;
  final List<String> labels;
  final double conf;
  final int size;
  final Float32List input;

  _Model(this.interpreter, this.labels, this.conf)
      : size = interpreter.getInputTensor(0).shape[1],
        input = Float32List(interpreter.getInputTensor(0).shape[1] *
            interpreter.getInputTensor(0).shape[1] *
            3);
}

class Detector {
  final List<_Model> _models = [];

  Future<void> load() async {
    _models.add(_Model(
        await Interpreter.fromAsset('assets/models/yolov8n.tflite',
            options: InterpreterOptions()..threads = 4),
        cocoLabels,
        0.6));
    try {
      _models.add(_Model(
          await Interpreter.fromAsset(
              'assets/models/door_dustbin_stairs.tflite',
              options: InterpreterOptions()..threads = 2),
          customLabels,
          0.5));
    } catch (_) {
      // custom model missing — app still works with COCO classes only
    }
  }

  /// Run all models on one camera frame. [rotation] is the clockwise
  /// rotation (degrees) needed to make the sensor image upright.
  List<Detection> detect(CameraImage image, int rotation) {
    final detections = <Detection>[];
    for (final m in _models) {
      _fillInput(image, rotation, m);
      detections.addAll(_runModel(m));
    }
    // keep only classes the guidance layer knows (drops "stairs" too)
    detections.retainWhere((d) => targetClasses.contains(d.name));
    return detections;
  }

  List<Detection> _runModel(_Model m) {
    final outShape = m.interpreter.getOutputTensor(0).shape; // [1, 4+C, N]
    final channels = outShape[1], anchors = outShape[2];
    final output = List.generate(
        1,
        (_) => List.generate(channels, (_) => List.filled(anchors, 0.0),
            growable: false),
        growable: false);
    m.interpreter.run(m.input.reshape([1, m.size, m.size, 3]), output);
    final out = output[0];

    final raw = <Detection>[];
    for (var i = 0; i < anchors; i++) {
      var best = 0.0;
      var bestClass = -1;
      for (var c = 4; c < channels; c++) {
        final s = out[c][i];
        if (s > best) {
          best = s;
          bestClass = c - 4;
        }
      }
      if (best < m.conf || bestClass < 0) continue;
      final cx = out[0][i], cy = out[1][i], w = out[2][i], h = out[3][i];
      raw.add(Detection(
        m.labels[bestClass],
        best,
        (cx - w / 2).clamp(0.0, 1.0),
        (cy - h / 2).clamp(0.0, 1.0),
        (cx + w / 2).clamp(0.0, 1.0),
        (cy + h / 2).clamp(0.0, 1.0),
      ));
    }
    return _nms(raw);
  }

  /// Per-class non-maximum suppression.
  List<Detection> _nms(List<Detection> dets) {
    dets.sort((a, b) => b.confidence.compareTo(a.confidence));
    final kept = <Detection>[];
    for (final d in dets) {
      var keep = true;
      for (final k in kept) {
        if (k.name == d.name && _iou(k, d) > kNmsIou) {
          keep = false;
          break;
        }
      }
      if (keep) kept.add(d);
    }
    return kept;
  }

  double _iou(Detection a, Detection b) {
    final ix1 = math.max(a.x1, b.x1), iy1 = math.max(a.y1, b.y1);
    final ix2 = math.min(a.x2, b.x2), iy2 = math.min(a.y2, b.y2);
    final iw = math.max(0.0, ix2 - ix1), ih = math.max(0.0, iy2 - iy1);
    final inter = iw * ih;
    final union = (a.x2 - a.x1) * (a.y2 - a.y1) +
        (b.x2 - b.x1) * (b.y2 - b.y1) -
        inter;
    return union <= 0 ? 0 : inter / union;
  }

  /// YUV420 -> rotated, resized RGB float [0..1] straight into the model's
  /// input buffer. Sampling happens on the model's own output grid (nearest
  /// neighbour), so the full-resolution frame is never converted.
  void _fillInput(CameraImage image, int rotation, _Model m) {
    final w = image.width, h = image.height;
    final size = m.size;
    final input = m.input;
    final yPlane = image.planes[0];
    final uPlane = image.planes[1];
    final vPlane = image.planes[2];
    final yBytes = yPlane.bytes, uBytes = uPlane.bytes, vBytes = vPlane.bytes;
    final yStride = yPlane.bytesPerRow;
    final uvStride = uPlane.bytesPerRow;
    final uvPixelStride = uPlane.bytesPerPixel ?? 1;

    // upright (rotated) frame dimensions
    final rw = (rotation == 90 || rotation == 270) ? h : w;
    final rh = (rotation == 90 || rotation == 270) ? w : h;

    var idx = 0;
    for (var oy = 0; oy < size; oy++) {
      final ry = (oy * rh) ~/ size; // y in upright frame
      for (var ox = 0; ox < size; ox++) {
        final rx = (ox * rw) ~/ size; // x in upright frame
        // map upright coords back into the sensor frame
        final int sx, sy;
        switch (rotation) {
          case 90: // sensor landscape, device portrait (typical back camera)
            sx = ry;
            sy = h - 1 - rx;
          case 180:
            sx = w - 1 - rx;
            sy = h - 1 - ry;
          case 270:
            sx = w - 1 - ry;
            sy = rx;
          default:
            sx = rx;
            sy = ry;
        }
        final yv = yBytes[sy * yStride + sx];
        final uvIndex = (sy >> 1) * uvStride + (sx >> 1) * uvPixelStride;
        final u = uBytes[uvIndex] - 128;
        final v = vBytes[uvIndex] - 128;
        final r = (yv + 1.402 * v).clamp(0, 255).toDouble();
        final g = (yv - 0.344136 * u - 0.714136 * v).clamp(0, 255).toDouble();
        final b = (yv + 1.772 * u).clamp(0, 255).toDouble();
        input[idx++] = r / 255.0;
        input[idx++] = g / 255.0;
        input[idx++] = b / 255.0;
      }
    }
  }

  void close() {
    for (final m in _models) {
      m.interpreter.close();
    }
  }
}
