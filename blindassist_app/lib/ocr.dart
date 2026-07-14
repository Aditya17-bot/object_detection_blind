// BlindAssist — OCR text reader. On-demand ("read"), the app captures a still
// photo and Google ML Kit's on-device text recognizer extracts printed text
// (labels, signs, mail) to be spoken aloud. Fully offline — the Latin model
// ships with the plugin. Kept tiny and injectable so the recognizer's heavy
// native handle is created once and disposed cleanly.
import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';

class OcrReader {
  final TextRecognizer _recognizer =
      TextRecognizer(script: TextRecognitionScript.latin);

  /// Recognize text in the image at [path]. Returns the joined text, or an
  /// empty string when nothing readable is found. Lines are flattened to a
  /// single spoken run (block order preserved).
  Future<String> readFile(String path) async {
    final input = InputImage.fromFilePath(path);
    final result = await _recognizer.processImage(input);
    // collapse ML Kit's block/line structure into one clean spoken string
    return result.text.replaceAll(RegExp(r'\s+'), ' ').trim();
  }

  void dispose() => _recognizer.close();
}
