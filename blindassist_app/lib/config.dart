/// Runtime wiring for where detection happens.
///
/// On the S20 FE (Exynos 990) on-device TFLite runs at ~2.5 s/inference for
/// BOTH the GPU and NNAPI delegates, so every frame times out and nothing is
/// detected. The remote path ships raw camera frames to a laptop running
/// yolov8s + the door model (~140 ms/frame) and gets real-time detections back
/// over Wi-Fi, keeping every native feature (sonar, haptics, voice, OCR).
library;

/// true  -> RemoteDetector (laptop does inference; needs infer_server.py).
/// false -> on-device Detector (TFLite; only viable on faster hardware).
const bool kUseRemote = true;

/// FALLBACK ONLY: the app finds the laptop via UDP broadcast at startup
/// (discovery.dart — infer_server.py answers with its port, its IP comes from
/// the reply packet). These constants are used only when discovery times out,
/// e.g. on a network that filters broadcast. Phone and laptop must be on the
/// same Wi-Fi/hotspot either way.
const String kServerHost = '172.17.77.158';
const int kServerPort = 5001;

/// Should speech the on-device parser could NOT resolve be sent to the router
/// unbidden?
///
/// DISABLED 2026-09-05, on the project's own stated criterion. The unsolicited
/// path was kept as "a convenience the eval says over-triggers", with the note
/// that the next walk's log would decide whether it earns its place. That log:
/// two unsolicited calls, both noise the grammar had force-matched ("many
/// plant", "my left"), both abstained, both taking 6.8-8.0 s while YOLO had
/// the GPU -- long enough to time out on the phone. It cost latency and spoke
/// nothing useful.
///
/// The trigger word ("assistant") is unaffected: that path is DELIBERATE, and
/// a question someone actually asked still reaches the router. This only stops
/// the app guessing at audio nobody addressed to it.
const bool kRouteUnmatchedSpeech = false;
