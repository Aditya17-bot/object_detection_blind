"""Naming a colour, and judging how lit a room is, from camera pixels.

Two capabilities that need no model at all, and that blind users reach for
daily: "what colour is this" (matching clothes is a constant, unglamorous
problem) and "is it bright in here" (you cannot tell that a light was left on,
it costs money, and sighted neighbours notice).

Both are pure functions over already-computed pixel means, mirrored in
`lib/logic/colour_naming.dart`, so the whole thing is unit-testable without a
camera, a device or a plugin — the rule the rest of `logic/` follows.

**These abstain, and that is the point.** A camera's white balance and the room
lighting move measured colour a long way, so there are patches this genuinely
cannot name. Guessing at those is worse than useless here: a user matching a
shirt to trousers acts on the answer and cannot check it. `name_colour` returns
None for a patch that is too dark to judge or blown out by exposure, and the
caller says so rather than inventing a word. Same principle as the naming
head's margin test and the router's abstention — say less, never mislead.
"""

# Below this saturation there is no hue worth naming; it is a grey.
_GREY_SATURATION = 0.12

# Darker than this and the sensor is guessing, not seeing.
_TOO_DARK = 0.06
# Brighter than this with no colour left is a blown highlight, not white cloth.
_BLOWN = 0.97

# Hue bands in degrees. Upper bound is exclusive; red wraps at both ends.
_HUES = (
    (15, "red"),
    (40, "orange"),
    (70, "yellow"),
    (160, "green"),
    (200, "turquoise"),
    (250, "blue"),
    (290, "purple"),
    (330, "pink"),
    (360, "red"),
)


def rgb_to_hsv(r, g, b):
    """RGB 0-255 -> (hue 0-360, saturation 0-1, value 0-1)."""
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    hi, lo = max(r, g, b), min(r, g, b)
    v = hi
    span = hi - lo
    s = 0.0 if hi <= 0 else span / hi
    if span <= 0:
        return 0.0, s, v
    if hi == r:
        h = 60.0 * (((g - b) / span) % 6)
    elif hi == g:
        h = 60.0 * (((b - r) / span) + 2)
    else:
        h = 60.0 * (((r - g) / span) + 4)
    return h % 360.0, s, v


def _hue_name(h):
    for upper, name in _HUES:
        if h < upper:
            return name
    return "red"


def name_colour(r, g, b):
    """Mean RGB of a patch -> spoken colour name, or None to abstain.

    None means "this cannot be named honestly", not "black": an unlit patch and
    a black jumper look identical to a sensor, and the caller must say which it
    is not able to tell.
    """
    h, s, v = rgb_to_hsv(r, g, b)

    if v < _TOO_DARK:
        return None                      # too dark to distinguish from unlit
    if v > _BLOWN and s < 0.05:
        return None                      # blown highlight, not a white object

    if s < _GREY_SATURATION:
        if v < 0.20:
            return "black"
        if v < 0.45:
            return "dark grey"
        if v < 0.78:
            return "grey"
        return "white"

    name = _hue_name(h)

    # Brown is dark orange, and it matters: it is a common clothing colour that
    # a pure hue lookup would call "orange", which is a different garment.
    if name in ("orange", "yellow") and v < 0.55:
        return "brown"

    if v < 0.32:
        return "dark " + name
    if v > 0.85 and s < 0.45:
        return "light " + name
    return name


def colour_message(r, g, b):
    """The spoken answer to 'what colour is this'."""
    name = name_colour(r, g, b)
    if name is None:
        return "I can't tell the colour clearly. Try more light."
    return name[0].upper() + name[1:]


# --- room brightness --------------------------------------------------------
# Deliberately phrased as how bright it IS, never as whether a switch is on:
# the camera cannot know that a bulb rather than a window is doing the work,
# and daylight through a curtain would make "the light is on" a false claim.

def light_message(luma):
    """Mean frame brightness 0-1 -> the spoken answer to 'is the light on'."""
    if luma < 0.08:
        return "It's dark here"
    if luma < 0.22:
        return "It's dim here"
    if luma < 0.65:
        return "It's bright here"
    return "It's very bright here"
