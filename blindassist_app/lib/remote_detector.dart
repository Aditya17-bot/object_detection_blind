// BlindAssist — remote inference client. The phone can't run YOLO in real time
// (Exynos 990: ~2.5 s/inference on device), so we ship each camera frame to
// infer_server.py on the laptop and get detections back over Wi-Fi.
//
// Frames go up as JPEG, compressed by Android's hardware encoder (see
// frame_codec.dart). Until 2026-09-05 they went up as RAW YUV420 planes —
// 506 KB per frame, measured at 320-510 ms to upload against 171 ms for all
// the inference on the other end, which blew the 1.2 s timeout regularly. The
// raw path is still here as the fallback when the platform channel is
// unavailable, so a phone without the native encoder keeps working.
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:http/http.dart' as http;

import 'detector.dart';
import 'frame_codec.dart';

/// A failed frame must resolve well inside the user's ~1 s guidance budget:
/// _busy in main.dart blocks new frames until the in-flight one resolves, so a
/// 3 s timeout meant up to 3 s of no guidance from one stalled request — and a
/// reply that old describes a scene the user already walked past. Normal LAN
/// round-trips are ~150-250 ms; real frames never come near this.
const Duration _inferTimeout = Duration(milliseconds: 1200);

class RemoteDetector implements FrameDetector {
  /// [client] is injectable for tests (package:http/testing MockClient).
  RemoteDetector(String host, int port, {http.Client? client})
      : _uri = Uri.parse('http://$host:$port/infer'),
        _healthUri = Uri.parse('http://$host:$port/health'),
        _client = client ?? http.Client();

  final Uri _uri;
  final Uri _healthUri;
  final http.Client _client;

  /// From the /health probe: whether the server loaded the custom
  /// door/dustbin model. Null until [load] succeeds. False means the app
  /// would run all day with no door warnings — the caller should say so.
  bool? customModelAvailable;

  @override
  Future<void> load() async {
    // Fail fast with a clear message if the laptop server isn't reachable,
    // instead of silently detecting nothing (looks identical to an empty room).
    try {
      final r = await _client
          .get(_healthUri)
          .timeout(const Duration(seconds: 4));
      if (r.statusCode != 200) {
        throw StateError('inference server returned ${r.statusCode}');
      }
      try {
        customModelAvailable =
            (jsonDecode(r.body) as Map<String, dynamic>)['custom'] as bool?;
      } catch (_) {
        customModelAvailable = null; // old server without the flag — unknown
      }
      // ignore: avoid_print
      print('BlindAssist: remote inference server OK ($_healthUri, '
          'custom model: $customModelAvailable)');
    } catch (e) {
      throw StateError('Cannot reach inference server at $_healthUri — is '
          'infer_server.py running and on the same Wi-Fi? ($e)');
    }
  }

  /// Returns null when the frame produced NO data (timeout, HTTP error,
  /// unreachable, bad body). Never an empty list on failure: the engine
  /// treats [] as a verified-clear scene (see FrameDetector docs).
  @override
  Future<List<Detection>?> detect(CameraImage image, int rotation) async {
    final Uint8List? jpeg = await FrameCodec.jpegFromCameraImage(image);
    final req = http.MultipartRequest('POST', _uri)
      ..fields['width'] = '${image.width}'
      ..fields['height'] = '${image.height}'
      ..fields['rotation'] = '$rotation';
    if (jpeg != null) {
      req.files.add(http.MultipartFile.fromBytes('jpeg', jpeg,
          filename: 'f.jpg'));
    } else {
      // Fallback: the raw planes, exactly as before the codec existed. The
      // server accepts either shape, so an old server or a phone without the
      // native encoder still works.
      final y = image.planes[0], u = image.planes[1], v = image.planes[2];
      req
        ..fields['yStride'] = '${y.bytesPerRow}'
        ..fields['uvStride'] = '${u.bytesPerRow}'
        ..fields['uvPixelStride'] = '${u.bytesPerPixel ?? 1}'
        ..files.add(http.MultipartFile.fromBytes('y', y.bytes, filename: 'y'))
        ..files.add(http.MultipartFile.fromBytes('u', u.bytes, filename: 'u'))
        ..files.add(http.MultipartFile.fromBytes('v', v.bytes, filename: 'v'));
    }
    try {
      final streamed = await _client.send(req).timeout(_inferTimeout);
      final body = await streamed.stream.bytesToString();
      if (streamed.statusCode != 200) {
        // ignore: avoid_print
        print('BlindAssist remote infer HTTP ${streamed.statusCode}');
        return null;
      }
      final data = jsonDecode(body) as Map<String, dynamic>;
      final list = (data['detections'] as List).cast<Map<String, dynamic>>();
      return [
        for (final d in list)
          Detection(
            d['name'] as String,
            (d['conf'] as num).toDouble(),
            (d['x1'] as num).toDouble(),
            (d['y1'] as num).toDouble(),
            (d['x2'] as num).toDouble(),
            (d['y2'] as num).toDouble(),
            // absent on an older server -> false, i.e. today's behaviour
            trustedName: d['trusted_name'] == true,
          ),
      ];
    } on TimeoutException {
      // a slow/lost frame must never wedge the camera loop
      // ignore: avoid_print
      print('BlindAssist remote infer timeout');
      return null;
    } catch (e) {
      // ignore: avoid_print
      print('BlindAssist remote infer failed: $e');
      return null;
    }
  }

  @override
  void close() => _client.close();
}
