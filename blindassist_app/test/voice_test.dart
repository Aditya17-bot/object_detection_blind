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
  });
}
