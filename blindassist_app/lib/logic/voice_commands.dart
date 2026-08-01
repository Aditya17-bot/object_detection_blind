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

/// Naive English plural of the LAST word ('cell phone' -> 'cell phones').
/// Good enough for the constrained grammar; irregulars are added explicitly.
String _plural(String phrase) {
  if (phrase.endsWith('s') ||
      phrase.endsWith('sh') ||
      phrase.endsWith('ch') ||
      phrase.endsWith('x')) {
    return '${phrase}es';
  }
  return '${phrase}s';
}

final Map<String, String> _findable = () {
  final base = {
    for (final name in targetClasses) name: name,
    ...synonyms,
  };
  // plurals: "how many chairs" is what people actually say — without these
  // the constrained grammar can't even HEAR the plural form
  return {
    ...base,
    for (final e in base.entries) _plural(e.key): e.value,
    'people': 'person',
  };
}();

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

/// Spoken words -> COCO class name, or null. Handles synonyms and plurals
/// ('sofas' -> 'couch'). Public so the agent layer can validate a tool
/// argument against exactly the vocabulary this parser accepts — the remote
/// tier must never be able to name an object the local tier would refuse.
/// Mirror of voice.resolve_class.
String? resolveClass(String? text) {
  if (text == null) return null;
  final t = text.trim().toLowerCase();
  if (t.isEmpty) return null;
  return _findable[t] ?? _matchObject(t);
}

/// Saying one of these opens the open-dictation window: the recognizer's
/// grammar is a closed list, so free speech is not mis-heard, it is never
/// heard at all. An explicit trigger keeps tier 0 instant and untouched —
/// only an utterance the user deliberately marked as a question takes the
/// slow open path. Mirror of voice.TRIGGER_WORDS.
const List<String> triggerWords = ['assistant', 'question'];

/// Directional query vocabulary ("what's on my left", "anything in front of
/// me"). Both halves must appear — a direction AND a question word — so a bare
/// "left" heard mid-sentence never fires a query. Mirror of
/// voice._DIRECTION_WORDS / voice._CHECK_WORDS.
const Map<String, String> _directionWords = {
  'left': 'left',
  'right': 'right',
  'ahead': 'ahead',
  'front': 'ahead',
  'forward': 'ahead',
};
const List<String> _checkWords = [
  'anything', 'something', 'what', 'whats', "what's", 'check', 'there',
  'see', 'is'
];

/// "left" and "right" are ordinary English words; "how much battery is LEFT"
/// routed to check(left) in the 2026-08-01 evaluation run. They only count as
/// a direction when a positional word introduces them. "ahead"/"front"/
/// "forward" need no such guard. Mirror of voice._DIRECTION_LEAD.
const Set<String> _unambiguousDirections = {'ahead', 'front', 'forward'};
const Set<String> _directionLead = {
  'my', 'the', 'on', 'to', 'your', 'check', 'toward', 'towards'
};

String? _findDirection(List<String> words) {
  for (var i = 0; i < words.length; i++) {
    final word = words[i];
    if (!_directionWords.containsKey(word)) continue;
    if (_unambiguousDirections.contains(word) ||
        (i > 0 && _directionLead.contains(words[i - 1]))) {
      return _directionWords[word];
    }
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
  if (words.contains('stop')) {
    return (action: 'stop', target: null); // halt current speech
  }
  if (words.contains('repeat') || words.contains('again')) {
    return (action: 'repeat', target: null); // last announcement again
  }
  if (words.contains('sonar')) { // hands-free toggle for the earphone beeps
    final target =
        words.contains('on') ? 'on' : (words.contains('off') ? 'off' : null);
    return (action: 'sonar', target: target);
  }
  if (words.contains('unmute')) return (action: 'mute', target: 'off');
  if (words.contains('mute')) return (action: 'mute', target: 'on');
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
  // Directional query, AFTER find so "find the door on my left" still finds.
  // Deliberately on-device: "is there anything in front of me" is the question
  // this system exists to answer, and it must work with no server and no LLM.
  final direction = _findDirection(words);
  if (direction != null && words.any(_checkWords.contains)) {
    return (action: 'check', target: direction);
  }
  // LAST, deliberately: every existing command keeps its exact precedence, so
  // the trigger can only fire on an utterance nothing else claimed.
  if (words.any(triggerWords.contains)) return (action: 'ask', target: null);
  return null;
}

/// Every phrase the recognizer should be able to hear.
List<String> grammarPhrases() {
  final phrases = ['walk mode', 'walk', 'describe', 'describe scene', 'summary',
    'clock mode', 'zone mode', 'clear path', 'which way', 'read', 'read text',
    'stop', 'repeat', 'say again', 'sonar', 'sonar on', 'sonar off',
    'mute', 'unmute', ...triggerWords];
  for (final spoken in ['on my left', 'on my right', 'in front of me',
    'ahead']) {
    phrases.add('what is $spoken');
    phrases.add('whats $spoken');
    phrases.add('is there anything $spoken');
    phrases.add('anything $spoken');
  }
  phrases.addAll(['check left', 'check right', 'check ahead']);
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
