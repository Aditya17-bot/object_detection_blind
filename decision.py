"""BlindAssist — Phase 3: decision logic.

Pure logic like position.py: no camera, no model, no real clock. Takes the
ObjectInfo list that position.analyze_box() produces for one frame, plus a
timestamp, and decides the ONE message worth speaking right now — or nothing.
Phase 4 only has to feed the returned strings to TTS.

Walk Mode   : warn about the single most important obstacle.
Find Mode   : report where the requested object is ("Bottle top right, close").
describe()  : on-demand scene summary ("A dining table ahead with 2 chairs...").

The GuidanceEngine adds the time-based rules that make speech pleasant:
persistence (ignore one-frame misdetections), repeat cooldown, minimum gap
between messages, and an escalation override so a closing obstacle is never
silenced by a cooldown.
"""

from position import OBSTACLE_CLASSES, PROXIMITY_LEVELS

# "very close" -> 3 ... "far" -> 0
_PROX_RANK = {level: rank for rank, level in enumerate(reversed(PROXIMITY_LEVELS))}

_SIDE_WORD = {"left": "on left", "center": "ahead", "right": "on right"}

# Below this confidence an obstacle warning says just "obstacle" instead of
# the class name: COCO misnames lookalikes (dustbin->"toilet",
# wardrobe->"refrigerator") and a wrong name costs the user's trust, while
# the warning itself is still worth speaking. 0.8 chosen from clip probing:
# known misnames scored 0.65-0.75, correct names >= 0.85.
NAME_CONFIDENCE = 0.8


def _cap(text):
    return text[0].upper() + text[1:]


# --------------------------------------------------------------------------
# Walk Mode
# --------------------------------------------------------------------------

def _relevant_obstacle(info):
    """Is this detection worth warning about at all?"""
    if info.name not in OBSTACLE_CLASSES:
        return False
    if info.proximity == "far":
        return False
    # medium-distance obstacles only matter when they are in the walking path
    if info.proximity == "medium" and info.h_zone != "center":
        return False
    return True


def walk_priority(info):
    """Sort key: closer wins, then more central, then bigger."""
    centrality = 1 - 2 * abs(info.center_x - 0.5)
    return (_PROX_RANK[info.proximity], centrality, info.area)


def pick_obstacle(infos):
    """The single obstacle Walk Mode should talk about, or None."""
    candidates = [i for i in infos if _relevant_obstacle(i)]
    return max(candidates, key=walk_priority) if candidates else None


def _freer_side(chosen, infos):
    """Which way to sidestep: the side with less obstacle mass on it."""
    left = right = 0.0
    for i in infos:
        if i is chosen or i.name not in OBSTACLE_CLASSES:
            continue
        if i.center_x < 0.5:
            left += i.area
        else:
            right += i.area
    if left != right:
        return "left" if left < right else "right"
    # nothing else around: step away from the side the obstacle leans to
    return "left" if chosen.center_x >= 0.5 else "right"


def walk_message(info, all_infos=()):
    """Spoken warning for the chosen obstacle. Short on purpose; vertical
    zone is irrelevant for walking, so only left/ahead/right is spoken."""
    name = info.name if info.confidence >= NAME_CONFIDENCE else "obstacle"
    side = _SIDE_WORD[info.h_zone]
    if info.proximity == "very close":
        if info.h_zone == "center":
            dodge = _freer_side(info, all_infos)
        else:  # obstacle on a side: step to the other side
            dodge = "right" if info.h_zone == "left" else "left"
        return _cap(f"{name} very close {side}, move slightly {dodge}")
    return _cap(f"{name} {side}")


# --------------------------------------------------------------------------
# Find Mode
# --------------------------------------------------------------------------

def find_target(infos, target):
    """Best visible match for the asked-for class: biggest box wins
    (closest / most visible, per spec)."""
    matches = [i for i in infos if i.name == target]
    return max(matches, key=lambda i: i.area) if matches else None


def find_message(info, target):
    if info is None:
        return _cap(f"{target} not visible")
    return _cap(f"{info.name} {info.phrase}, {info.proximity}")


# --------------------------------------------------------------------------
# Scene summary (innovation feature: on-demand "describe")
# --------------------------------------------------------------------------

_ZONE_ORDER = {"center": 0, "left": 1, "right": 2}
_ZONE_WORD = {"center": "ahead", "left": "on your left", "right": "on your right"}
_PLURALS = {"person": "people"}


def _plural(name):
    if name in _PLURALS:
        return _PLURALS[name]
    if name.endswith(("s", "sh", "ch", "x")):
        return name + "es"
    return name + "s"


def _article(name):
    return "an" if name[0] in "aeiou" else "a"


