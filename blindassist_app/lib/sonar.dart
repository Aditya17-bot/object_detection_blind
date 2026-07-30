// BlindAssist — sonar audio (phase A5). Same parking-sensor rules as the
// web UI's WebAudio implementation: stereo pan follows the tracked object's
// horizontal position, beeps tick faster and rise in pitch as it gets
// closer. Beep waveforms are synthesized once at startup — no audio assets.
//
// Android note (fixed 2026-07-21 after a device log showed every beep throwing
// "Bytes sources are not supported on LOW_LATENCY mode yet"): the low-latency
// backend is SoundPool, which loads only FILES — an in-memory BytesSource
// always fails. SoundPool also plays with equal left/right volume
// (soundPool.play(id, volume, volume, ...)), so setBalance() is a no-op there
// and panning would be lost even without the crash. Both are solved by baking
// the pan into STEREO samples: one small WAV per (level, pan bucket), written
// to the cache dir at startup and pre-loaded into its own player, so a beep is
// just a play() on an already-loaded sample.
import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';

class Sonar {
  Timer? _timer;
  bool enabled = false;

  int _level = 0;    // 0 silent, 1 medium, 2 close, 3 very close
  double _pan = 0.0; // -1 (left) .. 1 (right)

  // level -> (interval ms, frequency Hz) — same numbers as static/app.js
  static const _params = {
    1: (700, 494.0),
    2: (340, 660.0),
    3: (160, 880.0),
  };

  // Pan is quantised so the samples can be pre-loaded. 5 steps is plenty for
  // a left/right cue and keeps the player count low.
  static const _panSteps = [-1.0, -0.5, 0.0, 0.5, 1.0];

  // (level, pan bucket) -> player holding that pre-loaded sample.
  final Map<int, AudioPlayer> _players = {};
  Directory? _dir;
  bool _ready = false;
  bool _beeping = false;

  static int _key(int level, int bucket) => level * 100 + bucket;

  Future<void> init() async {
    try {
      final dir = Directory('${Directory.systemTemp.path}/sonar');
      await dir.create(recursive: true);
      _dir = dir;
      for (final entry in _params.entries) {
        for (var b = 0; b < _panSteps.length; b++) {
          final file = File('${dir.path}/beep_${entry.key}_$b.wav');
          await file.writeAsBytes(_wavBeep(entry.value.$2, _panSteps[b]));
          final player = AudioPlayer();
          await player.setPlayerMode(PlayerMode.lowLatency);
          await player.setReleaseMode(ReleaseMode.stop);
          await player.setVolume(0.6);
          // SoundPool loads asynchronously; doing it now means the first real
          // beep does not pay the load.
          await player.setSource(DeviceFileSource(file.path));
          _players[_key(entry.key, b)] = player;
        }
      }
      _ready = true;
    } catch (e) {
      // Sonar is an optional cue — speech and haptics still carry guidance.
      _ready = false;
    }
  }

  void toggle() {
    enabled = !enabled;
    if (enabled) {
      _schedule();
    } else {
      _timer?.cancel();
      _timer = null;
    }
  }

  /// Called every frame with the tracked object's state.
  void update(int level, double pan) {
    _level = level;
    _pan = pan.clamp(-1.0, 1.0);
  }

  void _schedule() {
    if (!enabled) return;
    final p = _params[_level];
    if (p != null) {
      _beep();
      _timer = Timer(Duration(milliseconds: p.$1), _schedule);
    } else {
      // nothing to warn about — check again shortly
      _timer = Timer(const Duration(milliseconds: 250), _schedule);
    }
  }

  /// Nearest pre-generated pan step to the current pan.
  int _bucket(double pan) {
    final idx = ((pan + 1) / 2 * (_panSteps.length - 1)).round();
    return idx.clamp(0, _panSteps.length - 1);
  }

  Future<void> _beep() async {
    if (!_ready || _beeping) return;
    final player = _players[_key(_level, _bucket(_pan))];
    if (player == null) return;
    _beeping = true;
    try {
      // stop() clears the finished stream id so resume() starts a fresh play
      // instead of resuming an already-ended one.
      await player.stop();
      await player.resume();
    } catch (e) {
      // A dropped beep must never take down the guidance loop.
    } finally {
      _beeping = false;
    }
  }

  /// 90 ms stereo PCM16 sine beep with a fast decay envelope, as a WAV blob.
  /// [pan] -1..1 sets the channel gains (equal-power, so loudness is steady
  /// as the object crosses the frame).
  static Uint8List _wavBeep(double freq, double pan, {int sampleRate = 22050}) {
    final n = (sampleRate * 0.09).round();
    const channels = 2;
    final bytes = n * channels * 2;
    final data = ByteData(44 + bytes);
    void ascii(int offset, String s) {
      for (var i = 0; i < s.length; i++) {
        data.setUint8(offset + i, s.codeUnitAt(i));
      }
    }

    ascii(0, 'RIFF');
    data.setUint32(4, 36 + bytes, Endian.little);
    ascii(8, 'WAVE');
    ascii(12, 'fmt ');
    data.setUint32(16, 16, Endian.little);      // fmt chunk size
    data.setUint16(20, 1, Endian.little);       // PCM
    data.setUint16(22, channels, Endian.little);
    data.setUint32(24, sampleRate, Endian.little);
    data.setUint32(28, sampleRate * channels * 2, Endian.little); // byte rate
    data.setUint16(32, channels * 2, Endian.little);              // block align
    data.setUint16(34, 16, Endian.little);      // bits per sample
    ascii(36, 'data');
    data.setUint32(40, bytes, Endian.little);

    // Equal-power panning: -1 -> full left, 0 -> centre, 1 -> full right.
    final angle = (pan.clamp(-1.0, 1.0) + 1) * math.pi / 4;
    final gainL = math.cos(angle);
    final gainR = math.sin(angle);

    for (var i = 0; i < n; i++) {
      final t = i / sampleRate;
      // quick attack, exponential-ish decay — a tick, not a tone
      final env = t < 0.012 ? t / 0.012 : math.exp(-(t - 0.012) * 40);
      final sample = math.sin(2 * math.pi * freq * t) * env * 32767 * 0.8;
      final offset = 44 + i * channels * 2;
      data.setInt16(offset, (sample * gainL).round(), Endian.little);
      data.setInt16(offset + 2, (sample * gainR).round(), Endian.little);
    }
    return data.buffer.asUint8List();
  }

  void dispose() {
    _timer?.cancel();
    _timer = null;
    for (final player in _players.values) {
      player.dispose();
    }
    _players.clear();
    _ready = false;
    try {
      _dir?.deleteSync(recursive: true);
    } catch (e) {
      // cache dir cleanup is best-effort
    }
  }
}
