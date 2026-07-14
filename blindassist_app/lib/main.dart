// BlindAssist — the assistant on the phone (phases A1-A5 integrated).
// Camera -> TFLite (COCO + custom door/dustbin) -> position -> decision ->
// speech, with offline Vosk voice control and stereo sonar.
//
// Gestures (screen-independent, designed for blind users; A6 polishes):
//   single tap  = describe scene aloud
//   double tap  = sonar beeps on/off
//   long press  = repeat last announcement
// Voice: "walk mode", "find <object>", "describe".
import 'dart:async';
import 'dart:math' as math;

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:permission_handler/permission_handler.dart';

import 'detector.dart';
import 'logic/decision.dart';
import 'logic/position.dart';
import 'logic/voice_commands.dart';
import 'ocr.dart';
import 'sonar.dart';
import 'speaker.dart';
import 'voice_listener.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const BlindAssistApp());
}

class BlindAssistApp extends StatelessWidget {
  const BlindAssistApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BlindAssist',
      theme: ThemeData.dark(useMaterial3: true),
      home: const AssistantScreen(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class AssistantScreen extends StatefulWidget {
  const AssistantScreen({super.key});

  @override
  State<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends State<AssistantScreen> {
  CameraController? _camera;
  final Detector _detector = Detector();
  final GuidanceEngine _engine = GuidanceEngine();
  final Speaker _speaker = Speaker();
  final Sonar _sonar = Sonar();
  final OcrReader _ocr = OcrReader();
  late final VoiceListener _voice;
  final Stopwatch _clock = Stopwatch()..start();

  bool _busy = false;
  bool _ready = false;
  int _frameLog = 0;
  String? _error;
  bool _voiceActive = false;
  List<Detection> _detections = const [];
  List<ObjectInfo> _infos = const [];
  String _banner = 'Starting up...';
  double _fps = 0;
  DateTime _lastFrame = DateTime.now();

  static const _sonarLevel = {
    'very close': 3,
    'close': 2,
    'medium': 1,
    'far': 0,
  };

  @override
  void initState() {
    super.initState();
    _voice = VoiceListener(onCommand: _onVoiceCommand);
    _init();
  }

  Future<void> _init() async {
    try {
      await _speaker.init();
      await _sonar.init();
      await _detector.load();

      final cameras = await availableCameras();
      final back = cameras.firstWhere(
          (c) => c.lensDirection == CameraLensDirection.back,
          orElse: () => cameras.first);
      final controller = CameraController(back, ResolutionPreset.medium,
          enableAudio: false, imageFormatGroup: ImageFormatGroup.yuv420);
      await controller.initialize();
      // assign before starting the stream: frames can fire immediately and
      // _onFrame reads _camera, so a late assignment races into a null crash
      _camera = controller;
      await controller.startImageStream(_onFrame);

      // voice is optional — the app keeps working without the mic
      final mic = await Permission.microphone.request();
      var voiceOk = false;
      if (mic.isGranted) voiceOk = await _voice.start();

      setState(() {
        _ready = true;
        _voiceActive = voiceOk;
        _banner = 'Walk mode';
      });
      await _speaker.say(voiceOk
          ? 'Walk mode. Say find bottle, walk mode, or describe.'
          : 'Walk mode started. Voice commands unavailable.');
    } catch (e) {
      setState(() => _error = '$e');
    }
  }

  double _now() => _clock.elapsedMilliseconds / 1000.0;

  Future<void> _onFrame(CameraImage image) async {
    if (_busy || !mounted || _camera == null) return;
    _busy = true;
    try {
      final rotation = _camera!.description.sensorOrientation;
      final detections = await _detector.detect(image, rotation);
      if (!mounted) return;
      _frameLog++;
      if (_frameLog % 30 == 1) {
        // liveness breadcrumb for logcat field debugging
        // ignore: avoid_print
        print('BlindAssist frame $_frameLog: ${_fps.toStringAsFixed(1)} FPS, '
            '${detections.length} detections '
            '${detections.map((d) => '${d.name}@${d.confidence.toStringAsFixed(2)}').join(' ')}');
      }
      final infos = [
        for (final d in detections)
          analyzeBox(d.name, d.confidence, d.x1, d.y1, d.x2, d.y2, 1, 1)
      ];
      final msg = _engine.update(infos, _now());
      if (msg != null) _speaker.say(msg);

      // sonar tracks the walking obstacle — or the searched object in find
      // mode, so the beeps lead the user to it (same rule as webapp.py)
      final tracked = _engine.mode == 'find'
          ? findTarget(infos, _engine.target!)
          : pickObstacle(infos);
      if (tracked != null) {
        var level = _sonarLevel[tracked.proximity]!;
        if (_engine.mode == 'find') level = math.max(level, 1);
        _sonar.update(level, tracked.centerX * 2 - 1);
      } else {
        _sonar.update(0, 0);
      }
      _haptic(tracked);

      final now = DateTime.now();
      final dt = now.difference(_lastFrame).inMilliseconds;
      _lastFrame = now;
      if (mounted) {
        setState(() {
          _detections = detections;
          _infos = infos;
          if (msg != null) _banner = msg;
          if (dt > 0) _fps = 0.8 * _fps + 0.2 * (1000 / dt);
        });
      }
    } finally {
      _busy = false;
    }
  }

  // Haptic direction: a single phone vibrator can't do true left/right, and
  // three impact *amplitudes* aren't reliably distinguishable one-handed, so
  // the SIDE is encoded by PULSE COUNT (1=left, 2=ahead, 3=right) — counting
  // taps is far more discriminable than judging strength. Fires only when the
  // tracked object CHANGES zone, so a stationary object never re-buzzes (no
  // time-throttled re-fire). Upgrade path: the `vibration` package for richer
  // temporal patterns. Sonar still carries continuous stereo L/R.
  String? _lastHapticZone;
  bool _pulsing = false;

  void _haptic(ObjectInfo? tracked) {
    if (tracked == null) {
      _lastHapticZone = null;
      return;
    }
    if (tracked.hZone == _lastHapticZone) return; // only on a real zone change
    _lastHapticZone = tracked.hZone;
    if (_pulsing) return; // don't interleave two pulse trains (object thrash)
    final pulses = tracked.hZone == 'left' ? 1 : (tracked.hZone == 'center' ? 2 : 3);
    unawaited(_pulse(pulses));
  }

  Future<void> _pulse(int n) async {
    _pulsing = true;
    try {
      for (var i = 0; i < n; i++) {
        HapticFeedback.mediumImpact();
        await Future.delayed(const Duration(milliseconds: 130));
      }
    } finally {
      _pulsing = false;
    }
  }

  String? _lastVoiceKey;
  double _lastVoiceTime = -10;

  void _onVoiceCommand(VoiceCommand command, String heard) {
    // Feedback-loop guard: the phone speaker's own TTS ("Finding person")
    // reaches the mic and the grammar force-matches it back into "find
    // person", repeating forever. Dropping identical commands within a few
    // seconds breaks the loop while real repeated requests still work.
    final key = '${command.action}:${command.target}';
    final now = _now();
    if (key == _lastVoiceKey && now - _lastVoiceTime < 4.0) return;
    _lastVoiceKey = key;
    _lastVoiceTime = now;
    switch (command.action) {
      case 'describe':
        _describe();
      case 'walk':
        _setWalk();
      case 'find':
        _setFind(command.target!);
      case 'clock':
        _setClock(true);
      case 'zones':
        _setClock(false);
      case 'path':
        _clearPath();
      case 'read':
        _readText();
      case 'count':
        _countClass(command.target!);
      case 'recall':
        _recall(command.target!);
    }
  }

  // Clear-path finder: speak the most open walking direction, on demand.
  void _clearPath() {
    final msg = _engine.path(_infos, _now());
    _speaker.say(msg);
    setState(() => _banner = msg);
  }

  // Count query: "how many chairs" -> spoken count of that class.
  void _countClass(String target) {
    final msg = _engine.count(_infos, target, _now());
    _speaker.say(msg);
    setState(() => _banner = msg);
  }

  // OCR: capture a still and read any printed text aloud. Pauses the detection
  // stream for the one-shot capture, then resumes it.
  bool _reading = false;
  Future<void> _readText() async {
    if (_reading || _camera == null) return;
    _reading = true;
    _speaker.say('Reading');
    try {
      await _camera!.stopImageStream();
      final shot = await _camera!.takePicture();
      final text = await _ocr.readFile(shot.path);
      final msg = text.isEmpty ? 'No text found' : text;
      _speaker.say(msg);
      setState(() => _banner = msg);
    } catch (e) {
      _speaker.say('Could not read text');
    } finally {
      // resume the live detection loop
      try {
        if (_camera != null) await _camera!.startImageStream(_onFrame);
      } catch (_) {}
      _reading = false;
    }
  }

  void _setClock(bool on) {
    _engine.setClock(on);
    _speaker.say(on ? 'Clock mode' : 'Zone mode');
    setState(() {});
  }

  // Object memory: speak where a class was last seen, on demand.
  void _recall(String target) {
    final msg = _engine.recall(target, _now());
    _speaker.say(msg);
    setState(() => _banner = msg);
  }

  void _describe() {
    final summary = _engine.describe(_infos, _now());
    _speaker.say(summary);
    setState(() => _banner = summary);
  }

  void _toggleSonar() {
    _sonar.toggle();
    _speaker.say(_sonar.enabled ? 'Sonar on' : 'Sonar off');
    setState(() {});
  }

  void _setWalk() {
    _engine.setMode('walk');
    _speaker.say('Walk mode');
    setState(() => _banner = 'Walk mode');
  }

  void _setFind(String target) {
    _engine.setMode('find', target);
    _speaker.say('Finding $target');
    setState(() => _banner = 'Finding $target');
  }

  void _toggleMute() {
    if (_speaker.muted) {
      _speaker.muted = false;
      _speaker.say('Voice on');
    } else {
      _speaker.say('Muted');
      _speaker.muted = true;
    }
    setState(() {});
  }

  // Touch fallback for find mode so testing never depends on the mic.
  static const _pickerTargets = [
    'bottle', 'cup', 'cell phone', 'laptop', 'book', 'toothbrush',
    'door', 'dustbin', 'chair', 'person',
  ];

  Future<void> _pickFindTarget() async {
    final target = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: const Color(0xFF1C1C1E),
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.symmetric(vertical: 8),
          children: [
            for (final t in _pickerTargets)
              ListTile(
                title: Text(t,
                    style: const TextStyle(
                        fontSize: 20, fontWeight: FontWeight.w600)),
                onTap: () => Navigator.pop(context, t),
              ),
          ],
        ),
      ),
    );
    if (target != null) _setFind(target);
  }

