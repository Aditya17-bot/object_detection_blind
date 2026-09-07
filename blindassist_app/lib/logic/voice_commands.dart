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
  // wardrobe/window are namer-only classes (see position.dart). 'almirah' is
  // the everyday Indian-English word for a wardrobe.
  'cupboard': 'wardrobe',
  'almirah': 'wardrobe',
  'closet': 'wardrobe',
  // 'basket' alone is safe — no other class contains the word. Longer forms
  // are listed too because matching takes the LONGEST phrase, so 'laundry bag'
  // resolves to the basket and never to the generic 'bag' -> backpack.
  'laundry': 'laundry basket',
  'basket': 'laundry basket',
  'hamper': 'laundry basket',
  'laundry bag': 'laundry basket',
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
/// The findable phrase nearest the START of [rest], or null.
///
/// EARLIEST first, then longest. Longest-anywhere was the original rule and it
/// picks the wrong object the moment a second class word is present: the field
/// log has "find dustbin toilets" (a grammar-forced mishearing) resolving to
/// `toilet`, which is neither what was said nor even the first thing the
/// sentence names. The user's object is the one they said first after "find";
/// length still breaks ties at the same position so "cell phone" beats
/// "phone". Mirror of voice._match_object.
String? _matchObject(String rest) {
  String? best;
  var bestAt = -1;
  var bestLen = -1;
  for (final entry in _findable.entries) {
    final at = rest.indexOf(entry.key);
    if (at < 0) continue;
    if (best == null ||
        at < bestAt ||
        (at == bestAt && entry.key.length > bestLen)) {
      best = entry.value;
      bestAt = at;
      bestLen = entry.key.length;
    }
  }
  return best;
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
  // Every way back from mute, BEFORE the mute test so "voice on" is not read
  // as a request to mute. "unmute" is kept for typed and agent input; the
  // spoken forms exist because the shipped model cannot pronounce it (see
  // [kUnhearableWords]), which left a muted app with no voice route back.
  if (words.contains('unmute') ||
      words.contains('speak') ||
      (words.contains('on') &&
          (words.contains('voice') || words.contains('sound')))) {
    return (action: 'mute', target: 'off');
  }
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
  // Help BEFORE everything that could claim one of its words: "what can you
  // do" has "do" in it and "what can this app do" has "this". Deterministic on
  // purpose — llama3.2:1b abstained on every phrasing of this question, and a
  // capability list is the last thing that should be improvised.
  if (words.contains('help') ||
      (words.contains('what') &&
          words.contains('can') &&
          (words.contains('do') || words.contains('say')))) {
    return (action: 'help', target: null);
  }
  // Summarise BEFORE read, so "summarise this" is not swallowed by a stray
  // "read". "summary" alone stays with describe, which has owned it since the
  // scene-summary feature and is what users already say for it.
  if (words.contains('summarise') || words.contains('summarize')) {
    return (action: 'summarise', target: null);
  }
  if (words.contains('read')) {
    return (action: 'read', target: null); // OCR: read printed text aloud
  }
  // Colour and brightness, both BEFORE the object queries so "what colour is
  // the chair" is not dragged into find by the trailing class word.
  if (words.contains('colour') || words.contains('color')) {
    return (action: 'colour', target: null);
  }
  if (words.contains('bright') ||
      words.contains('dark') ||
      words.contains('light')) {
    return (action: 'light', target: null);
  }
  // Photo. Checked BEFORE the object queries so "take a picture" never gets
  // dragged into find/count by a stray class word later in the utterance.
  if (words.contains('picture') || words.contains('photo')) {
    return (action: 'photo', target: null);
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

/// Every DISTINCT object class named anywhere in [text]. Mirror of
/// `voice.named_classes`.
///
/// The signature of grammar-forced noise, and the reason it needs its own
/// detector: Vosk emits `[unk]` only for sound it cannot place at all, so
/// ambient noise that lands on trained words arrives with ZERO unplaceable
/// tokens and sails through the unknown-ratio floor. The 2026-09-07 field log
/// is full of it — "cupboard find dustbin", "find dustbin toilets" — and one
/// of those put the app into find mode for an object nobody asked about.
///
/// Real requests name ONE thing. Two different objects in one utterance is
/// evidence of a bag of force-matched words rather than a sentence.
Set<String> namedClasses(String text) {
  final words = text.toLowerCase().split(RegExp(r'\s+'))
    ..removeWhere((w) => w.isEmpty);
  final found = <String>{};
  for (final entry in _findable.entries) {
    final parts = entry.key.split(' ');
    // WHOLE words only. Substring matching looks equivalent and is not: "how
    // many chairs" contains "man" (a person synonym) and "cupboard" contains
    // "cup", so a plain contains() reports two objects in ordinary
    // single-object requests and would reject them as noise.
    for (var i = 0; i + parts.length <= words.length; i++) {
      if (words.sublist(i, i + parts.length).join(' ') == entry.key) {
        found.add(entry.value);
        break;
      }
    }
  }
  return found;
}

/// Which capability each keyword belongs to. Mirrors the keyword tests in
/// [parseCommand], and exists for the same reason [namedClasses] does: an
/// utterance naming TWO capabilities is a bag of force-matched words, not a
/// sentence. The 2026-09-07 field log ran `describe` from "describe light
/// left" and "the clock summary", and `read` from "the many where of me is
/// there read walk".
///
/// Direction words are deliberately absent: "left" is only a capability with a
/// question word in front of it, and "find the door on my left" is one
/// request. The dictation trigger is absent too — "assistant find the door" is
/// a trigger plus a request BY DESIGN.
const Map<String, String> _capabilityWords = {
  'walk': 'walk', 'find': 'find',
  'describe': 'describe', 'scene': 'describe', 'summary': 'describe',
  'many': 'count', 'where': 'recall',
  'path': 'path', 'way': 'path',
  'read': 'read', 'picture': 'photo', 'photo': 'photo',
  'summarise': 'summarise', 'summarize': 'summarise',
  'colour': 'colour', 'color': 'colour',
  'bright': 'light', 'dark': 'light', 'light': 'light',
  'clock': 'clock', 'zone': 'zones', 'zones': 'zones',
  'sonar': 'sonar', 'mute': 'mute', 'unmute': 'mute',
  'stop': 'stop', 'repeat': 'repeat', 'again': 'repeat',
  'help': 'help',
};

/// The longest phrase the grammar can legitimately produce is "is there
/// anything in front of me" (7 words). Anything much past that is the
/// recognizer chaining trained phrases out of room noise.
const int kMaxRequestWords = 8;

/// Every DISTINCT capability named anywhere in [text].
Set<String> namedCapabilities(String text) => text
    .toLowerCase()
    .split(RegExp(r'\s+'))
    .where(_capabilityWords.containsKey)
    .map((w) => _capabilityWords[w]!)
    .toSet();

/// Could this recognizer output be ONE thing a person asked for?
///
/// Three conditions, each of which the 2026-09-07 field log broke: at most one
/// object class ("cupboard find dustbin"), at most one capability ("describe
/// light left"), and no longer than [kMaxRequestWords] ("do laptops ahead
/// laptop on my left bottle on here right").
///
/// None of these is visible to the unknown-token ratio, because words forced
/// onto the grammar are not unplaceable — the recognizer is certain about
/// every one of them. Mirror of voice.looks_like_one_request.
bool looksLikeOneRequest(String text) {
  if (text.trim().isEmpty) return false;
  final words = text.split(RegExp(r'\s+'))..removeWhere((w) => w.isEmpty);
  if (words.length > kMaxRequestWords) return false;
  if (namedClasses(text).length > 1) return false;
  return namedCapabilities(text).length <= 1;
}

/// True when [text] names two or more different classes — see [namedClasses].
bool namesMultipleObjects(String text) => namedClasses(text).length > 1;

/// Words the shipped Vosk model has no pronunciation for. Vosk drops them from
/// the grammar with a warning nobody reads, so a phrase built from one is not
/// misheard — it is UNHEARABLE, exactly like one that was never added.
///
/// `unmute` is the one that mattered: on the 2026-09-07 walk the user said
/// "mute it", the app muted, and there was then NO SPOKEN WAY BACK — every
/// command after that ran silently, which is indistinguishable from the app
/// having stopped hearing. Hence "voice on" / "sound on" / "speak".
///
/// The other three are Indian-English and plural synonyms; they stay in the
/// PARSER (typed input and the agent tier still resolve them) and only leave
/// the grammar. Mirror of voice.UNHEARABLE_WORDS, kept honest by
/// test_voice.VocabularyTest, which builds the real grammar against the real
/// model.
const Set<String> kUnhearableWords = {
  'almirah', 'almirahs', 'laundrys', 'unmute',
};

/// True when every word of [phrase] is one the model can hear.
bool hearable(String phrase) =>
    !phrase.split(' ').any(kUnhearableWords.contains);

/// Every phrase the recognizer should be able to hear.
List<String> grammarPhrases() {
  final phrases = ['walk mode', 'walk', 'describe', 'describe scene', 'summary',
    'clock mode', 'zone mode', 'clear path', 'which way', 'read', 'read text',
    'take a picture', 'take a photo', 'photo',
    'stop', 'repeat', 'say again', 'sonar', 'sonar on', 'sonar off',
    'mute', 'voice on', 'sound on', 'speak', ...triggerWords];
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
  return phrases.where(hearable).toList();
}
