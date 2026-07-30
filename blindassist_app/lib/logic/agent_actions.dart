// BlindAssist — agent layer, pure Dart half. Mirror of agent.py's registry,
// validator and action model.
//
// WHY A HAND-MIRRORED REGISTRY
// ----------------------------
// agent.py exists because the 13 capabilities were declared in four places and
// had already drifted. Re-typing them here looks like the same mistake — it
// isn't, because `capabilities.json` is committed and `test/agent_test.dart`
// asserts this table against it field by field. The moment Python's TOOLS
// changes, the Dart suite goes red. That is the project's existing
// Python/Dart mirroring pattern (position, decision, voice), not new debt.
//
// THE AUTHORITY BOUNDARY holds on the phone exactly as it does on the laptop:
// the server may return a tool name and an argument, and nothing else. Every
// spoken word still comes from decision.dart / position.dart or from
// [askTemplates] below. A malformed, unknown or out-of-enum action is dropped,
// never spoken and never guessed at.
library;

import 'voice_commands.dart';

/// The ONLY strings this layer may put in the user's ear. Byte-identical to
/// agent.ASK_TEMPLATES — the model picks a key, it never writes a sentence.
const Map<String, String> askTemplates = {
  'unknown': "Sorry, I can't do that. I can find things, describe the "
      'scene, count them, read text, or check your path.',
  'not_understood': "Sorry, I didn't catch that. Say it again?",
  'which_object': 'Which object should I look for?',
  'unsupported': "That control isn't available here.",
  'listening': 'Yes?',
  'working': 'One moment',
};
const String defaultAsk = 'unknown';

/// One capability. [name] is byte-identical to the action string parseCommand
/// already emits, so tier 0 and tier 1 produce the same shape.
class ToolSpec {
  const ToolSpec(this.name,
      {this.arg,
      this.required = false,
      this.internal = false,
      this.examples = const []});

  final String name;
  final String? arg; // null | 'class' | 'onoff' | 'template'
  final bool required;
  final bool internal; // true -> the model may never select it
  final List<String> examples;
}

/// Mirror of agent.TOOLS, in the same order (the manifest test depends on it).
const List<ToolSpec> kTools = [
  ToolSpec('walk', examples: ['walk mode', 'walk']),
  ToolSpec('find',
      arg: 'class', required: true, examples: ['find bottle', 'find the door']),
  ToolSpec('describe', examples: ['describe', 'describe scene', 'summary']),
  ToolSpec('count', arg: 'class', required: true, examples: ['how many chairs']),
  ToolSpec('recall',
      arg: 'class', required: true, examples: ['where is the cup']),
  ToolSpec('path', examples: ['clear path', 'which way']),
  ToolSpec('read', examples: ['read', 'read text']),
  ToolSpec('clock', examples: ['clock mode']),
  ToolSpec('zones', examples: ['zone mode']),
  ToolSpec('sonar', arg: 'onoff', examples: ['sonar', 'sonar on', 'sonar off']),
  ToolSpec('mute', arg: 'onoff', required: true, examples: ['mute', 'unmute']),
  ToolSpec('stop', examples: ['stop']),
  ToolSpec('repeat', examples: ['repeat', 'say again']),
  ToolSpec('abstain', arg: 'template'),
  ToolSpec('ask', internal: true, examples: ['assistant']),
];

final Map<String, ToolSpec> kToolsByName = {
  for (final spec in kTools) spec.name: spec
};

/// Keys the server (or a model) might use for the argument. Forgiving on the
/// way in, strict on the way out — the value still has to survive the enum.
const List<String> _argKeys = [
  'arg', 'object', 'value', 'target', 'class', 'name', 'template', 'state'
];

/// One validated capability call.
class AgentAction {
  const AgentAction(this.tool, [this.arg]);

  final String tool;
  final String? arg;