  @override
  void dispose() {
    _camera?.dispose();
    _detector.close();
    _speaker.dispose();
    _sonar.dispose();
    _ocr.dispose();
    _voice.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return Scaffold(
          body: Center(
              child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text('Startup error:\n$_error', textAlign: TextAlign.center),
      )));
    }
    if (!_ready || _camera == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return Scaffold(
      body: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: _describe,
        onDoubleTap: _toggleSonar,
        onLongPress: () => _speaker.say(_banner),
        child: Stack(
          fit: StackFit.expand,
          children: [
            CameraPreview(_camera!),
            CustomPaint(
                painter: _BoxPainter(detections: _detections, infos: _infos)),
            SafeArea(
              child: Align(
                alignment: Alignment.topCenter,
                child: Container(
                  margin: const EdgeInsets.all(12),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                  decoration: BoxDecoration(
                    color: Colors.black54,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    '${_engine.mode == 'find' ? 'FIND ${_engine.target}' : 'WALK'}'
                    '  ·  ${_fps.toStringAsFixed(1)} FPS'
                    '  ·  ${_voiceActive ? '🎤 on' : '🎤 off'}'
                    '${_sonar.enabled ? '  ·  sonar' : ''}',
                    style: const TextStyle(fontSize: 13),
                  ),
                ),
              ),
            ),
            Align(
              alignment: Alignment.bottomCenter,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 8),
                    child: Row(
                      children: [
                        Expanded(
                            child: _ctrlButton(
                                _engine.mode == 'walk' ? 'WALK ✓' : 'Walk',
                                _setWalk)),
                        const SizedBox(width: 8),
                        Expanded(
                            child: _ctrlButton(
                                _engine.mode == 'find'
                                    ? 'FIND ${_engine.target} ✓'
                                    : 'Find…',
                                _pickFindTarget)),
                        const SizedBox(width: 8),
                        Expanded(
                            child: _ctrlButton(
                                _engine.useClock ? 'Clock ✓' : 'Clock',
                                () => _setClock(!_engine.useClock))),
                        const SizedBox(width: 8),
                        Expanded(
                            child: _ctrlButton(
                                _reading ? 'Reading…' : 'Read', _readText)),
                        const SizedBox(width: 8),
                        Expanded(
                            child: _ctrlButton(
                                _speaker.muted ? 'Unmute' : 'Mute',
                                _toggleMute)),
                      ],
                    ),
                  ),
                  Container(
                    width: double.infinity,
                    color: Colors.black87,
                    padding: const EdgeInsets.fromLTRB(16, 14, 16, 28),
                    child: Text(
                      _banner,
                      style: const TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFFFFC247)),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

Widget _ctrlButton(String label, VoidCallback onPressed) {
  return FilledButton.tonal(
    onPressed: onPressed,
    style: FilledButton.styleFrom(
      backgroundColor: Colors.black54,
      foregroundColor: Colors.white,
      minimumSize: const Size(0, 52),
      padding: const EdgeInsets.symmetric(horizontal: 8),
    ),
    child: Text(label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
  );
}

class _BoxPainter extends CustomPainter {
  final List<Detection> detections;
  final List<ObjectInfo> infos;
  _BoxPainter({required this.detections, required this.infos});

  static const _proxColor = {
    'very close': Color(0xFFFF5A5F),
    'close': Color(0xFFFF9F40),
    'medium': Color(0xFF3ECF8E),
    'far': Color(0xFF3ECF8E),
  };

  @override
  void paint(Canvas canvas, Size size) {
    final grid = Paint()
      ..color = Colors.white24
      ..strokeWidth = 1;
    for (final f in [1 / 3, 2 / 3]) {
      canvas.drawLine(
          Offset(size.width * f, 0), Offset(size.width * f, size.height), grid);
      canvas.drawLine(
          Offset(0, size.height * f), Offset(size.width, size.height * f), grid);
    }

    for (var i = 0; i < detections.length; i++) {
      final d = detections[i];
      final info = infos[i];
      final color = _proxColor[info.proximity]!;
      final rect = Rect.fromLTRB(d.x1 * size.width, d.y1 * size.height,
          d.x2 * size.width, d.y2 * size.height);
      canvas.drawRect(
          rect,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 3
            ..color = color);
      final tp = TextPainter(
        text: TextSpan(
          text:
              ' ${d.name} | ${info.phrase} | ${info.proximity} ${d.confidence.toStringAsFixed(2)} ',
          style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: Colors.black,
              backgroundColor: color),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(
          canvas, Offset(rect.left, (rect.top - 18).clamp(0, size.height)));
    }
  }

  @override
  bool shouldRepaint(_BoxPainter old) =>
      old.detections != detections || old.infos != infos;
}
