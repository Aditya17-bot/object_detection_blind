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
/// Raised from 5 s on 2026-09-05. Tier 1 measures ~0.5-1.1 s with the GPU
/// idle, but 6.8-8.0 s while frames are streaming: the router model and the
/// two YOLO models share 4 GB of VRAM. At 5 s every real question the user
/// asked mid-walk timed out, which is indistinguishable from a broken app.
/// The wait is still poor and the real fix is not to make both fight for one
/// GPU -- see the notes in CLAUDE.md -- but a slow answer beats none.
const Duration _agentTimeout = Duration(seconds: 12);

class AgentClient {
  /// [client] is injectable for tests (package:http/testing MockClient).
  AgentClient(String host, int port, {http.Client? client})
      : _uri = Uri.parse('http://$host:$port/agent'),
        _phraseUri = Uri.parse('http://$host:$port/phrase'),
        _client = client ?? http.Client();

  final Uri _uri;
  final Uri _phraseUri;
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

  /// Ask the laptop to reword one remembered sighting.
  ///
  /// The phone owns the memory and composes [fallback] itself, so this is
  /// pure polish: the server verifies every object and number in the model's
  /// reply against the record and returns the fallback when anything fails.
  /// Returns null on no data, and the caller then speaks its own sentence —
  /// so an absent laptop, a slow model and a hallucination are all the same
  /// outcome, which is the point.
  ///
  /// The timeout is short on purpose. This is a spoken answer to a question
  /// the user just asked; waiting seconds for nicer wording is a worse answer
  /// than plain wording now.
  Future<String?> phrase({
    required String object,
    required List<String> near,
    required List<String> context,
    required String agoPhrase,
    required String fallback,
  }) async {
    try {
      final r = await _client
          .post(_phraseUri,
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'object': object,
                'near': near,
                'context': context,
                'ago_phrase': agoPhrase,
                'fallback': fallback,
              }))
          .timeout(const Duration(milliseconds: 1500));
      if (r.statusCode != 200) return null;
      final body = jsonDecode(r.body);
      if (body is! Map) return null;
      final text = body['text'];
      return text is String && text.trim().isNotEmpty ? text.trim() : null;
    } catch (_) {
      // never throws: this runs on the speech path
      return null;
    }
  }
}
