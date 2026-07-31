// Agent layer tests — the Dart half of the two-tier router.
//
// The first group is the CROSS-LANGUAGE CONTRACT: kTools is asserted field by
// field against the committed capabilities.json that agent.py generates. That
// is what makes a hand-mirrored registry safe — Python cannot change a tool,
// an argument or an enum without turning this suite red.
//
// The rest pins the authority boundary on the phone: a server reply is
// untrusted input, and anything malformed, unknown or out-of-enum becomes an
// abstention. No network in any of it.
import 'dart:convert';
import 'dart:io';

import 'package:blindassist/agent_client.dart';
import 'package:blindassist/logic/agent_actions.dart';
import 'package:blindassist/logic/position.dart';
import 'package:blindassist/logic/voice_commands.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> _manifest() {
  // flutter test runs from the package root; the manifest lives in the Python
  // project one level up and is committed alongside it.
  final file = File('../capabilities.json');
  expect(file.existsSync(), isTrue,
      reason: 'capabilities.json missing — run python agent.py '
          '--write-manifest in the project root');
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

AgentClient _client(MockClient client) =>
    AgentClient('example.test', 5001, client: client);

http.Response _ok(Map<String, dynamic> body) =>
    http.Response(jsonEncode(body), 200,
        headers: {'content-type': 'application/json'});

