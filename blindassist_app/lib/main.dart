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
import 'package:flutter/semantics.dart' show CustomSemanticsAction;
import 'package:flutter/services.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import 'agent_client.dart';
import 'config.dart';
import 'detector.dart';
import 'discovery.dart';
import 'remote_detector.dart';
import 'logic/agent_actions.dart';
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

class _AssistantScreenState extends State<AssistantScreen>
    with WidgetsBindingObserver {
  CameraController? _camera;
  // Laptop-tethered inference by default (config.kUseRemote) — on-device
  // TFLite is ~2.5 s/frame on this phone. Created in _loadDetectorWithRetry:
  // the remote host comes from UDP discovery (falls back to config), so it
  // can't be constructed at field-init time. Null until load succeeds.
  FrameDetector? _detector;
  final GuidanceEngine _engine = GuidanceEngine();
  final Speaker _speaker = Speaker();
  final Sonar _sonar = Sonar();
  final OcrReader _ocr = OcrReader();
  // Tier 1: only utterances the local grammar could not parse go here, and
  // only when the laptop is reachable. Null in on-device mode or before the
  // server is found — the app is then exactly as capable as it was before.
  AgentClient? _agent;
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
    WidgetsBinding.instance.addObserver(this);
    _voice = VoiceListener(onCommand: _onVoiceCommand, onUnmatched: _askAgent);
    _init();
  }

  Future<void> _init() async {
    try {
      // speaker FIRST: every later failure must be audible — the user can't
      // read the screen, so a silent error is indistinguishable from a hang.
      await _speaker.init();
      // speak IMMEDIATELY: server discovery + camera + Vosk unzip add up to
      // many seconds, and dead air at launch reads as "the app crashed"
      _speaker.say('Starting BlindAssist');
      await _sonar.init();
      // a field walk outlasts the 30-60 s screen timeout; a paused activity
      // stops the camera stream and the app goes silently dead mid-walk
      unawaited(WakelockPlus.enable());
      await _loadDetectorWithRetry();

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

      // voice is optional AND slow (the Vosk model unzips ~40 MB on first
      // run) — start it in parallel instead of gating the welcome message
      unawaited(_startVoice());

      setState(() {
        _ready = true;
        _banner = 'Walk mode';
      });
      // the user trained the door model specifically — its silent absence on
      // the server would look exactly like "door detection is broken"
      final det = _detector;
      final doorWarning =
          (det is RemoteDetector && det.customModelAvailable == false)
              ? ' Warning: door detection unavailable on the server.'
              : '';
      await _speaker.say(
          'Walk mode. Say find bottle, walk mode, or describe.$doorWarning');
    } catch (e) {
      setState(() => _error = '$e');
      // spoken, not just shown: the target user cannot see the error text
      _speaker.say('Start up failed. $e');
    }
  }

  /// Mic permission + Vosk start, off the critical startup path. Speaks the
  /// outcome so the user knows whether voice control is live.
  Future<void> _startVoice() async {
    var ok = false;
    try {
      final mic = await Permission.microphone.request();
      if (mic.isGranted) ok = await _voice.start();
    } catch (_) {}
    if (!mounted) return;
    setState(() => _voiceActive = ok);
    if (!ok) {
      // let the welcome sentence finish first (say() replaces, not queues)
      await Future.delayed(const Duration(seconds: 4));
      if (mounted) _speaker.say('Voice commands unavailable');
    }
  }

  /// The laptop server is often started AFTER the app (or the hotspot is
  /// still coming up). Instead of dying to the error screen, keep retrying
  /// with spoken progress so the user knows the app is alive and what to fix.
  /// Each attempt re-runs UDP discovery — the server's IP is only knowable
  /// once it is actually up, and it changes every hotspot session.
  Future<void> _loadDetectorWithRetry() async {
    if (!kUseRemote) {
      final d = Detector();
      await d.load();
      _detector = d;
      return;
    }
    var attempt = 0;
    while (true) {
      final found = await discoverServer();
      final host = found?.host ?? kServerHost; // baked-in fallback
      final port = found?.port ?? kServerPort;
      final remote = RemoteDetector(host, port);
      try {
        await remote.load();
        _detector = remote;
        // same host as inference: /agent is registered by infer_server.py, so
        // reaching one means reaching the other
        _agent = AgentClient(host, port);
        // ignore: avoid_print
        print('BlindAssist: server via '
            '${found != null ? 'discovery' : 'config fallback'}');
        return;
      } catch (e) {
        remote.close();
        attempt++;
        if (!mounted) rethrow;
        if (attempt == 1) {
          _speaker.say('Cannot reach the laptop server. Retrying.');
          setState(() => _banner = 'Waiting for laptop server…');
        } else if (attempt % 4 == 0) {
          // every ~20 s, so silence never reads as a crash
          _speaker.say('Still waiting for the laptop server.');
        }
        await Future.delayed(const Duration(seconds: 5));
      }
    }
  }

  // --- app lifecycle: Android pauses the activity (screen off, task switch)
  // and the camera plugin requires an explicit dispose/re-init cycle around
  // that, or the stream comes back dead with no error.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      final cam = _camera;
      if (cam == null) return;
      _camera = null; // _onFrame checks _camera — frames stop immediately
      cam.dispose();
    } else if (state == AppLifecycleState.resumed && _ready) {
      _resumeCamera();
    }
  }

  Future<void> _resumeCamera() async {
    if (_camera != null) return;
    try {
      final cameras = await availableCameras();
      final back = cameras.firstWhere(
          (c) => c.lensDirection == CameraLensDirection.back,
          orElse: () => cameras.first);
      final controller = CameraController(back, ResolutionPreset.medium,
          enableAudio: false, imageFormatGroup: ImageFormatGroup.yuv420);
      await controller.initialize();
      _camera = controller;
      await controller.startImageStream(_onFrame);
      if (mounted) setState(() {});
      _speaker.say('Resuming');
    } catch (e) {
      _speaker.say('Camera failed to resume');
      // ignore: avoid_print
      print('BlindAssist resume failed: $e');
    }
  }

  double _now() => _clock.elapsedMilliseconds / 1000.0;

  // Consecutive detect() failures (null = no data, network down). Distinct
  // from "no detections": guidance must PAUSE, not act on a fake empty scene
  // — [] would silence sonar (silence means "path clear"), reset walk
  // escalation, and let find mode announce "not visible" during a Wi-Fi blip.
  int _failStreak = 0;
  double _lastFailReminder = 0;
  static const int _failStreakToAnnounce = 5;

  Future<void> _onFrame(CameraImage image) async {
    final detector = _detector;
    if (_busy || !mounted || _camera == null || detector == null) return;
    _busy = true;
    try {
      final rotation = _camera!.description.sensorOrientation;
      final detections = await detector.detect(image, rotation);
      if (!mounted) return;
      if (detections == null) {
        _failStreak++;
        if (_failStreak == _failStreakToAnnounce) {
          _lastFailReminder = _now();
          _speaker.say('Connection lost, guidance paused');
          _sonar.update(0, 0); // stale beeps would keep implying an obstacle
          setState(() => _banner = 'Connection lost…');
        } else if (_failStreak > _failStreakToAnnounce &&
            _now() - _lastFailReminder > 10) {
          _lastFailReminder = _now();
          _speaker.say('Still no connection');
        }
        return; // skip engine/sonar/haptics — no data is not an empty room
      }
      if (_failStreak >= _failStreakToAnnounce) {
        _speaker.say('Guidance restored');
        setState(() => _banner = 'Walk mode');
      }
      _failStreak = 0;
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
      // routine guidance is droppable while an on-demand read-out plays;
      // a "very close" escalation is safety and always cuts through
      if (msg != null) {
        _speaker.say(msg, urgent: msg.contains('very close'));
      }

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
    // busy pulsing: do NOT record the zone — recording it here swallowed the
    // change (next frame matches _lastHapticZone and never buzzes). Leaving
    // it unrecorded retries on the next frame once the train finishes.
    if (_pulsing) return;
    _lastHapticZone = tracked.hZone;
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
    if (_repeatedTooSoon(key)) return;
    _dispatch(command);
  }

  /// True when this exact request arrived again within a few seconds — see the
  /// feedback-loop note above. Shared by the local and remote tiers.
  bool _repeatedTooSoon(String key) {
    final now = _now();
    if (key == _lastVoiceKey && now - _lastVoiceTime < 4.0) return true;
    _lastVoiceKey = key;
    _lastVoiceTime = now;
    return false;
  }

  /// The trigger word ("assistant") was heard. Acknowledge, capture ONE
  /// free-form utterance with the open recognizer, then route it.
  ///
  /// The transcript goes through the local parser first — free speech often
  /// contains a trained phrasing outright ("assistant, find the door"), and
  /// that must not need the laptop. Only what the parser cannot resolve is
  /// posted to the agent.
  Future<void> _startDictation() async {
    // 'Yes?' is a fixed template, not a written reply — the same rule that
    // keeps the router out of the speech channel.
    await _speaker.say(askTemplates['listening']!, onDemand: true);
    if (mounted) setState(() => _banner = 'Listening…');
    final heard = await _voice.dictate();
    if (!mounted) return;
    if (_voice.error != null) {
      // the recognizer did not come back — say so, silence here would look
      // exactly like a working app that has stopped hearing anything
      _speaker.say('Voice commands unavailable', onDemand: true);
      setState(() => _voiceActive = false);
      return;
    }
    if (heard == null || heard.isEmpty) {
      _speaker.say(askTemplates['not_understood']!, onDemand: true);
      setState(() => _banner = 'Walk mode');
      return;
    }
    setState(() => _banner = heard);
    final command = parseCommand(heard);
    if (command != null) {
      _dispatch(command);
    } else if (_agent == null) {
      // Deliberate question, no router reachable. Unlike a stray half-heard
      // phrase, this one has to be answered — with the truth.
      _speaker.say(askTemplates['unknown']!, onDemand: true);
    } else {
      await _askAgent(heard);
    }
  }

  /// Heard, but the local grammar made nothing of it. Ask the laptop's router,
  /// which has the same capability registry plus (optionally) a local LLM.
  ///
  /// Silence is the correct outcome when there is no server: the phone has
  /// already tried everything it can do offline, and a spoken "I can't do that"
  /// on every stray noise the recognizer half-hears would be worse than
  /// nothing. When the server DOES answer an abstention, that is a real answer
  /// to a real question and it is spoken.
  Future<void> _askAgent(String heard) async {
    final agent = _agent;
    if (agent == null) return;
    if (_repeatedTooSoon('ask:$heard')) return;
    final result = await agent.route(heard);
    if (!mounted || result == null) return; // null = no data, never a guess
    if (result.actions.isEmpty) {
      final message = result.message;
      if (message != null) {
        _speaker.say(message, onDemand: true);
        setState(() => _banner = message);
      }
      return;
    }
    for (final action in result.actions) {
      _dispatch(action.toVoiceCommand());
    }
  }

  /// The one place a capability is invoked, whichever tier chose it.
  void _dispatch(VoiceCommand command) {
    switch (command.action) {
      case 'ask':
        unawaited(_startDictation()); // trigger word: open the speech window
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
      case 'stop':
        _speaker.stop(); // halt a long read-out without issuing a new command
      case 'repeat':
        _speaker.say(_banner, onDemand: true);
      case 'sonar':
        if (command.target == 'on') {
          if (!_sonar.enabled) _toggleSonar();
        } else if (command.target == 'off') {
          if (_sonar.enabled) _toggleSonar();
        } else {
          _toggleSonar();
        }
      case 'mute':
        // "mute"/"unmute" must work by voice: the mute BUTTON is the one
        // control a blind user can't find while walking
        if ((command.target == 'on') != _speaker.muted) _toggleMute();
    }
  }

  // Clear-path finder: speak the most open walking direction, on demand.
  void _clearPath() {
    final msg = _engine.path(_infos, _now());
    _speaker.say(msg, onDemand: true);
    setState(() => _banner = msg);
  }

  // Count query: "how many chairs" -> spoken count of that class.
  void _countClass(String target) {
    final msg = _engine.count(_infos, target, _now());
    _speaker.say(msg, onDemand: true);
    setState(() => _banner = msg);
  }

  // OCR: capture a still and read any printed text aloud. Pauses the detection
  // stream for the one-shot capture, then resumes it.
  bool _reading = false;
  Future<void> _readText() async {
    if (_reading || _camera == null) return;
    _reading = true;
    _speaker.say('Reading', onDemand: true);
    try {
      await _camera!.stopImageStream();
      // the stream is paused but the last obstacle's beeps would keep
      // implying "something approaching" while the user holds still reading
      _sonar.update(0, 0);
      final shot = await _camera!.takePicture();
      final text = await _ocr.readFile(shot.path);
      final msg = text.isEmpty ? 'No text found' : text;
      _speaker.say(msg, onDemand: true);
      setState(() => _banner = msg);
    } catch (e) {
      _speaker.say('Could not read text', onDemand: true);
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
    _speaker.say(msg, onDemand: true);
    setState(() => _banner = msg);
  }

  void _describe() {
    final summary = _engine.describe(_infos, _now());
    _speaker.say(summary, onDemand: true);
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
    WidgetsBinding.instance.removeObserver(this);
    WakelockPlus.disable();
    _camera?.dispose();
    _detector?.close();
    _agent?.close();
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
      // TalkBack: name the surface, expose the gestures as discoverable
      // actions (TalkBack swallows raw double-taps/long-presses), and make
      // every action reachable without vision or voice.
      body: Semantics(
        label: 'BlindAssist camera view',
        hint: 'Double tap to describe the scene',
        customSemanticsActions: {
          const CustomSemanticsAction(label: 'Toggle sonar beeps'):
              _toggleSonar,
          const CustomSemanticsAction(label: 'Repeat last announcement'): () =>
              _speaker.say(_banner, onDemand: true),
        },
        child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: _describe,
        onDoubleTap: _toggleSonar,
        onLongPress: () => _speaker.say(_banner, onDemand: true),
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
                  // status pill is sighted-tester chrome — keep TalkBack off
                  // it so focus lands on the controls and the live banner
                  child: ExcludeSemantics(
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
                    // liveRegion: TalkBack announces every new guidance
                    // message on its own — same job as aria-live in webapp
                    child: Semantics(
                      liveRegion: true,
                      child: Text(
                        _banner,
                        style: const TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w600,
                            color: Color(0xFFFFC247)),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
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
