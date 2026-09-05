// BlindAssist — native frame compression for the remote-inference path.
//
// Why this exists, measured on the user's hotspot 2026-09-05:
//
//   raw YUV420 planes, 720x480 ...... 506 KB ... 320-510 ms to upload
//   all server-side inference ........          ... 171 ms
//   app's per-frame timeout ..........          ... 1200 ms
//
// The upload was three times the cost of every model on the other end, and
// frames were being lost to it. A lost frame is not merely a slower app: it
// breaks GuidanceEngine's two-frame persistence streak, so obstacles get
// announced erratically and a briefly-seen object never accumulates enough
// sightings to enter the object memory.
//
// JPEG at quality 80 is ~45 KB for the same frame — about a 10x cut — and
// Android's YuvImage.compressToJpeg is hardware-backed, so it costs a few ms
// on the phone. Encoding in Dart instead would mean a per-pixel loop on the UI
// isolate, which is the very cost that makes on-device inference unusable here.
import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/services.dart';

/// JPEG quality for uploaded frames. 80 is visually lossy but detection-safe:
/// YOLO's backbone is far more tolerant of JPEG artefacts than of the
/// resolution loss that the alternative (downscaling) would cost.
const int kJpegQuality = 80;

class FrameCodec {
  static const MethodChannel _channel = MethodChannel('blindassist/frame');

  /// Set once the native encoder has failed. Everything then posts raw planes,
  /// exactly as before this existed — a phone whose platform channel is
  /// missing or broken keeps working, just slower.
  static bool _nativeBroken = false;

  /// True while frames are being compressed. Read by the UI/logs so a silent
  /// fallback to the slow path is visible rather than merely felt.
  static bool get compressing => !_nativeBroken;

  /// Last failure reason, for diagnostics.
  static String? failure;

  /// Encode [image]'s planes as JPEG, or null if the native path is
  /// unavailable — in which case the caller posts the raw planes.
  static Future<Uint8List?> jpegFromCameraImage(CameraImage image) async {
    if (_nativeBroken) return null;
    try {
      final y = image.planes[0], u = image.planes[1], v = image.planes[2];
      final bytes = await _channel.invokeMethod<Uint8List>('encodeJpeg', {
        'y': y.bytes,
        'u': u.bytes,
        'v': v.bytes,
        'width': image.width,
        'height': image.height,
        'yStride': y.bytesPerRow,
        'uvStride': u.bytesPerRow,
        'uvPixelStride': u.bytesPerPixel ?? 1,
        'quality': kJpegQuality,
      });
      if (bytes == null || bytes.isEmpty) {
        _giveUp('native encoder returned no bytes');
        return null;
      }
      return bytes;
    } catch (e) {
      // One failure disables the fast path for the session. Retrying per frame
      // would pay the platform-channel round trip on every frame forever to
      // rediscover the same broken encoder.
      _giveUp('$e');
      return null;
    }
  }

  static void _giveUp(String reason) {
    if (_nativeBroken) return;
    _nativeBroken = true;
    failure = reason;
    // ignore: avoid_print
    print('BlindAssist: JPEG frame encoding unavailable ($reason) — '
        'falling back to raw YUV upload, expect slower frames');
  }

  /// Test seam: forget any recorded failure.
  static void resetForTest() {
    _nativeBroken = false;
    failure = null;
  }
}