void main() {
  group('capability registry matches capabilities.json', () {
    test('same tools, same order, same arguments', () {
      final tools = (_manifest()['tools'] as List).cast<Map<String, dynamic>>();
      expect(kTools.length, tools.length);
      for (var i = 0; i < tools.length; i++) {
        final want = tools[i];
        final got = kTools[i];
        expect(got.name, want['name']);
        expect(got.arg, want['arg'], reason: 'arg of ${got.name}');
        expect(got.required, want['required'], reason: 'required ${got.name}');
        expect(got.internal, want['internal'], reason: 'internal ${got.name}');
        expect(got.examples, (want['examples'] as List).cast<String>(),
            reason: 'examples of ${got.name}');
      }
    });

    test('same ask templates, word for word', () {
      // These are the only strings the layer may speak, so a drifted template
      // is a drifted user-facing behaviour, not a cosmetic difference.
      expect(askTemplates,
          (_manifest()['ask_templates'] as Map).cast<String, String>());
    });

    test('class enum matches the detector class list on both sides', () {
      final enums = (_manifest()['enums'] as Map)['class'] as List;
      expect(enums.cast<String>(), (targetClasses.toList()..sort()));
    });
  });

  group('validateAction — the authority boundary', () {
    test('accepts a well-formed action and resolves synonyms', () {
      expect(validateAction({'tool': 'find', 'arg': 'sofa'}),
          const AgentAction('find', 'couch'));
      expect(validateAction({'tool': 'find', 'args': {'value': 'phones'}}),
          const AgentAction('find', 'cell phone'));
    });

    test('rejects unknown tools, unknown classes and bad enums', () {
      expect(validateAction({'tool': 'launch_missiles'}), isNull);
      expect(validateAction({'tool': 'find', 'arg': 'unicorn'}), isNull);
      expect(validateAction({'tool': 'mute', 'arg': 'maybe'}), isNull);
      expect(validateAction({'tool': 'abstain', 'arg': 'made_up'}), isNull);
      expect(validateAction('find the bottle'), isNull); // prose, not an action
      expect(validateAction(null), isNull);
    });

    test('rejects the internal dictation trigger', () {
      // 'ask' opens the microphone window; the router may not drive it.
      expect(validateAction({'tool': 'ask'}), isNull);
    });

    test('required argument missing is a rejection, optional one is not', () {
      expect(validateAction({'tool': 'find'}), isNull);
      expect(validateAction({'tool': 'count'}), isNull);
      expect(validateAction({'tool': 'sonar'}), const AgentAction('sonar'));
      expect(validateAction({'tool': 'describe', 'arg': 'chair'}),
          const AgentAction('describe')); // stray argument dropped
    });

    test('every accepted class is one parseCommand would also accept', () {
      for (final name in targetClasses) {
        final action = validateAction({'tool': 'find', 'arg': name});
        expect(action, isNotNull, reason: name);
        expect(resolveClass(action!.arg), action.arg);
      }
    });
  });

  group('parseRouteResponse', () {
    test('actions survive and keep their order', () {
      final result = parseRouteResponse({
        'source': 'llm',
        'latency_ms': 1234.5,
        'actions': [
          {'tool': 'sonar', 'arg': 'on'},
          {'tool': 'find', 'arg': 'door'},
        ],
      });
      expect(result.source, 'llm');
      expect(result.latencyMs, 1234.5);
      expect(result.actions,
          [const AgentAction('sonar', 'on'), const AgentAction('find', 'door')]);
      expect(result.message, isNull);
    });

    test('an abstention carries its template, not model prose', () {
      final result = parseRouteResponse({
        'source': 'abstain',
        'ask': 'unknown',
        'actions': const [],
      });
      expect(result.actions, isEmpty);
      expect(result.message, askTemplates['unknown']);
    });

    test('one bad action invalidates the whole reply', () {
      // Executing only the half we understood would carry out part of a
      // request we could not verify.
      final result = parseRouteResponse({
        'source': 'llm',
        'actions': [
          {'tool': 'find', 'arg': 'bottle'},
          {'tool': 'teleport'},
        ],
      });
      expect(result.actions, isEmpty);
      expect(result.message, askTemplates['unknown']);
    });

    test('unknown ask key falls back to a template that exists', () {
      final result =
          parseRouteResponse({'source': 'abstain', 'ask': 'nonsense'});
      expect(result.message, askTemplates[defaultAsk]);
    });

    test('at most two actions are taken', () {
      final result = parseRouteResponse({
        'source': 'llm',
        'actions': [
          {'tool': 'walk'},
          {'tool': 'describe'},
          {'tool': 'read'},
        ],
      });
      expect(result.actions.length, 2);
    });

    test('garbage body does not throw', () {
      // An exception here would kill the voice thread for the whole session.
      expect(parseRouteResponse({'actions': 'nope'}).actions, isEmpty);
      expect(parseRouteResponse(const {}).message, isNotNull);
    });
  });

  group('AgentClient — fail-safe transport', () {
    test('posts the utterance as JSON to /agent', () async {
      late String seenBody;
      final client = _client(MockClient((req) async {
        expect(req.url.path, '/agent');
        seenBody = req.body;
        return _ok({
          'source': 'grammar',
          'actions': [
            {'tool': 'describe', 'arg': null}
          ],
        });
      }));
      final result = await client.route('what is around me');
      expect(jsonDecode(seenBody)['text'], 'what is around me');
      expect(result!.actions, [const AgentAction('describe')]);
    });

    test('HTTP error returns null — no data, never a guessed action', () async {
      final client = _client(MockClient((_) async => http.Response('nope', 500)));
      expect(await client.route('find the door'), isNull);
    });

    test('unreachable server returns null instead of throwing', () async {
      // Throwing would end speech recognition for the rest of the session.
      final client =
          _client(MockClient((_) async => throw const SocketException('down')));
      expect(await client.route('find the door'), isNull);
    });

    test('non-JSON body returns null', () async {
      final client = _client(MockClient((_) async => http.Response('<html>', 200)));
      expect(await client.route('find the door'), isNull);
    });

    test('the phone ships its own scene state', () async {
      // The laptop has no engine: without this the LLM would answer a question
      // about the room from nothing, which is how invention starts.
      Map<String, dynamic>? sent;
      final client = _client(MockClient((request) async {
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response('{"source":"chat","say":"All clear."}', 200);
      }));
      await client.route('how does it look',
          state: {'mode': 'walk', 'visible': []});
      expect(sent!['text'], 'how does it look');
      expect(sent!['state'], {'mode': 'walk', 'visible': []});
    });
  });

  group('chat replies', () {
    // The one deliberate hole in the authority boundary (2026-07-31): the
    // laptop's LLM may author a REPLY. These pin how wide the hole is.
    test('a say reply is carried through and spoken', () {
      final r = parseRouteResponse(
          {'source': 'chat', 'say': 'There is a chair on your left.'});
      expect(r.source, 'chat');
      expect(r.actions, isEmpty);
      expect(r.message, 'There is a chair on your left.');
    });

    test('actions win over chat', () {
      final r = parseRouteResponse({
        'source': 'llm',
        'say': 'Sure, looking now.',
        'actions': [
          {'tool': 'describe'}
        ],
      });
      expect(r.say, isNull);
      expect(r.actions.single.tool, 'describe');
    });

    test('junk say values are never spoken', () {
      for (final junk in <Object?>[
        '', '   ', 42, null, {'nested': 1}, '{"tool": "walk"}'
      ]) {
        final r = parseRouteResponse({'source': 'chat', 'say': junk});
        expect(r.say, isNull, reason: '$junk');
        expect(r.source, 'abstain', reason: '$junk');
      }
    });

    test('a long reply is cut at a sentence', () {
      final long = ('There is a chair on your left. ' * 20).trim();
      final r = parseRouteResponse({'source': 'chat', 'say': long});
      expect(r.say!.length, lessThanOrEqualTo(maxSayChars));
      expect(r.say, endsWith('.'));
    });
  });

  group('direction argument', () {
    test('aliases resolve, unknown directions are rejected', () {
      expect(validateAction({'tool': 'check', 'args': {'value': 'front'}})?.arg,
          'ahead');
      expect(validateAction({'tool': 'check', 'args': {'value': 'LEFT'}})?.arg,
          'left');
      expect(validateAction({'tool': 'check', 'args': {'value': 'behind'}}),
          isNull);
      // required argument: a bare check is not actionable
      expect(validateAction({'tool': 'check'}), isNull);
    });
  });
}
