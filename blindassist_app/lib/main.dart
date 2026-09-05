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
import 'package:gal/gal.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart' show CustomSemanticsAction;
import 'package:flutter/services.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import 'agent_client.dart';
import 'config.dart';
import 'detector.dart';
import 'discovery.dart';
import 'features_page.dart';
import 'settings.dart';
import 'remote_detector.dart';
import 'logic/agent_actions.dart';
import 'logic/decision.dart';
import 'logic/position.dart';
import 'logic/speech_policy.dart';
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
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        scaffoldBackgroundColor: const Color(0xFF07090D),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFFFC247),
          secondary: Color(0xFF4DD0E1),
          surface: Color(0xFF10161F),
        ),
      ),
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
  // Which task owns the speech channel. Without it every capability spoke the
  // moment it fired, so an unrequested read-out could land in the middle of a
  // find the user had just asked for.
  final SpeechPolicy _policy = SpeechPolicy();
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
    _voice = VoiceListener(
        onCommand: _onVoiceCommand,
        onUnmatched: _onUnmatchedSpeech,
        echoing: () => _speaker.isEchoing);
    _init();
  }

  Future<void> _init() async {
    try {
      // speaker FIRST: every later failure must be audible — the user can't
      // read the screen, so a silent error is indistinguishable from a hang.
      await _speaker.init();
      // the greeting IS the startup signal: a blind user has no splash screen,
      // and hearing their own name confirms it is their configured app that
      // came up. Settings load first (it is a local key-value read) so the
      // very first utterance is already personal.
      await AppSettings.load();
      // speak IMMEDIATELY: server discovery + camera + Vosk unzip add up to
      // many seconds, and dead air at launch reads as "the app crashed"
      final greeting = AppSettings.greeting();
      _speaker.say('$greeting. Starting BlindAssist');
      if (mounted) setState(() => _banner = greeting);
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
          _say('Connection lost, guidance paused', kSafety, 'link');
          _sonar.update(0, 0); // stale beeps would keep implying an obstacle
          setState(() => _banner = 'Connection lost…');
        } else if (_failStreak > _failStreakToAnnounce &&
            _now() - _lastFailReminder > 10) {
          _lastFailReminder = _now();
          _say('Still no connection', kSafety, 'link');
        }
        return; // skip engine/sonar/haptics — no data is not an empty room
      }
      if (_failStreak >= _failStreakToAnnounce) {
        _say('Guidance restored', kSafety, 'link');
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
          analyzeBox(d.name, d.confidence, d.x1, d.y1, d.x2, d.y2, 1, 1,
              trustedName: d.trustedName)
      ];
      final wasFinding = _engine.mode == 'find';
      final findTag = wasFinding ? 'find:${_engine.target}' : null;
      final msg = _engine.update(infos, _now());
      if (msg != null) {
        if (msg.contains('very close')) {
          // safety: never gated, never delayed, whatever else is happening
          _say(msg, kSafety, 'walk');
        } else if (wasFinding) {
          // In find mode the engine's output IS the answer to the request the
          // user made, so it speaks under the find task's own focus.
          //
          // The engine auto-returns to walk the moment it announces the
          // target. Ending the hold on that transition released the channel
          // BEFORE the sentence had been spoken, and the next frame's warning
          // cut it off mid-word — the bug the user reported as "it finds it
          // but the voice gets interrupted and it goes away". So the
          // open-ended search hold is replaced by one that covers the
          // announcement, and expires on its own afterwards.
          final resolved = _engine.mode != 'find';
          if (resolved) _policy.begin(findTag!, _now(), seconds: 0.1);
          _say(msg, kResponse, findTag!);
        } else {
          _say(msg, kRoutine, 'walk');
        }
      } else if (wasFinding && _engine.mode != 'find') {
        // resolved without anything to say (mode change only)
        _policy.end(findTag!, _now());
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
    // (Speaker.isEchoing now stops most of this at the microphone; this stays
    // as the guard for an echo that arrives after the tail has expired.)
    final key = '${command.action}:${command.target}';
    if (_repeatedTooSoon(key)) return;
    _dispatch(command);
  }

  /// Heard, but the deterministic parser made nothing of it.
  ///
  /// This is where the 2026-08-02 walk went wrong. The recognizer is
  /// GRAMMAR-CONSTRAINED: it cannot return "I did not understand", only its
  /// best match over the trained phrases, for any audio at all — a passing
  /// conversation, a door closing, our own TTS. Every one of those used to be
  /// posted to the router (26 round trips in 2.5 minutes), and the router,
  /// whose measured out-of-scope over-trigger rate is 55%, turned some of them
  /// into spoken actions and the rest into a spoken "I can't do that" the user
  /// had not asked for.
  ///
  /// Two rules now. Unparseable audio must clear a plausibility floor before
  /// the router is consulted at all, and whatever comes back is UNSOLICITED:
  /// it may run a capability, but it may never speak an abstention. Silence is
  /// the right answer to a question nobody asked.
  double _lastUnsolicited = -100;
  static const double _unsolicitedGap = 3.0;

  void _onUnmatchedSpeech(String heard) {
    if (!isPlausibleRequest(heard, classWords: targetClasses)) return;
    // Rate limit, on top of the plausibility floor. The walk that exposed this
    // sent 26 requests in 2.5 minutes; a burst of near-identical noise costs a
    // ~1.5 s model call each time and can only end in an abstention.
    final now = _now();
    if (now - _lastUnsolicited < _unsolicitedGap) return;
    _lastUnsolicited = now;
    unawaited(_askAgent(heard, solicited: false));
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
    _releaseFocus(); // a deliberate question outranks whatever was running
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
      await _askAgent(heard, solicited: true);
    }
  }

  /// Ask the laptop's router, which has the same capability registry plus
  /// (optionally) a local LLM.
  ///
  /// [solicited] is the whole safety argument. True when the user deliberately
  /// opened a dictation window with the trigger word: they asked a question, so
  /// an abstention is a real answer and gets spoken. False when this came from
  /// audio the grammar recognizer produced unbidden: then the router's answer
  /// may RUN a capability but must never speak, because "I can't do that" in
  /// reply to a door closing is the failure the user reported.
  Future<void> _askAgent(String heard, {required bool solicited}) async {
    final agent = _agent;
    if (agent == null) return;
    // A single force-matched token is never a request, on ANY path in. The
    // 2026-08-02 walk sent bare "door", "is", "bed" and "tv" to the router,
    // which obligingly invented a capability for each. Tier 0 would already
    // have parsed a real one-word command, so nothing useful is lost.
    if (heard.trim().split(RegExp(r'\s+')).length < 2) {
      if (solicited) _speaker.say(askTemplates['not_understood']!, onDemand: true);
      return;
    }
    if (_repeatedTooSoon('ask:$heard')) return;
    final result =
        await agent.route(heard, state: _engine.stateSummary(_infos, _now()));
    if (!mounted || result == null) return; // null = no data, never a guess
    if (result.actions.isEmpty) {
      if (!solicited) return; // nobody asked — say nothing
      final message = result.message;
      if (message != null) {
        _speaker.say(message, onDemand: true);
        setState(() => _banner = message);
      }
      return;
    }
    for (final action in result.actions) {
      _dispatch(action.toVoiceCommand(), solicited: solicited);
    }
  }

  /// The one place a capability is invoked, whichever tier chose it.
  ///
  /// [solicited] false means the dialogue layer guessed at audio the user may
  /// not have spoken; such a guess never interrupts a task in progress.
  void _dispatch(VoiceCommand command, {bool solicited = true}) {
    final action = command.action;
    if (!_policy.allowCommand(action, _now(), solicited: solicited)) {
      // ignore: avoid_print
      print('BlindAssist policy: dropped "$action" '
          '(focus=${_policy.activeTag(_now())}, solicited=$solicited)');
      return;
    }
    // An informational read-out owns the channel briefly so the next routine
    // warning does not tread on its last word. Find takes an open-ended hold:
    // it runs until the target is located, not until it has spoken once.
    if (kInformational.contains(action)) {
      _policy.begin(action, _now(), seconds: _policy.focusSeconds);
    }
    switch (action) {
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
      case 'check':
        _checkDirection(command.target!);
      case 'read':
        _readText();
      case 'photo':
        _takePhoto();
      case 'count':
        _countClass(command.target!);
      case 'recall':
        _recall(command.target!);
      case 'stop':
        _releaseFocus(); // "stop" ends the task as well as the sentence
        _speaker.stop();
      case 'repeat':
        _say(_banner, kResponse, 'repeat');
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

  /// Every spoken message goes through here, so the ordering rules live in one
  /// place instead of being re-derived at each call site.
  void _say(String message, int priority, String tag, {bool solicited = true}) {
    final now = _now();
    if (!_policy.allowSpeech(priority, tag, now, solicited: solicited)) {
      return; // dropped, never queued: stale guidance spoken late is worse
    }
    // An answer to the user holds the channel for as long as it takes to SAY,
    // not just until its state change is done. Without this the find
    // announcement was cut off mid-word: the engine auto-returns to walk the
    // instant it announces the target, so the channel went free before the
    // user had heard the answer. Safety is exempt — it must never be delayed
    // by, nor delay, anything.
    if (priority == kResponse) {
      if (_policy.activeTag(now) == tag) {
        _policy.extend(tag, now, _speakSeconds(message));
      } else {
        _policy.begin(tag, now, seconds: _speakSeconds(message));
      }
    }
    _speaker.say(message,
        onDemand: priority >= kResponse, urgent: priority >= kSafety);
    if (mounted) setState(() => _banner = message);
  }

  /// Rough time to speak [message] at the configured rate (~15 chars/s), with
  /// a floor so a two-word answer still gets the last word in.
  double _speakSeconds(String message) =>
      (message.length / 15).clamp(2.5, 30).toDouble();

  /// Release whatever task holds the channel. Called when a task completes and
  /// by "stop", which the user means as "that's enough".
  void _releaseFocus() {
    final tag = _policy.activeTag(_now());
    if (tag != null) _policy.end(tag, _now());
  }

  // Directional query: "is there anything on my left?". Answered on-device
  // from the current detections — no server, no model, no invention.
  void _checkDirection(String direction) {
    final msg = _engine.check(_infos, direction, _now());
    if (msg == null) {
      // a direction we do not have (nothing behind the camera): say so
      _say(askTemplates['not_understood']!, kResponse, 'check');
      return;
    }
    _say(msg, kResponse, 'check');
  }

  // Clear-path finder: speak the most open walking direction, on demand.
  void _clearPath() {
    final msg = _engine.path(_infos, _now());
    _say(msg, kResponse, 'path');
  }

  // Count query: "how many chairs" -> spoken count of that class.
  void _countClass(String target) {
    final msg = _engine.count(_infos, target, _now());
    _say(msg, kResponse, 'count');
  }

  // OCR: capture a still and read any printed text aloud. Pauses the detection
  // stream for the one-shot capture, then resumes it.
  bool _reading = false;
  Future<void> _readText() async {
    if (_reading || _camera == null) return;
    _reading = true;
    _say('Reading', kConfirm, 'read');
    // the control row that used to show "Reading…" is gone, so the banner is
    // now the only visual sign the capture is in progress
    setState(() => _banner = 'Reading…');
    try {
      await _camera!.stopImageStream();
      // the stream is paused but the last obstacle's beeps would keep
      // implying "something approaching" while the user holds still reading
      _sonar.update(0, 0);
      final shot = await _camera!.takePicture();
      final text = await _ocr.readFile(shot.path);
      final msg = text.isEmpty ? 'No text found' : text;
      // Through _say, NOT _speaker.say: this is what extends the 'read' focus
      // to cover the time the text takes to SPEAK. _dispatch opened the hold
      // for the default 6 s, which a page of OCR text outlasts easily — after
      // which routine walk chatter was free to cut in mid-sentence. That, plus
      // the stream resuming below, is the "read stops before reading fully"
      // the user reported.
      _say(msg, kResponse, 'read');
    } catch (e) {
      _say('Could not read text', kResponse, 'read');
    } finally {
      // Resume the live detection loop. Deliberately NOT deferred until the
      // speech ends: a very-close obstacle while the user stands reading is
      // still worth interrupting for, and going blind for the length of a page
      // of text would be worse than a cut-off sentence. Safety may interrupt;
      // routine guidance may not, and now it cannot — the focus hold above
      // outlives the read.
      try {
        if (_camera != null) await _camera!.startImageStream(_onFrame);
      } catch (_) {}
      _reading = false;
      // The hold is NOT released here. It was released the instant OCR
      // finished, which is before the user has heard a word of the result;
      // it now expires on its own once the sentence has been spoken.
    }
  }

  // Photo: capture a still and put it in the phone's GALLERY.
  //
  // The user cannot review it, so app-private storage would make the feature
  // pointless — the whole purpose is handing the picture to a sighted person,
  // which means it has to appear where every other photo on the phone appears.
  // Same pause/capture/resume dance as _readText: the detection stream and a
  // still capture cannot both own the camera.
  bool _capturing = false;
  Future<void> _takePhoto() async {
    if (_capturing || _reading || _camera == null) return;
    _capturing = true;
    _say('Taking a picture', kResponse, 'photo');
    try {
      await _camera!.stopImageStream();
      // beeps during a capture imply an obstacle is approaching while the user
      // is deliberately holding still
      _sonar.update(0, 0);
      final shot = await _camera!.takePicture();
      await Gal.putImage(shot.path, album: 'BlindAssist');
      _say('Photo saved', kResponse, 'photo');
    } on GalException catch (e) {
      // most often the gallery permission was refused — say which, because a
      // user who cannot see the dialog has no other way to find out
      _say(e.type == GalExceptionType.accessDenied
              ? 'Photo not saved, permission denied'
              : 'Could not save the photo',
          kResponse, 'photo');
    } catch (_) {
      _say('Could not take the picture', kResponse, 'photo');
    } finally {
      try {
        if (_camera != null) await _camera!.startImageStream(_onFrame);
      } catch (_) {}
      _capturing = false;
      _policy.end('photo', _now());
    }
  }

  void _setClock(bool on) {
    _engine.setClock(on);
    // Through _say so this confirmation obeys the same ordering rules as every
    // other utterance; _speaker.say bypassed the policy entirely and could
    // land in the middle of a task the user had asked for.
    _say(on ? 'Clock mode' : 'Zone mode', kConfirm, 'clock');
    setState(() {});
  }

  // Object memory: speak where a class was last seen, on demand.
  void _recall(String target) {
    final msg = _engine.recall(target, _now());
    _say(msg, kResponse, 'recall');
  }

  void _describe() {
    final summary = _engine.describe(_infos, _now());
    _say(summary, kResponse, 'describe');
  }

  void _toggleSonar() {
    _sonar.toggle();
    _speaker.say(_sonar.enabled ? 'Sonar on' : 'Sonar off');
    setState(() {});
  }

  void _setWalk() {
    _releaseFocus(); // whatever task was running, the user has moved on
    _engine.setMode('walk');
    _say('Walk mode', kConfirm, 'walk');
  }

  void _setFind(String target) {
    // An OPEN-ENDED hold, not a timed one: find runs until the target is
    // located, and the user's complaint was precisely that other things spoke
    // during the search. The hold is released in _onFrame when the engine
    // auto-returns to walk, by _setWalk, by "stop", and by the 90 s cap.
    _releaseFocus();
    _policy.begin('find:$target', _now());
    _engine.setMode('find', target);
    _say('Finding $target', kConfirm, 'find:$target');
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

  /// The features page: every capability, the phrases that trigger it, the
  /// gestures, and the name used in the greeting. Reached by swiping up — the
  /// control row it replaced was screen space a blind user could not use.
  Future<void> _openFeatures() async {
    // beeps over a page the user is reading are just noise
    final sonarWasOn = _sonar.enabled;
    if (sonarWasOn) _sonar.setEnabled(false);
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => FeaturesPage(
        onCommand: _dispatch,
        onNameChanged: (name) async {
          await AppSettings.setUserName(name);
          if (mounted) setState(() {});
        },
        voiceActive: _voiceActive,
        agentReady: _agent != null,
        muted: _speaker.muted,
      ),
    ));
    if (!mounted) return;
    if (sonarWasOn) _sonar.setEnabled(true);
    setState(() {});
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
      backgroundColor: Colors.black,
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
          const CustomSemanticsAction(label: 'Open the features page'):
              _openFeatures,
        },
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: _describe,
          onDoubleTap: _toggleSonar,
          onLongPress: () => _speaker.say(_banner, onDemand: true),
          // Swipe up replaces the control row: the features page is sighted
          // chrome (demo, setup, learning the phrases), so it gets a gesture
          // no blind user will hit by accident rather than screen space that
          // was doing nothing for them.
          onVerticalDragEnd: (details) {
            if ((details.primaryVelocity ?? 0) < -250) _openFeatures();
          },
          child: Stack(
            fit: StackFit.expand,
            children: [
              CameraPreview(_camera!),
              CustomPaint(
                  painter: _BoxPainter(detections: _detections, infos: _infos)),
              // top and bottom scrims: the announcement has to stay readable
              // over a bright doorway or a dark corridor alike
              const _Scrim(),
              SafeArea(child: _statusBar()),
              Align(
                alignment: Alignment.bottomCenter,
                child: SafeArea(
                  top: false,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 18),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _announcementCard(),
                        const SizedBox(height: 12),
                        _swipeHint(),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ---- chrome -------------------------------------------------------------

  static const _accent = Color(0xFFFFC247);
  static const _teal = Color(0xFF4DD0E1);

  Widget _statusBar() {
    // sighted-tester chrome — keep TalkBack off it so focus lands on the
    // live announcement instead
    return ExcludeSemantics(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
        child: Row(
          children: [
            _modeChip(),
            const Spacer(),
            if (_sonar.enabled) _miniChip(Icons.graphic_eq, 'sonar'),
            if (_speaker.muted) _miniChip(Icons.volume_off, 'muted'),
            _miniChip(_voiceActive ? Icons.mic : Icons.mic_off,
                _fps.toStringAsFixed(1)),
          ],
        ),
      ),
    );
  }

  Widget _modeChip() {
    final finding = _engine.mode == 'find';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(30),
        border: Border.all(
            color: (finding ? _accent : _teal).withValues(alpha: 0.55)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(finding ? Icons.search : Icons.directions_walk,
            size: 16, color: finding ? _accent : _teal),
        const SizedBox(width: 7),
        Text(
          finding ? 'Finding ${_engine.target}' : 'Walking',
          style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.3,
              color: finding ? _accent : _teal),
        ),
      ]),
    );
  }

  Widget _miniChip(IconData icon, String label) => Container(
        margin: const EdgeInsets.only(left: 8),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
        decoration: BoxDecoration(
          color: Colors.black.withValues(alpha: 0.55),
          borderRadius: BorderRadius.circular(30),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 14, color: Colors.white70),
          const SizedBox(width: 5),
          Text(label,
              style: const TextStyle(fontSize: 12, color: Colors.white70)),
        ]),
      );

  Widget _announcementCard() => Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Colors.black.withValues(alpha: 0.72),
              Colors.black.withValues(alpha: 0.55),
            ],
          ),
          border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
        ),
        // liveRegion: TalkBack announces every new guidance message on its
        // own — same job as aria-live in webapp
        child: Semantics(
          liveRegion: true,
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 220),
            child: Text(
              _banner,
              key: ValueKey(_banner),
              textAlign: TextAlign.center,
              style: const TextStyle(
                  fontSize: 24,
                  height: 1.25,
                  fontWeight: FontWeight.w700,
                  color: _accent),
            ),
          ),
        ),
      );

  Widget _swipeHint() => ExcludeSemantics(
        child: Opacity(
          opacity: 0.5,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: const [
              Icon(Icons.keyboard_arrow_up, size: 16, color: Colors.white),
              SizedBox(width: 4),
              Text('swipe up for everything I can do',
                  style: TextStyle(fontSize: 12, color: Colors.white)),
            ],
          ),
        ),
      );
}

/// Vertical scrims so white text survives a bright doorway or a dark corridor.
class _Scrim extends StatelessWidget {
  const _Scrim();

  @override
  Widget build(BuildContext context) => IgnorePointer(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                Colors.black.withValues(alpha: 0.45),
                Colors.transparent,
                Colors.transparent,
                Colors.black.withValues(alpha: 0.55),
              ],
              stops: const [0.0, 0.18, 0.62, 1.0],
            ),
          ),
        ),
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
