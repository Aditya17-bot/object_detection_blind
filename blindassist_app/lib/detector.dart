// BlindAssist — on-device detection, run in a BACKGROUND ISOLATE so the two
// TFLite inferences never block the UI isolate (that block was the cause of the
// unusable lag, and it also starved the Vosk voice callback + TTS, which share
// the UI isolate). The main isolate only copies the camera frame's bytes and
// awaits the detections.
//
// Same rules as webapp.py: COCO model at conf 0.6, custom door/dustbin model at
// conf 0.5. "stairs" is dropped because it is not in targetClasses. To keep the
// average cost down the custom model runs every _customEvery-th frame.
import 'dart:async';
import 'dart:isolate';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:tflite_flutter/tflite_flutter.dart';

import 'logic/labels.dart';
import 'logic/position.dart';

const double kNmsIou = 0.45;
const int _customEvery = 3; // run the custom door/dustbin model 1 frame in N

// Try the TFLite GPU delegate first (Adreno on the S20 FE): ~5x faster than
// single-thread CPU and it sidesteps the multi-thread-XNNPACK-in-isolate
// deadlock entirely (GPU isn't XNNPACK). Falls back to CPU automatically if
// the delegate can't be created on the device. Flip to false to force CPU.
const bool _useGpu = true;

/// GPU delegates created in the worker isolate, kept so they can be explicitly
/// deleted on dispose (closing the interpreter does NOT free the delegate's
/// native GL handle).
final List<GpuDelegateV2> _workerDelegates = [];

/// Build an interpreter for [bytes], GPU-delegated when possible, else a
/// single-thread CPU interpreter (the project's known-good config). Created on
/// whichever isolate calls this — the worker — so the GPU GL context lives on
/// the same thread that runs inference.
Interpreter _buildInterpreter(Uint8List bytes) {
  if (_useGpu) {
    try {
      final delegate = GpuDelegateV2();
      final interp = Interpreter.fromBuffer(bytes,
          options: InterpreterOptions()..addDelegate(delegate));
      interp.allocateTensors();
      _workerDelegates.add(delegate);
      // ignore: avoid_print
      print('BlindAssist: GPU delegate active');
      return interp;
    } catch (e) {
      // ignore: avoid_print
      print('BlindAssist: GPU delegate unavailable, CPU fallback ($e)');
    }
  }
  final interp = Interpreter.fromBuffer(bytes,
      options: InterpreterOptions()..threads = 1);
  interp.allocateTensors();
  return interp;
}

/// One detection in normalized portrait coordinates. Plain fields so it is
/// sendable across the isolate boundary.
class Detection {
  final String name;
  final double confidence;
  final double x1, y1, x2, y2; // 0..1
  const Detection(this.name, this.confidence, this.x1, this.y1, this.x2, this.y2);
}

// --- messages across the isolate boundary ---------------------------------

/// Raw model bytes + labels shipped to the worker, which builds the
/// interpreter itself (see _buildInterpreter — the GPU delegate must be
/// created on the same isolate that runs inference). Multi-thread XNNPACK is
/// never used, so the old "create in worker deadlocks" caveat does not apply.
class _ModelSpec {
  final Uint8List bytes;
  final List<String> labels;
  final double conf;
  _ModelSpec(this.bytes, this.labels, this.conf);
}

class _InitMsg {
  final SendPort reply;
  final _ModelSpec coco;
  final _ModelSpec? custom;
  _InitMsg(this.reply, this.coco, this.custom);
}

/// A camera frame flattened into sendable byte buffers.
class _FrameMsg {
  final int id;
  final int width, height, rotation;
  final int yStride, uvStride, uvPixelStride;
  final Uint8List y, u, v;
  final bool runCustom;
  _FrameMsg(this.id, this.width, this.height, this.rotation, this.yStride,
      this.uvStride, this.uvPixelStride, this.y, this.u, this.v, this.runCustom);
}

class _ResultMsg {
  final int id;
  final List<Detection> detections;
  final String? error;
  _ResultMsg(this.id, this.detections, [this.error]);
}

/// Public API is unchanged apart from detect() now returning a Future.
class Detector {
  Isolate? _isolate;
  SendPort? _toWorker;
  final Completer<void> _ready = Completer<void>();
  final Map<int, Completer<List<Detection>>> _pending = {};
  int _frameId = 0;
  int _frameCount = 0;

