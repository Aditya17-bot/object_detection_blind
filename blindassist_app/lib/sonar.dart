// BlindAssist — sonar audio (phase A5). Same parking-sensor rules as the
// web UI's WebAudio implementation: stereo pan follows the tracked object's
// horizontal position, beeps tick faster and rise in pitch as it gets
// closer. Beep waveforms are synthesized once at startup — no audio assets.
import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';

class Sonar {
  final AudioPlayer _player = AudioPlayer();
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

  late final Map<int, Uint8List> _beeps;

  Future<void> init() async {
    _beeps = {for (final e in _params.entries) e.key: _wavBeep(e.value.$2)};
    await _player.setPlayerMode(PlayerMode.lowLatency);
    await _player.setReleaseMode(ReleaseMode.stop);
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

  Future<void> _beep() async {
    final wav = _beeps[_level];
    if (wav == null) return;
    await _player.setBalance(_pan);
    await _player.play(BytesSource(wav), volume: 0.6);
  }

  /// 90 ms mono PCM16 sine beep with a fast decay envelope, as a WAV blob.
  static Uint8List _wavBeep(double freq, {int sampleRate = 22050}) {
    final n = (sampleRate * 0.09).round();
    final data = ByteData(44 + n * 2);
    void ascii(int offset, String s) {
      for (var i = 0; i < s.length; i++) {
        data.setUint8(offset + i, s.codeUnitAt(i));
      }
    }

    ascii(0, 'RIFF');
    data.setUint32(4, 36 + n * 2, Endian.little);
    ascii(8, 'WAVE');
    ascii(12, 'fmt ');
    data.setUint32(16, 16, Endian.little);      // fmt chunk size
    data.setUint16(20, 1, Endian.little);       // PCM
    data.setUint16(22, 1, Endian.little);       // mono
    data.setUint32(24, sampleRate, Endian.little);
    data.setUint32(28, sampleRate * 2, Endian.little); // byte rate
    data.setUint16(32, 2, Endian.little);       // block align
    data.setUint16(34, 16, Endian.little);      // bits per sample
    ascii(36, 'data');
    data.setUint32(40, n * 2, Endian.little);

    for (var i = 0; i < n; i++) {
      final t = i / sampleRate;
      // quick attack, exponential-ish decay — a tick, not a tone
      final env = t < 0.012 ? t / 0.012 : math.exp(-(t - 0.012) * 40);
      final sample = math.sin(2 * math.pi * freq * t) * env;
      data.setInt16(44 + i * 2, (sample * 32767 * 0.8).round(), Endian.little);
    }
    return data.buffer.asUint8List();
  }

  void dispose() {
    _timer?.cancel();
    _player.dispose();
  }
}
