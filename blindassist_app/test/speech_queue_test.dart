// Mirror of test_speech_queue.py. The behaviour under test is the one the
// user reported missing on 2026-09-08: a read-out interrupted by a safety
// warning has to come BACK, and come back at a sentence boundary rather than
// wherever the interruption happened to land.
import 'package:flutter_test/flutter_test.dart';

import 'package:blindassist/logic/speech_queue.dart';

void main() {
  group('splitForSpeech', () {
    test('splits at sentence boundaries and keeps the terminator', () {
      expect(
          splitForSpeech('Your account is overdrawn. Contact the bank. Thanks.'),
          ['Your account is overdrawn.', 'Contact the bank.', 'Thanks.']);
    });

    test('a short message stays one chunk', () {
      expect(splitForSpeech('Bottle on your right, close'),
          ['Bottle on your right, close']);
    });

    test('empty and whitespace produce no chunks at all', () {
      expect(splitForSpeech(''), isEmpty);
      expect(splitForSpeech('   '), isEmpty);
      expect(splitForSpeech(null), isEmpty);
    });

    test('a sentence longer than the limit is split at clauses', () {
      final long = 'The notice says the meeting has moved to the second floor, '
          'that attendance is required for all students on the course, '
          'and that the room will be open from nine in the morning.';
      final chunks = splitForSpeech(long, maxChars: 80);
      expect(chunks.length, greaterThan(1));
      for (final c in chunks) {
        expect(c.length, lessThanOrEqualTo(80));
      }
      // nothing is lost: every word survives the split
      expect(chunks.join(' ').split(RegExp(r'\s+')).length,
          long.split(RegExp(r'\s+')).length);
    });

    test('never splits mid-word', () {
      final chunks = splitForSpeech('a' * 40 + ' ' + 'b' * 40, maxChars: 30);
      for (final c in chunks) {
        expect(c.contains(' ') || c.length >= 30, isTrue);
      }
      expect(chunks.every((c) => c == 'a' * 40 || c == 'b' * 40), isTrue);
    });
  });

  group('SpeechQueue', () {
    test('hands out chunks in order, then reports empty', () {
      final q = SpeechQueue();
      expect(q.load('One. Two. Three.'), 3);
      expect(q.take(), 'One.');
      expect(q.take(), 'Two.');
      expect(q.remaining, 1);
      expect(q.take(), 'Three.');
      expect(q.hasMore, isFalse);
      expect(q.take(), isNull);
    });

    test('rewind repeats the interrupted chunk, not the next one', () {
      final q = SpeechQueue();
      q.load('One. Two. Three.');
      expect(q.take(), 'One.');
      expect(q.take(), 'Two.'); // safety cuts in here
      q.rewind();
      expect(q.take(), 'Two.'); // the cut sentence is said again in full
      expect(q.take(), 'Three.');
    });

    test('rewind at the start is a no-op, never a negative index', () {
      final q = SpeechQueue();
      q.load('Only one.');
      q.rewind();
      expect(q.take(), 'Only one.');
    });

    test('loading a new read-out abandons the previous one', () {
      final q = SpeechQueue();
      q.load('One. Two. Three.');
      q.take();
      q.load('Something else.');
      expect(q.remaining, 1);
      expect(q.take(), 'Something else.');
    });

    test('a read-out interrupted too long ago is dropped, not spoken late', () {
      final q = SpeechQueue(staleAfter: 90);
      q.load('One. Two. Three.', now: 100);
      q.take();
      // the user asked 91 seconds ago and has walked on since
      expect(q.resumeOrDrop(191), isNull);
      expect(q.hasMore, isFalse);
    });

    test('a read-out interrupted a moment ago resumes', () {
      final q = SpeechQueue(staleAfter: 90);
      q.load('One. Two. Three.', now: 100);
      q.take();
      expect(q.resumeOrDrop(103), 'Two.');
    });

    test('clear drops everything: "stop" means the task, not the sentence', () {
      final q = SpeechQueue();
      q.load('One. Two. Three.');
      q.clear();
      expect(q.hasMore, isFalse);
      expect(q.remaining, 0);
    });
  });
}