  Future<void> load() async {
    final cocoBytes =
        (await rootBundle.load('assets/models/yolov8n.tflite')).buffer.asUint8List();
    final coco = _ModelSpec(cocoBytes, cocoLabels, 0.6);
    _ModelSpec? custom;
    try {
      final customBytes = (await rootBundle
              .load('assets/models/door_dustbin_stairs.tflite'))
          .buffer
          .asUint8List();
      custom = _ModelSpec(customBytes, customLabels, 0.5);
    } catch (_) {
      // custom model missing — app still works with COCO classes only
    }

    final fromWorker = ReceivePort();
    final errors = ReceivePort();
    errors.listen((e) {
      // isolates swallow uncaught errors by default — surface them in logcat
      // ignore: avoid_print
      print('BlindAssist detector isolate error: $e');
    });
    _isolate = await Isolate.spawn(_workerEntry, fromWorker.sendPort,
        onError: errors.sendPort, errorsAreFatal: false);
    fromWorker.listen((msg) {
      if (msg is SendPort) {
        _toWorker = msg;
        msg.send(_InitMsg(fromWorker.sendPort, coco, custom));
      } else if (msg == 'ready') {
        if (!_ready.isCompleted) _ready.complete();
      } else if (msg is String && msg.startsWith('init-failed')) {
        // surface the failure so the app shows an error instead of silently
        // detecting nothing forever (an empty room looks identical otherwise)
        if (!_ready.isCompleted) _ready.completeError(msg);
      } else if (msg is _ResultMsg) {
        if (msg.error != null) {
          // ignore: avoid_print
          print('BlindAssist detect failed: ${msg.error}');
        }
        _pending.remove(msg.id)?.complete(msg.detections);
      }
    });
    await _ready.future;
  }

  /// Run detection for one camera frame off the UI isolate.
  Future<List<Detection>> detect(CameraImage image, int rotation) async {
    if (_toWorker == null) return const [];
    final id = _frameId++;
    final runCustom = (_frameCount++ % _customEvery) == 0;
    final u = image.planes[1], v = image.planes[2];
    final msg = _FrameMsg(
      id,
      image.width,
      image.height,
      rotation,
      image.planes[0].bytesPerRow,
      u.bytesPerRow,
      u.bytesPerPixel ?? 1,
      // copy so the native camera buffer can be recycled immediately
      Uint8List.fromList(image.planes[0].bytes),
      Uint8List.fromList(u.bytes),
      Uint8List.fromList(v.bytes),
      runCustom,
    );
    final c = Completer<List<Detection>>();
    _pending[id] = c;
    _toWorker!.send(msg);
    // watchdog: a lost/failed frame must never wedge the camera loop
    return c.future.timeout(const Duration(seconds: 3), onTimeout: () {
      _pending.remove(id);
      // ignore: avoid_print
      print('BlindAssist detect timeout (frame $id)');
      return const [];
    });
  }

  void close() {
    // ask the worker to free native interpreter + GPU-delegate handles first
    // (isolate death alone does NOT run the C-API destructors), then kill it.
    _toWorker?.send('dispose');
    final iso = _isolate;
    _isolate = null;
    _toWorker = null;
    Future.delayed(const Duration(milliseconds: 150),
        () => iso?.kill(priority: Isolate.immediate));
  }
}

// --- worker isolate --------------------------------------------------------

void _workerEntry(SendPort toMain) {
  final port = ReceivePort();
  toMain.send(port.sendPort);
  _Worker? worker;
  port.listen((msg) {
    if (msg is _InitMsg) {
      try {
        worker = _Worker(msg.coco, msg.custom);
        msg.reply.send('ready');
      } catch (e, st) {
        // ignore: avoid_print
        print('BlindAssist worker init failed: $e\n$st');
        msg.reply.send('init-failed: $e'); // surfaced as an app error
      }
    } else if (msg is _FrameMsg) {
      try {
        toMain.send(_ResultMsg(msg.id, worker!.run(msg)));
      } catch (e, st) {
        toMain.send(_ResultMsg(msg.id, const [], '$e\n$st'));
      }
    } else if (msg == 'dispose') {
      worker?.dispose();
    }
  });
}

/// One reattached model plus reusable buffers (allocated once, not per frame).
class _WModel {
  final Interpreter interpreter;
  final List<String> labels;
  final double conf;
  final int size, channels, anchors;
  final Float32List input;
  final List<List<List<double>>> output; // reused every frame
  // letterbox of the last _fillInput, in normalized input coords (0..1)
  double lbLeft = 0, lbTop = 0, lbW = 1, lbH = 1;

  factory _WModel(_ModelSpec spec) {
    final interp = _buildInterpreter(spec.bytes);
    final size = interp.getInputTensor(0).shape[1];
    final outShape = interp.getOutputTensor(0).shape; // [1, 4+C, N]
    final channels = outShape[1], anchors = outShape[2];
    final output = List.generate(
        channels, (_) => List.filled(anchors, 0.0, growable: false),
        growable: false);
    final m = _WModel._(interp, spec.labels, spec.conf, size, channels, anchors,
        Float32List(size * size * 3), [output]);
    // Warm up: the FIRST inference on mobile TFLite pays graph-optimization +
    // delegate-init cost (often 1-2 s) — running it once here, on zeroed
    // input, means the first real camera frame is already fast.
    try {
      final sw = Stopwatch()..start();
      m.interpreter.run(m.input.reshape([1, size, size, 3]), m.output);
      // ignore: avoid_print
      print('BlindAssist warmup ${size}px: ${sw.elapsedMilliseconds}ms');
    } catch (e) {
      // ignore: avoid_print
      print('BlindAssist warmup failed: $e');
    }
    return m;
  }

