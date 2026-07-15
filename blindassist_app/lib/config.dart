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

/// The laptop's LAN IP and the infer_server.py port. Phone and laptop must be
/// on the same Wi-Fi/hotspot. Update the IP to match `ipconfig` on the laptop.
const String kServerHost = '172.17.77.158';
const int kServerPort = 5001;
