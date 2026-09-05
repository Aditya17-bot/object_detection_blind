/// Naming a colour, and judging how lit a room is, from camera pixels.
/// Direct port of `colour_naming.py` — see that file for the full reasoning.
///
/// Two capabilities that need no model at all, and that blind users reach for
/// daily: "what colour is this" (matching clothes is a constant, unglamorous
/// problem) and "is it bright in here" (you cannot tell a light was left on, it
/// costs money, and sighted neighbours notice).
///
/// **These abstain, and that is the point.** White balance and room lighting
/// move measured colour a long way, so some patches genuinely cannot be named.
/// A user matching a shirt to trousers acts on the answer and cannot check it,
/// so [nameColour] returns null for a patch too dark to judge or blown out by
/// exposure, and the caller says so rather than inventing a word.
library;

/// Below this saturation there is no hue worth naming; it is a grey.
const double _greySaturation = 0.12;

/// Darker than this and the sensor is guessing, not seeing.
const double _tooDark = 0.06;

/// Brighter than this with no colour left is a blown highlight, not white cloth.
const double _blown = 0.97;

/// Hue bands in degrees; upper bound exclusive, red wraps at both ends.
const List<(double, String)> _hues = [
  (15, 'red'),
  (40, 'orange'),
  (70, 'yellow'),
  (160, 'green'),
  (200, 'turquoise'),
  (250, 'blue'),
  (290, 'purple'),
  (330, 'pink'),
  (360, 'red'),
];

/// RGB 0-255 -> (hue 0-360, saturation 0-1, value 0-1).
(double, double, double) rgbToHsv(num r, num g, num b) {
  final rr = r / 255.0, gg = g / 255.0, bb = b / 255.0;
  final hi = [rr, gg, bb].reduce((a, b) => a > b ? a : b);
  final lo = [rr, gg, bb].reduce((a, b) => a < b ? a : b);
  final span = hi - lo;
  final s = hi <= 0 ? 0.0 : span / hi;
  if (span <= 0) return (0.0, s, hi);
  double h;
  if (hi == rr) {
    h = 60.0 * ((((gg - bb) / span) % 6) + 6) % 360;
  } else if (hi == gg) {
    h = 60.0 * (((bb - rr) / span) + 2);
  } else {
    h = 60.0 * (((rr - gg) / span) + 4);
  }
  h %= 360.0;
  if (h < 0) h += 360.0;
  return (h, s, hi);
}

String _hueName(double h) {
  for (final band in _hues) {
    if (h < band.$1) return band.$2;
  }
  return 'red';
}

/// Mean RGB of a patch -> spoken colour name, or null to abstain.
///
/// Null means "this cannot be named honestly", not "black": an unlit patch and
/// a black jumper look identical to a sensor, and the caller must say which it
/// is unable to tell.
String? nameColour(num r, num g, num b) {
  final (h, s, v) = rgbToHsv(r, g, b);

  if (v < _tooDark) return null; // too dark to distinguish from unlit
  if (v > _blown && s < 0.05) return null; // blown highlight, not a white object

  if (s < _greySaturation) {
    if (v < 0.20) return 'black';
    if (v < 0.45) return 'dark grey';
    if (v < 0.78) return 'grey';
    return 'white';
  }

  final name = _hueName(h);

  // Brown is dark orange, and it matters: a common clothing colour a pure hue
  // lookup would call "orange", which is a different garment.
  if ((name == 'orange' || name == 'yellow') && v < 0.55) return 'brown';

  if (v < 0.32) return 'dark $name';
  if (v > 0.85 && s < 0.45) return 'light $name';
  return name;
}

/// The spoken answer to "what colour is this".
String colourMessage(num r, num g, num b) {
  final name = nameColour(r, g, b);
  if (name == null) return "I can't tell the colour clearly. Try more light.";
  return name[0].toUpperCase() + name.substring(1);
}

/// Mean frame brightness 0-1 -> the spoken answer to "is the light on".
///
/// Deliberately phrased as how bright it IS, never as whether a switch is on:
/// the camera cannot know that a bulb rather than a window is doing the work,
/// and daylight through a curtain would make "the light is on" a false claim.
String lightMessage(double luma) {
  if (luma < 0.08) return "It's dark here";
  if (luma < 0.22) return "It's dim here";
  if (luma < 0.65) return "It's bright here";
  return "It's very bright here";
}
