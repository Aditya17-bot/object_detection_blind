// RemoteDetector protocol tests — MockClient, no network, no camera.
// The one rule under test that matters for safety: failure returns NULL,
// never an empty list (an empty list means "verified clear scene").
import 'dart:convert';
import 'dart:typed_data';

import 'package:blindassist/remote_detector.dart';
import 'package:camera/camera.dart';
import 'package:camera_platform_interface/camera_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

CameraImage _fakeImage() {
  return CameraImage.fromPlatformInterface(CameraImageData(
    format: const CameraImageFormat(ImageFormatGroup.yuv420, raw: 35),
    planes: [
      CameraImagePlane(
          bytes: Uint8List(64), bytesPerRow: 8, bytesPerPixel: 1),
      CameraImagePlane(
          bytes: Uint8List(16), bytesPerRow: 4, bytesPerPixel: 1),
      CameraImagePlane(
          bytes: Uint8List(16), bytesPerRow: 4, bytesPerPixel: 1),
    ],
    height: 8,
    width: 8,
  ));
}

RemoteDetector _detector(MockClient client) =>
    RemoteDetector('example.test', 5001, client: client);

void main() {
  test('successful response parses detections', () async {
    final client = MockClient((req) async {
      expect(req.url.path, '/infer');
      return http.Response(
          jsonEncode({
            'detections': [
              {
                'name': 'person',
                'conf': 0.9,
                'x1': 0.1,
                'y1': 0.2,
                'x2': 0.3,
                'y2': 0.4,
              }
            ]
          }),
          200);
    });
    final dets = await _detector(client).detect(_fakeImage(), 90);
    expect(dets, isNotNull);
    expect(dets!.length, 1);
    expect(dets[0].name, 'person');
    expect(dets[0].confidence, closeTo(0.9, 1e-9));
    expect(dets[0].x1, closeTo(0.1, 1e-9));
    expect(dets[0].y2, closeTo(0.4, 1e-9));
  });

  test('empty detections is an empty list, NOT null', () async {
    final client = MockClient(
        (req) async => http.Response(jsonEncode({'detections': []}), 200));
    final dets = await _detector(client).detect(_fakeImage(), 0);
    expect(dets, isNotNull);
    expect(dets, isEmpty);
  });

  test('HTTP error returns null (no data), never empty list', () async {
    final client =
        MockClient((req) async => http.Response('boom', 500));
    expect(await _detector(client).detect(_fakeImage(), 0), isNull);
  });

  test('malformed body returns null', () async {
    final client =
        MockClient((req) async => http.Response('not json', 200));
    expect(await _detector(client).detect(_fakeImage(), 0), isNull);
  });

  test('network exception returns null', () async {
    final client = MockClient(
        (req) async => throw const SocketExceptionLike('unreachable'));
    expect(await _detector(client).detect(_fakeImage(), 0), isNull);
  });

  test('request carries frame geometry and rotation fields', () async {
    late Map<String, String> seen;
    final client = MockClient((req) async {
      // MultipartRequest body: assert on the fields via the request headers
      // is fragile — instead RemoteDetector puts geometry in fields, which
      // MockClient exposes only via the encoded body. Parse the essentials.
      final body = utf8.decode(req.bodyBytes, allowMalformed: true);
      seen = {
        for (final f in ['width', 'height', 'yStride', 'rotation'])
          f: RegExp('name="$f"\\r\\n\\r\\n(\\d+)').firstMatch(body)?.group(1) ??
              'MISSING'
      };
      return http.Response(jsonEncode({'detections': []}), 200);
    });
    await _detector(client).detect(_fakeImage(), 90);
    expect(seen, {
      'width': '8',
      'height': '8',
      'yStride': '8',
      'rotation': '90',
    });
  });

  test('load() succeeds on healthy server and reads custom flag', () async {
    final client = MockClient((req) async {
      expect(req.url.path, '/health');
      return http.Response(jsonEncode({'ok': true, 'custom': false}), 200);
    });
    final d = _detector(client);
    await d.load();
    expect(d.customModelAvailable, false);
  });

  test('load() throws a clear error when the server is unreachable', () async {
    final client = MockClient(
        (req) async => throw const SocketExceptionLike('no route'));
    expect(
      () => _detector(client).load(),
      throwsA(isA<StateError>().having(
          (e) => e.message, 'message', contains('infer_server.py'))),
    );
  });
}

/// Stand-in for SocketException without importing dart:io in a test that
/// should stay platform-agnostic.
class SocketExceptionLike implements Exception {
  final String message;
  const SocketExceptionLike(this.message);
  @override
  String toString() => 'SocketExceptionLike: $message';
}
