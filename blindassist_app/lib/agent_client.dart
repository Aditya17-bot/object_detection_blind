// BlindAssist — agent client. Sends an utterance the phone's own grammar could
// not turn into a command to POST /agent on the tethered laptop, and gets back
// a validated capability call.
//
// LOCAL FIRST, ALWAYS. main.dart only reaches for this after parseCommand has
// already failed, so every trained phrase still routes on-device in ~0 ms with
// no network and no model — the two-tier property agent.py's AgentRouter has,
// with the tier boundary drawn at the Wi-Fi link. Nothing that works today
// starts depending on the laptop being up.
//
// FAIL-SAFE, same rule as RemoteDetector.detect: [route] returns null for NO
// DATA (unreachable, timeout, HTTP error, unparseable body) and never a
// fabricated action. Degrade to fewer capabilities, never to a wrong one — a
// wrong capability on a blind user's phone is worse than a spoken "I can't do
// that".
import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'logic/agent_actions.dart';

/// Voice queries are on-demand, not inside the ~1 s continuous-guidance loop,
/// so this can be longer than the frame timeout — a local LLM route costs 1-2 s
/// on the laptop. It still has to end well before the user assumes the app is
/// dead and repeats themselves.
const Duration _agentTimeout = Duration(seconds: 5);

class AgentClient {
  /// [client] is injectable for tests (package:http/testing MockClient).
  AgentClient(String host, int port, {http.Client? client})
      : _uri = Uri.parse('http://$host:$port/agent'),
        _client = client ?? http.Client();

  final Uri _uri;
  final http.Client _client;

  /// Utterance -> route result, or null when the server produced NO data.
  /// Never throws: this is called from the voice thread's callback, where an
  /// exception silently ends speech recognition for the whole session.
  /// [state] is this phone's deterministic scene summary
  /// (GuidanceEngine.stateSummary). The laptop has no engine and no frame
  /// memory of its own, so without it a question about the scene would be
  /// answered from nothing — which is exactly how a model starts inventing.
  Future<AgentRouteResult?> route(String text,
      {Map<String, dynamic>? state}) async {
    try {
      final response = await _client
          .post(_uri,
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'text': text, 'state': ?state}))
          .timeout(_agentTimeout);
      if (response.statusCode != 200) {
        // ignore: avoid_print
        print('BlindAssist agent HTTP ${response.statusCode}');
        return null;
      }
      final body = jsonDecode(response.body);
      if (body is! Map<String, dynamic>) return null;
      return parseRouteResponse(body);
    } on TimeoutException {
      // ignore: avoid_print
      print('BlindAssist agent timeout');
      return null;
    } catch (e) {
      // ignore: avoid_print
      print('BlindAssist agent failed: $e');
      return null;
    }
  }

  void close() => _client.close();
}