  _WModel._(this.interpreter, this.labels, this.conf, this.size, this.channels,
      this.anchors, this.input, this.output);
}

class _Worker {
  final List<_WModel> _models = [];
  _WModel? _custom;

  _Worker(_ModelSpec coco, _ModelSpec? custom) {
    _models.add(_WModel(coco));
    if (custom != null) {
      _custom = _WModel(custom);
    }
  }

  /// Free native handles: close every interpreter, then delete the GPU
  /// delegates (interpreter.close() does not release the delegate).
  void dispose() {
    for (final m in [..._models, if (_custom != null) _custom!]) {
      try {
        m.interpreter.close();
      } catch (_) {}
    }
    for (final d in _workerDelegates) {
      try {
        d.delete();
      } catch (_) {}
    }
    _workerDelegates.clear();
  }

  List<Detection> run(_FrameMsg f) {
    final detections = <Detection>[];
    final sw = Stopwatch()..start();
    final coco = _models[0];
    _fillInput(f, coco);
    detections.addAll(_runModel(coco));
    if (f.id < 12) {
      print('BlindAssist TIMING f${f.id} coco: fill+infer ${sw.elapsedMilliseconds}ms');
    }
    if (f.runCustom && _custom != null) {
      final c = _custom!;
      // The YUV→RGB letterbox is the same image for both models when they use
      // the same input size (both export at 640). Reuse coco's buffer instead
      // of recomputing ~410k pixels of per-pixel float math a second time.
      if (c.size == coco.size) {
        c.input.setAll(0, coco.input);
        c.lbLeft = coco.lbLeft;
        c.lbTop = coco.lbTop;
        c.lbW = coco.lbW;
        c.lbH = coco.lbH;
      } else {
        _fillInput(f, c);
      }
      final t1 = sw.elapsedMilliseconds;
      detections.addAll(_runModel(c));
      if (f.id < 12) {
        print('BlindAssist TIMING f${f.id} custom: infer ${sw.elapsedMilliseconds - t1}ms');
      }
    }
    if (f.id < 12) print('BlindAssist TIMING f${f.id} total ${sw.elapsedMilliseconds}ms');
    detections.retainWhere((d) => targetClasses.contains(d.name));
    return detections;
  }

  List<Detection> _runModel(_WModel m) {
    m.interpreter.run(m.input.reshape([1, m.size, m.size, 3]), m.output);
    final out = m.output[0];
    final raw = <Detection>[];
    for (var i = 0; i < m.anchors; i++) {
      var best = 0.0;
      var bestClass = -1;
      for (var c = 4; c < m.channels; c++) {
        final s = out[c][i];
        if (s > best) {
          best = s;
          bestClass = c - 4;
        }
      }
      if (best < m.conf || bestClass < 0) continue;
      // model coords are in the letterboxed input square — map back to frame
      final cx = (out[0][i] - m.lbLeft) / m.lbW;
      final cy = (out[1][i] - m.lbTop) / m.lbH;
      final w = out[2][i] / m.lbW, h = out[3][i] / m.lbH;
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

  /// YUV420 -> rotated, letterboxed RGB float [0..1] into the model input
  /// buffer. Letterbox (not stretch) matches ultralytics preprocessing — a
  /// stretched portrait frame cost ~0.1-0.2 confidence per detection.
  void _fillInput(_FrameMsg f, _WModel m) {
    final w = f.width, h = f.height, size = m.size;
    final input = m.input;
    final yBytes = f.y, uBytes = f.u, vBytes = f.v;
    final yStride = f.yStride, uvStride = f.uvStride, uvPixelStride = f.uvPixelStride;
    final rotation = f.rotation;

    final rw = (rotation == 90 || rotation == 270) ? h : w;
    final rh = (rotation == 90 || rotation == 270) ? w : h;

    // letterbox: fit the rotated frame inside size×size, gray padding
    final scale = size / math.max(rw, rh);
    final nw = math.max(1, (rw * scale).round());
    final nh = math.max(1, (rh * scale).round());
    final left = (size - nw) ~/ 2, top = (size - nh) ~/ 2;
    m.lbLeft = left / size;
    m.lbTop = top / size;
    m.lbW = nw / size;
    m.lbH = nh / size;
    const pad = 114 / 255.0; // ultralytics letterbox gray

    var idx = 0;
    for (var oy = 0; oy < size; oy++) {
      final iy = oy - top;
      if (iy < 0 || iy >= nh) {
        for (var k = 0; k < size * 3; k++) {
          input[idx++] = pad;
        }
        continue;
      }
      final ry = (iy * rh) ~/ nh;
      for (var ox = 0; ox < size; ox++) {
        final ix = ox - left;
        if (ix < 0 || ix >= nw) {
          input[idx++] = pad;
          input[idx++] = pad;
          input[idx++] = pad;
          continue;
        }
        final rx = (ix * rw) ~/ nw;
        final int sx, sy;
        switch (rotation) {
          case 90:
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
}
