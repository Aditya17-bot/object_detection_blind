// Discovery round-trip against an in-test loopback UDP responder — the same
// protocol infer_server.py's start_discovery_responder speaks.
import 'dart:convert';
import 'dart:io';

import 'package:blindassist/discovery.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('finds a responding server and reads its port', () async {
    final responder =
        await RawDatagramSocket.bind(InternetAddress.loopbackIPv4, 0);
    responder.listen((event) {
      if (event != RawSocketEvent.read) return;
      final dg = responder.receive();
      if (dg == null) return;
      if (utf8.decode(dg.data).trim() == 'BLINDASSIST_DISCOVER') {
        responder.send(
            utf8.encode('BLINDASSIST_INFER 5001'), dg.address, dg.port);
      }
    });

    final found = await discoverServer(
      address: InternetAddress.loopbackIPv4,
      discoveryPort: responder.port,
    );
    responder.close();
    expect(found, isNotNull);
    expect(found!.host, '127.0.0.1');
    expect(found.port, 5001);
  });

  test('ignores replies with a bad prefix or unparsable port', () async {
    final responder =
        await RawDatagramSocket.bind(InternetAddress.loopbackIPv4, 0);
    responder.listen((event) {
      if (event != RawSocketEvent.read) return;
      final dg = responder.receive();
      if (dg == null) return;
      responder.send(utf8.encode('SOMETHING_ELSE 5001'), dg.address, dg.port);
    });

    final found = await discoverServer(
      timeout: const Duration(milliseconds: 600),
      address: InternetAddress.loopbackIPv4,
      discoveryPort: responder.port,
    );
    responder.close();
    expect(found, isNull);
  });

  test('times out to null when nothing answers', () async {
    // a bound-but-silent socket guarantees the port is real yet mute
    final silent =
        await RawDatagramSocket.bind(InternetAddress.loopbackIPv4, 0);
    final found = await discoverServer(
      timeout: const Duration(milliseconds: 400),
      address: InternetAddress.loopbackIPv4,
      discoveryPort: silent.port,
    );
    silent.close();
    expect(found, isNull);
  });
}
