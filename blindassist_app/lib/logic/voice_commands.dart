// BlindAssist — voice command parsing. Direct port of voice.py's pure layer.
//
// parseCommand(text): recognized utterance -> (action, target) or null.
// grammarPhrases(): every phrase the recognizer should be able to hear —
// the Vosk recognizer is constrained to these, which makes the small
// offline model far more reliable than free dictation.
library;

import 'position.dart';

/// spoken word -> COCO class ("find phone" should just work)
const Map<String, String> synonyms = {
  'phone': 'cell phone',
  'mobile': 'cell phone',
  'table': 'dining table',
  'sofa': 'couch',
  'fridge': 'refrigerator',
  'television': 'tv',
  'plant': 'potted plant',
  'bag': 'backpack',
  'man': 'person',
  'woman': 'person',
};

final Map<String, String> _findable = {
  for (final name in targetClasses) name: name,
  ...synonyms,
};

/// A parsed voice command: action is walk / find / describe.
typedef VoiceCommand = ({String action, String? target});

/// Longest findable phrase inside [rest], mapped to its COCO class, or null.
/// Longest first so "cell phone" beats "phone".
String? _matchObject(String rest) {
  final phrases = _findable.keys.toList()
    ..sort((a, b) => b.length.compareTo(a.length));
  for (final phrase in phrases) {
    if (rest.contains(phrase)) return _findable[phrase];
  }
  return null;
}

/// Recognized utterance -> command, or null if not understood. Actions:
/// walk / find / describe / clock / zones / recall. Tolerant of filler words:
/// "please find the bottle" works.
VoiceCommand? parseCommand(String text) {
  final words = text.toLowerCase().split(RegExp(r'\s+'))
    ..removeWhere((w) => w.isEmpty);
  if (words.isEmpty) return null;
  if (words.contains('describe') ||
      words.contains('scene') ||
      words.contains('summary')) {
    return (action: 'describe', target: null);
  }
  if (words.contains('clock')) return (action: 'clock', target: null);
  if (words.contains('zone') || words.contains('zones')) {
    return (action: 'zones', target: null);
  }
  if (words.contains('path') ||
      (words.contains('which') && words.contains('way'))) {
    return (action: 'path', target: null); // clear-path finder
  }
  if (words.contains('read')) {
    return (action: 'read', target: null); // OCR: read printed text aloud
  }
  final manyIdx = words.indexOf('many'); // count query: "how many chairs"
  if (words.contains('how') && manyIdx >= 0) {
    final obj = _matchObject(words.sublist(manyIdx + 1).join(' '));
    if (obj != null) return (action: 'count', target: obj);
  }
  final whereIdx = words.indexOf('where'); // object-memory query
  if (whereIdx >= 0) {
    final obj = _matchObject(words.sublist(whereIdx + 1).join(' '));
    if (obj != null) return (action: 'recall', target: obj);
  }
  if (words.contains('walk')) return (action: 'walk', target: null);
  final findIdx = words.indexOf('find');
  if (findIdx >= 0) {
    final obj = _matchObject(words.sublist(findIdx + 1).join(' '));
    if (obj != null) return (action: 'find', target: obj);
  }
  return null;
}

/// Every phrase the recognizer should be able to hear.
List<String> grammarPhrases() {
  final phrases = ['walk mode', 'walk', 'describe', 'describe scene', 'summary',
    'clock mode', 'zone mode', 'clear path', 'which way', 'read', 'read text'];
  final names = _findable.keys.toList()..sort();
  for (final name in names) {
    phrases.add('find $name');
    phrases.add('find the $name');
    phrases.add('where is $name');
    phrases.add('where is the $name');
    phrases.add('how many $name');
  }
  return phrases;
}
