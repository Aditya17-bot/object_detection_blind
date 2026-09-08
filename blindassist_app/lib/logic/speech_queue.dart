/// BlindAssist — chunking and resumption for spoken read-outs.
///
/// Mirror of `speech_queue.py`; see that file for the full reasoning. The short
/// version: [Speaker]'s one rule has always been "latest wins, cut the current
/// utterance off". That is right for guidance — stale guidance spoken late is
/// worse than not spoken — and wrong for everything the user asked for. On the
/// 2026-09-08 walk a summary was cut mid-sentence by a "very close" warning and
/// never came back, which the user reported as the app not finishing one thing
/// before starting the next.
///
/// Safety must still interrupt. What was missing is the other half: after the
/// warning, the read-out the user asked for RESUMES. So an on-demand read-out
/// is spoken as a sequence of chunks split at sentence boundaries, and the
/// position in that sequence survives an interruption. The chunk that was cut
/// is repeated from its start — the user heard half of it, and half a sentence
/// is not information.
library;

/// ~12 s of speech at the configured rate. Small enough that resuming after an
/// interruption repeats little, large enough that the pauses between chunks do
/// not turn a paragraph into a list.
const int kMaxChunkChars = 180;

/// A read-out interrupted this long ago is not worth resuming: the user has
/// walked on and the answer is about a scene that has moved.
const double kStaleAfterSeconds = 90.0;

final RegExp _sentenceEnd = RegExp(r'(?<=[.!?;:])\s+');
final RegExp _clauseEnd = RegExp(r'(?<=,)\s+');

/// Split [text] into speakable chunks at the most natural boundary that fits:
/// sentence, then clause, then word. Never mid-word, never empty — a chunk
/// boundary is a place the read-out can be resumed from.
List<String> splitForSpeech(String? text, {int maxChars = kMaxChunkChars}) {
  final source = (text ?? '').trim();
  if (source.isEmpty) return const [];
  final chunks = <String>[];
  for (final raw in source.split(_sentenceEnd)) {
    final sentence = raw.trim();
    if (sentence.isEmpty) continue;
    chunks.addAll(_splitLong(sentence, maxChars));
  }
  return chunks;
}

/// One sentence, split further only if it would not fit. Commas first — they
/// are where a reader would breathe — then words.
List<String> _splitLong(String sentence, int maxChars) {
  if (sentence.length <= maxChars) return [sentence];
  final parts = <String>[];
  var current = '';
  for (final piece in _clausePieces(sentence, maxChars)) {
    if (current.isEmpty) {
      current = piece;
    } else if (current.length + 1 + piece.length <= maxChars) {
      current = '$current $piece';
    } else {
      parts.add(current);
      current = piece;
    }
  }
  if (current.isNotEmpty) parts.add(current);
  // A single word longer than the limit is left whole: breaking it would be
  // unspeakable, and TTS engines handle long tokens fine.
  return parts;
}

List<String> _clausePieces(String sentence, int maxChars) {
  final out = <String>[];
  for (final raw in sentence.split(_clauseEnd)) {
    final piece = raw.trim();
    if (piece.isEmpty) continue;
    if (piece.length <= maxChars) {
      out.add(piece);
    } else {
      out.addAll(piece.split(RegExp(r'\s+')).where((w) => w.isNotEmpty));
    }
  }
  return out;
}

/// The remaining chunks of the read-out that currently owns the channel.
///
/// Deliberately dumb about time: the caller supplies `now`, so the same code
/// runs under test without waiting.
class SpeechQueue {
  SpeechQueue(
      {this.maxChars = kMaxChunkChars,
      this.staleAfter = kStaleAfterSeconds});

  final int maxChars;
  final double staleAfter;

  List<String> _chunks = const [];
  int _index = 0;
  double _started = 0;

  /// Begin a new read-out, discarding anything left of the last one.
  int load(String message, {double now = 0}) {
    _chunks = splitForSpeech(message, maxChars: maxChars);
    _index = 0;
    _started = now;
    return _chunks.length;
  }

  void clear() {
    _chunks = const [];
    _index = 0;
  }

  int get remaining {
    final left = _chunks.length - _index;
    return left < 0 ? 0 : left;
  }

  bool get hasMore => remaining > 0;

  /// The next chunk to speak, or null when the read-out is finished.
  String? take() {
    if (!hasMore) return null;
    return _chunks[_index++];
  }

  /// The chunk just taken was cut off before it finished. Say it again when
  /// the channel comes back — half a sentence is not information.
  void rewind() {
    if (_index > 0) _index--;
  }

  /// Has this read-out been waiting so long that resuming it would answer a
  /// question about a scene the user has already left?
  bool isStale(double now) => _started != 0 && (now - _started) > staleAfter;

  /// Called when the channel comes free after an interruption. Returns the
  /// chunk to speak, or null — and a stale read-out is DROPPED rather than
  /// spoken late, the same rule that governs guidance.
  String? resumeOrDrop(double now) {
    if (isStale(now)) {
      clear();
      return null;
    }
    return take();
  }
}