  /// The (action, target) shape main.dart's dispatcher already speaks.
  VoiceCommand toVoiceCommand() => (action: tool, target: arg);

  @override
  String toString() => arg == null ? tool : '$tool($arg)';

  @override
  bool operator ==(Object other) =>
      other is AgentAction && other.tool == tool && other.arg == arg;

  @override
  int get hashCode => Object.hash(tool, arg);
}

/// What the router decided. [source] is grammar | llm | abstain | local —
/// 'local' is the phone's own offline fallback when the server is unreachable.
class AgentRouteResult {
  const AgentRouteResult({
    this.actions = const [],
    this.source = 'abstain',
    this.ask,
    this.latencyMs = 0,
    this.error,
  });

  final List<AgentAction> actions;
  final String source;
  final String? ask;
  final double latencyMs;
  final String? error;

  /// The spoken template for an abstention, or null.
  String? get message => ask == null ? null : askTemplates[ask];
}

/// One raw action map -> AgentAction, or null if it must be rejected.
///
/// Rejects: unknown tool names, internal tools, missing required arguments,
/// class names the detector does not know, and anything outside an argument's
/// enum. Object names resolve through the PARSER's own vocabulary, so the
/// remote tier cannot name an object the local tier would refuse.
AgentAction? validateAction(Object? raw) {
  if (raw is! Map) return null;
  final name = raw['tool'] ?? raw['name'];
  if (name is! String) return null;
  final spec = kToolsByName[name.trim().toLowerCase()];
  if (spec == null || spec.internal) return null;

  final source = raw['args'] is Map ? raw['args'] as Map : raw;
  String? arg;
  for (final key in _argKeys) {
    final v = source[key];
    if (v is String && v.trim().isNotEmpty) {
      arg = v.trim();
      break;
    }
  }

  if (spec.arg == null) return AgentAction(spec.name); // stray args dropped
  if (arg == null) return spec.required ? null : AgentAction(spec.name);
  if (spec.arg == 'class') {
    final resolved = resolveClass(arg);
    return resolved == null ? null : AgentAction(spec.name, resolved);
  }
  arg = arg.toLowerCase();
  if (spec.arg == 'onoff' && arg != 'on' && arg != 'off') return null;
  if (spec.arg == 'template' && !askTemplates.containsKey(arg)) return null;
  return AgentAction(spec.name, arg);
}

/// Whole server response body -> route result. Never throws: this runs on the
/// voice path, and an exception there kills speech recognition for the rest of
/// the session (the "clock mode" bug agent.py's docstring records).
AgentRouteResult parseRouteResponse(Map<String, dynamic> body,
    {int maxActions = 2}) {
  final source = body['source'] is String ? body['source'] as String : 'abstain';
  final latency =
      body['latency_ms'] is num ? (body['latency_ms'] as num).toDouble() : 0.0;
  final error = body['error'] is String ? body['error'] as String : null;

  final raw = body['actions'];
  final actions = <AgentAction>[];
  if (raw is List) {
    for (final item in raw.take(maxActions)) {
      final action = validateAction(item);
      // One bad action invalidates the whole reply: executing the half we
      // understood would carry out part of a request we could not verify.
      if (action == null) {
        return AgentRouteResult(
            ask: defaultAsk, latencyMs: latency, error: 'rejected action $item');
      }
      if (action.tool == 'abstain') {
        return AgentRouteResult(
            source: 'abstain',
            ask: action.arg ?? defaultAsk,
            latencyMs: latency);
      }
      actions.add(action);
    }
  }
  if (actions.isEmpty) {
    final ask = body['ask'];
    return AgentRouteResult(
        source: source == 'abstain' ? 'abstain' : source,
        ask: (ask is String && askTemplates.containsKey(ask))
            ? ask
            : defaultAsk,
        latencyMs: latency,
        error: error);
  }
  return AgentRouteResult(
      actions: actions, source: source, latencyMs: latency, error: error);
}