def summarize_scene(infos):
    """One sentence grouping everything visible, center first:
    'A dining table ahead, 2 chairs on your left, a person on your right'."""
    groups = {}  # (name, h_zone) -> [count, biggest area]
    for i in infos:
        entry = groups.setdefault((i.name, i.h_zone), [0, 0.0])
        entry[0] += 1
        entry[1] = max(entry[1], i.area)
    if not groups:
        return "Nothing detected"
    ordered = sorted(groups.items(),
                     key=lambda kv: (_ZONE_ORDER[kv[0][1]], -kv[1][1]))
    parts = []
    for (name, zone), (count, _) in ordered:
        what = f"{_article(name)} {name}" if count == 1 else f"{count} {_plural(name)}"
        parts.append(f"{what} {_ZONE_WORD[zone]}")
    return _cap(", ".join(parts))


# --------------------------------------------------------------------------
# Stateful engine: what to say NOW (phases 4/5 call this once per frame)
# --------------------------------------------------------------------------

class GuidanceEngine:
    """Per-frame decision maker with anti-spam rules.

    update(infos, now) -> message string to speak, or None. `now` is any
    monotonic clock in seconds (real time live, frame/fps for recorded clips)
    so behaviour is identical and testable everywhere.
    """

    def __init__(self, mode="walk", target=None,
                 repeat_cooldown=3.0, min_gap=1.5, persistence=2):
        self.repeat_cooldown = repeat_cooldown  # s before repeating same message
        self.min_gap = min_gap                  # s between any two messages
        self.persistence = persistence          # frames a class must persist
        self._streaks = {}        # class name -> consecutive frames seen
        self._last_msg = None
        self._last_time = None
        self._last_obstacle = None  # (name, prox rank) of last walk warning
        self._absent = 0            # find mode: consecutive frames w/o target
        self._said_not_visible = False
        self.set_mode(mode, target)

    def set_mode(self, mode, target=None):
        """Switch walk/find (future voice-command hook). Resets per-mode
        state but keeps the clock so min_gap still applies across switches."""
        if mode not in ("walk", "find"):
            raise ValueError(f"unknown mode {mode!r}")
        if mode == "find" and not target:
            raise ValueError("find mode needs a target class")
        self.mode = mode
        self.target = target
        self._last_msg = None
        self._last_obstacle = None
        self._absent = 0
        self._said_not_visible = False

    # -- helpers ----------------------------------------------------------

    def _clear_to_speak(self, msg, now, urgent=False):
        if self._last_time is None or urgent:
            return True
        elapsed = now - self._last_time
        if elapsed < self.min_gap:
            return False
        if msg == self._last_msg and elapsed < self.repeat_cooldown:
            return False
        return True

    def _speak(self, msg, now):
        self._last_msg = msg
        self._last_time = now
        return msg

    # -- per-frame update -------------------------------------------------

    def update(self, infos, now):
        # persistence is tracked per class name (not per zone) so an object
        # keeps its streak while the user walks and it drifts across zones;
        # one-frame misdetections never reach `persistence` and stay silent.
        self._streaks = {i.name: self._streaks.get(i.name, 0) + 1
                         for i in infos}
        if self.mode == "walk":
            return self._update_walk(infos, now)
        return self._update_find(infos, now)

    def _update_walk(self, infos, now):
        obstacle = pick_obstacle(infos)
        if obstacle is None:
            self._last_obstacle = None
            return None
        if self._streaks.get(obstacle.name, 0) < self.persistence:
            return None
        rank = _PROX_RANK[obstacle.proximity]
        # the same obstacle got closer since last warned -> safety overrides
        # every cooldown
        urgent = (self._last_obstacle is not None
                  and self._last_obstacle[0] == obstacle.name
                  and rank > self._last_obstacle[1])
        msg = walk_message(obstacle, infos)
        if not self._clear_to_speak(msg, now, urgent):
            return None
        self._last_obstacle = (obstacle.name, rank)
        return self._speak(msg, now)

    def _update_find(self, infos, now):
        match = find_target(infos, self.target)
        if match is None:
            self._absent += 1
            # say "not visible" once (after it is REALLY gone, not a flicker)
            if self._said_not_visible or self._absent < self.persistence:
                return None
            msg = find_message(None, self.target)
            if not self._clear_to_speak(msg, now):
                return None
            self._said_not_visible = True
            return self._speak(msg, now)
        self._absent = 0
        if self._streaks.get(self.target, 0) < self.persistence:
            return None
        self._said_not_visible = False
        msg = find_message(match, self.target)
        if not self._clear_to_speak(msg, now):
            return None
        return self._speak(msg, now)

    def describe(self, infos, now):
        """On-demand scene summary; stamps the clock so the next walk/find
        message still respects min_gap."""
        return self._speak(summarize_scene(infos), now)
