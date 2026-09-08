/// Counting taps on the camera view, so one surface can carry three actions.
///
/// Flutter gives `onTap` and `onDoubleTap` and stops there, and the two
/// recognizers fight over a third tap: a triple tap arrives as a double plus a
/// single, which would run two capabilities. So the taps are counted here and
/// dispatched once the burst has settled.
///
/// The cost is that a single tap is acted on [kMultiTapWindow] later than
/// before. That is the right trade: everything on this surface is on-demand
/// (describe, sonar, guidance), none of it is a warning, and a wrong action is
/// far more expensive to a user who cannot see what happened than 450 ms is.
///
/// Pure logic, injected clock — mirrored by `multi_tap.py` only in spirit;
/// there is no desktop equivalent of the gesture, so this one has no mirror.
library;

/// How long after a tap another tap still belongs to the same gesture.
const double kMultiTapWindow = 0.45;

/// What a burst of [count] taps means. Ordered by how often it is wanted and
/// how bad it is to trigger by accident: describing the scene is harmless,
/// toggling the beeps is noticeable, and switching the continuous warnings off
/// is the one a user must not do by brushing the screen — hence three.
String? tapAction(int count) {
  if (count <= 0) return null;
  if (count == 1) return 'describe';
  if (count == 2) return 'sonar';
  return 'guidance';
}

/// Counts taps that arrive within [window] of each other.
class MultiTap {
  MultiTap({this.window = kMultiTapWindow});

  final double window;

  double _last = double.negativeInfinity;
  int _count = 0;

  /// Record a tap at [now]; returns how many taps this burst is up to.
  int tap(double now) {
    _count = (now - _last <= window) ? _count + 1 : 1;
    _last = now;
    return _count;
  }

  /// Has the burst ended — i.e. is it time to act on the count?
  bool settled(double now) => now - _last > window;

  int get count => _count;

  void reset() {
    _count = 0;
    _last = double.negativeInfinity;
  }
}
