// BlindAssist — UDP auto-discovery of the laptop inference server.
//
// The hotspot hands the laptop a different IP every session; baking it into
// config.dart meant editing source + rebuilding the APK each time. Instead:
// broadcast "BLINDASSIST_DISCOVER" on the LAN, infer_server.py replies
// "BLINDASSIST_INFER <port>", and the server's IP is simply the source
// address of the reply. Runs at startup only — never per frame.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

const int kDiscoveryPort = 5002;
const String _discoverMsg = 'BLINDASSIST_DISCOVER';
const String _replyPrefix = 'BLINDASSIST_INFER ';

class DiscoveredServer {
  final String host;
  final int port;
  const DiscoveredServer(this.host, this.port);
}

/// Broadcast targets: the limited broadcast plus each interface's directed
/// broadcast. Android hotspot mode routes 255.255.255.255 out the CELLULAR
/// interface, so a phone acting as the hotspot never reaches the laptop with
/// the limited broadcast alone — the directed one (e.g. 10.250.253.255) goes
/// out swlan0. dart:io exposes no netmask, so /24 is assumed (Android hotspot
/// subnets are /24).
Future<List<InternetAddress>> _broadcastTargets() async {
  final targets = <InternetAddress>[InternetAddress('255.255.255.255')];
  try {
    final ifaces = await NetworkInterface.list(
        includeLoopback: false, type: InternetAddressType.IPv4);
    for (final iface in ifaces) {
      for (final addr in iface.addresses) {
        final parts = addr.address.split('.');
        if (parts.length != 4) continue;
        final directed = '${parts[0]}.${parts[1]}.${parts[2]}.255';
        if (!targets.any((t) => t.address == directed)) {
          targets.add(InternetAddress(directed));
        }
      }
    }
  } catch (_) {
    // interface enumeration is best-effort; limited broadcast still goes out
  }
  return targets;
}

/// Broadcast a discovery ping and wait for the first valid server reply.
/// Returns null when nothing answered within [timeout] (caller falls back to
/// the baked-in config host). [address] overrides the broadcast target so
/// tests can run against a loopback responder.
Future<DiscoveredServer?> discoverServer({
  Duration timeout = const Duration(seconds: 2),
  InternetAddress? address,
  int discoveryPort = kDiscoveryPort,
}) async {
  RawDatagramSocket? socket;
  try {
    socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
    socket.broadcastEnabled = true;
    final targets =
        address != null ? [address] : await _broadcastTargets();
    final completer = Completer<DiscoveredServer?>();

    final sub = socket.listen((event) {
      if (event != RawSocketEvent.read) return;
      final dg = socket!.receive();
      if (dg == null || completer.isCompleted) return;
      final text = utf8.decode(dg.data, allowMalformed: true).trim();
      if (!text.startsWith(_replyPrefix)) return;
      final port = int.tryParse(text.substring(_replyPrefix.length));
      if (port == null) return;
      completer.complete(DiscoveredServer(dg.address.address, port));
    });

    // ping a few times inside the window — a single UDP packet on a hotspot
    // that is still settling can simply vanish
    void ping() {
      for (final target in targets) {
        try {
          socket?.send(utf8.encode(_discoverMsg), target, discoveryPort);
        } catch (_) {
          // some targets can be unroutable (e.g. cellular /24) — keep going
        }
      }
    }

    final pinger =
        Timer.periodic(const Duration(milliseconds: 500), (_) => ping());
    ping();

    final result = await completer.future
        .timeout(timeout, onTimeout: () => null);
    pinger.cancel();
    await sub.cancel();
    return result;
  } catch (e) {
    // discovery is best-effort; the baked-in host still works without it
    // ignore: avoid_print
    print('BlindAssist discovery failed: $e');
    return null;
  } finally {
    socket?.close();
  }
}
