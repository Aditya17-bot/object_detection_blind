// Mirror of test_voice.py — voice command parser, pure logic.
import 'package:flutter_test/flutter_test.dart';

import 'package:blindassist/logic/voice_commands.dart';

void main() {
  group('parseCommand', () {
    test('walk', () {
      expect(parseCommand('walk mode'), (action: 'walk', target: null));
      expect(parseCommand('walk'), (action: 'walk', target: null));
    });
    test('find simple', () {
      expect(parseCommand('find bottle'), (action: 'find', target: 'bottle'));
    });
    test('find with filler words', () {
      expect(parseCommand('please find the bottle'),
          (action: 'find', target: 'bottle'));
    });
    test('find two-word class', () {
      expect(parseCommand('find cell phone'),
          (action: 'find', target: 'cell phone'));
    });
    test('find synonyms map to coco', () {
      expect(parseCommand('find phone'), (action: 'find', target: 'cell phone'));
      expect(parseCommand('find the fridge'),
          (action: 'find', target: 'refrigerator'));
      expect(parseCommand('find sofa'), (action: 'find', target: 'couch'));
      expect(parseCommand('find table'),
          (action: 'find', target: 'dining table'));
    });
    test('describe', () {
      expect(parseCommand('describe'), (action: 'describe', target: null));
      expect(parseCommand('describe the scene'),
          (action: 'describe', target: null));
    });
    test('clock and zone toggle', () {
      expect(parseCommand('clock mode'), (action: 'clock', target: null));
      expect(parseCommand('zone mode'), (action: 'zones', target: null));
    });
    test('clear path finder', () {
      expect(parseCommand('clear path'), (action: 'path', target: null));
      expect(parseCommand('which way'), (action: 'path', target: null));
    });
    test('count query', () {
      expect(parseCommand('how many chairs'), (action: 'count', target: 'chair'));
      expect(parseCommand('how many bottles are there'),
          (action: 'count', target: 'bottle'));
    });
    test('read ocr', () {
      expect(parseCommand('read'), (action: 'read', target: null));
      expect(parseCommand('read text'), (action: 'read', target: null));
    });
    test('recall where is', () {
      expect(parseCommand('where is the cup'), (action: 'recall', target: 'cup'));
      expect(parseCommand('where is my phone'),
          (action: 'recall', target: 'cell phone'));
    });
    test('unknown utterances ignored', () {
      expect(parseCommand('hello there'), isNull);
      expect(parseCommand('find unicorn'), isNull);
      expect(parseCommand('where is the unicorn'), isNull);
      expect(parseCommand(''), isNull);
    });
    test('grammar covers all commands (no dead phrases)', () {
      final phrases = grammarPhrases();
      expect(phrases, contains('walk mode'));
      expect(phrases, contains('find bottle'));
      expect(phrases, contains('find the fridge'));
      expect(phrases, contains('clock mode'));
      expect(phrases, contains('where is cup'));
      for (final p in phrases) {
        expect(parseCommand(p), isNotNull, reason: p);
      }
    });
    test('door is findable by voice (custom model class)', () {
      expect(parseCommand('find door'), (action: 'find', target: 'door'));
    });
    test('stop and repeat', () {
      expect(parseCommand('stop'), (action: 'stop', target: null));
      expect(parseCommand('repeat'), (action: 'repeat', target: null));
      expect(parseCommand('say again'), (action: 'repeat', target: null));
    });
    test('sonar toggle', () {
      expect(parseCommand('sonar'), (action: 'sonar', target: null));
      expect(parseCommand('sonar on'), (action: 'sonar', target: 'on'));
      expect(parseCommand('turn sonar off'), (action: 'sonar', target: 'off'));
    });
    test('mute and unmute', () {
      expect(parseCommand('mute'), (action: 'mute', target: 'on'));
      expect(parseCommand('unmute'), (action: 'mute', target: 'off'));
    });
    test('trigger word opens dictation', () {
      for (final word in triggerWords) {
        expect(parseCommand(word), (action: 'ask', target: null));
      }
      // it is in the grammar, or the recognizer could never hear it
      expect(grammarPhrases(), containsAll(triggerWords));
    });
    test('trigger loses to every real command (checked last)', () {
      // "assistant, find the door" must find the door, not open a window and
      // throw the words away.
      expect(parseCommand('assistant find the door'),
          (action: 'find', target: 'door'));
      expect(parseCommand('assistant describe'),
          (action: 'describe', target: null));
      expect(parseCommand('question how many chairs'),
          (action: 'count', target: 'chair'));
    });
    test('direction queries parse on-device', () {
      for (final text in ['is there anything in front of me', 'what is ahead',
        'anything in front of me', 'check ahead']) {
        expect(parseCommand(text), (action: 'check', target: 'ahead'),
            reason: text);
      }
      expect(parseCommand('what is on my left'),
          (action: 'check', target: 'left'));
      expect(parseCommand("what's on my left"),
          (action: 'check', target: 'left'));
      expect(parseCommand('is there anything on my right'),
          (action: 'check', target: 'right'));
    });
    test('a direction never steals an existing command', () {
      expect(parseCommand('find the door on my left'),
          (action: 'find', target: 'door'));
      expect(parseCommand('where is the cup on my right'),
          (action: 'recall', target: 'cup'));
      expect(parseCommand('which way is clear'), (action: 'path', target: null));
      expect(parseCommand('left'), isNull);
    });
    test('left and right need a positional lead-in', () {
      // found by the 2026-08-01 eval run, not by hand: "left" is an ordinary
      // English word and was turning an out-of-scope utterance into a query
      expect(parseCommand('how much battery is left'), isNull);
      expect(parseCommand('turn left at the corner'), isNull);
      // ...while ahead/front/forward have no non-spatial reading here
      expect(parseCommand('is anything ahead'),
          (action: 'check', target: 'ahead'));
    });
    test('plurals parse to the singular class', () {
      expect(parseCommand('how many chairs'), (action: 'count', target: 'chair'));
      expect(parseCommand('how many people'), (action: 'count', target: 'person'));
      expect(parseCommand('how many couches'), (action: 'count', target: 'couch'));
      expect(parseCommand('find bottles'), (action: 'find', target: 'bottle'));
    });
  });

  group('photo', () {
    // The photo goes to the phone GALLERY: the user cannot review it and the
    // point is handing it to a sighted person.
    test('the spoken forms parse', () {
      for (final t in [
        'take a picture',
        'take a photo',
        'photo',
        'please take a picture',
      ]) {
        expect(parseCommand(t)?.action, 'photo', reason: t);
      }
    });

    test('it does not steal an object query', () {
      expect(parseCommand('find the bottle')?.action, 'find');
      expect(parseCommand('take a picture of the chair')?.action, 'photo');
    });

    test('read still wins over photo', () {
      expect(parseCommand('read the text in the picture')?.action, 'read');
    });
  });
}
