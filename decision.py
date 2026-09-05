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

from position import OBSTACLE_CLASSES, PROXIMITY_LEVELS, clock_phrase

# "very close" -> 3 ... "far" -> 0
_PROX_RANK = {level: rank for rank, level in enumerate(reversed(PROXIMITY_LEVELS))}

_SIDE_WORD = {"left": "on left", "center": "ahead", "right": "on right"}


def _distance_or_bucket(info):
    """What to say after a Find location: a rough "about N meters" for a
    medium/far object when we have a TRUSTWORTHY metric estimate, otherwise the
    coarse proximity bucket. Guards (all must hold to speak meters):
      - a distance exists (known class height, box not edge-clipped),
      - confidence >= NAME_CONFIDENCE (a misdetected class = wrong real-height
        = confidently wrong meters),
      - the object is medium/far (up close the pinhole estimate is worst and
        the bucket already means "here").
    Deliberately Find-mode only — Walk warnings stay short and bucket-based."""
    d = getattr(info, "distance_m", None)
    if (d is not None and info.confidence >= NAME_CONFIDENCE
            and info.proximity in ("medium", "far")):
        m = max(1, int(round(d)))
        return f"about {m} meter" + ("s" if m != 1 else "")
    return info.proximity

# Below this confidence an obstacle warning says just "obstacle" instead of
# the class name: COCO misnames lookalikes (dustbin->"toilet",
# wardrobe->"refrigerator") and a wrong name costs the user's trust, while
# the warning itself is still worth speaking. 0.8 chosen from clip probing:
# known misnames scored 0.65-0.75, correct names >= 0.85.
NAME_CONFIDENCE = 0.8

# Classes from the DEDICATED custom model (door_dustbin_stairs), not COCO. The
# NAME_CONFIDENCE gate exists only because COCO misnames lookalikes; these have
# no lookalike to confuse, so their name is always trustworthy and bypasses the
# gate — otherwise a real door at 0.5-0.79 conf is spoken as generic "obstacle"
# and the user thinks door detection failed.
TRUSTED_NAME_CLASSES = {"door", "dustbin"}


def _cap(text):
    return text[0].upper() + text[1:]


# --------------------------------------------------------------------------
# Walk Mode
# --------------------------------------------------------------------------

# Walk Mode speaks ONLY at this proximity or nearer. Field feedback
# 2026-07-31: continuous naming of everything in the room ("too much of a
# cluster") drowned the warnings that mattered — the user stops listening, and
# an ignored warning is worth less than silence. Medium obstacles are therefore
# silent even dead ahead; the full inventory moved to describe(), which is
# on-demand and cannot interrupt anything.
WALK_MIN_PROXIMITY = "close"


def _relevant_obstacle(info):
    """Is this detection worth warning about at all?"""
    if info.name not in OBSTACLE_CLASSES:
        return False
    return _PROX_RANK[info.proximity] >= _PROX_RANK[WALK_MIN_PROXIMITY]


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


def _spoken_name(info):
    """The class name, or "obstacle" when the label is not trustworthy enough
    to say out loud (see NAME_CONFIDENCE / TRUSTED_NAME_CLASSES).

    Three ways a name earns the right to be spoken, in order of evidence:

    1. `info.trusted_name` — the embedding naming head committed a rename, or
       the detection came from the dedicated door/dustbin model. This is the
       STRONGEST signal and the only calibrated one: a rename had to beat every
       competing label by MIN_MARGIN and survive hysteresis.
    2. `TRUSTED_NAME_CLASSES` — a class with no COCO lookalike to confuse.
    3. `confidence >= NAME_CONFIDENCE` — the legacy gate, kept for un-renamed
       COCO detections only. Its stated basis is FALSIFIED (EVALUATION.md
       section 6.2): misnames and correct names occupy overlapping confidence
       bands, so no threshold separates them. It survives because it is still a
       weak prior against speaking a low-confidence guess by name, not because
       the number means what the original probe claimed.
    """
    if (info.trusted_name
            or info.name in TRUSTED_NAME_CLASSES
            or info.confidence >= NAME_CONFIDENCE):
        return info.name
    return "obstacle"


def walk_message(info, all_infos=(), use_clock=False):
    """Spoken warning for the chosen obstacle. Short on purpose; vertical
    zone is irrelevant for walking, so only left/ahead/right (or the clock
    bearing when use_clock) is spoken."""
    name = _spoken_name(info)
    side = clock_phrase(info.center_x) if use_clock else _SIDE_WORD[info.h_zone]
    if info.proximity == "very close":
        if info.h_zone == "center":
            dodge = _freer_side(info, all_infos)
        else:  # obstacle on a side: step to the other side
            dodge = "right" if info.h_zone == "left" else "left"
        return _cap(f"{name} very close {side}, move slightly {dodge}")
    # Walk stays short + bucket-based (no meters): the actionable token is the
    # direction, and metric range would only lengthen a continuous warning.
    return _cap(f"{name} {side}, {info.proximity}")


# --------------------------------------------------------------------------
# Clear-path finder (innovation feature: "which way is open?")
# --------------------------------------------------------------------------
# On demand (voice "clear path" / "which way"), report the emptiest of the
# three walking directions. Sums the box area of every near obstacle per
# horizontal third; the third with the least obstacle mass wins, straight
# ahead preferred on a tie. Coarse and cheap — reuses the same ObjectInfo list.

_PATH_WORD = {
    "center": "Path clear ahead",
    "left": "Clearest on your left",
    "right": "Clearest on your right",
}


def clear_path(infos):
    """Spoken guidance toward the most open direction, or "Stop" if none is.

    Each third is scored by its CLOSEST obstacle (proximity rank), not summed
    box area — a nearby small hazard must outweigh a far bulky one. Doors are
    excluded (a doorway is the thing you want to walk THROUGH, not around), and
    far obstacles are ignored. If even the emptiest third has a close/very-close
    obstacle, we refuse to call it "clear" and say to stop.
    Known limit: ObjectInfo carries only the box center, so a wide object that
    straddles thirds is scored in its center third only (add box extent later).
    """
    ranks = {"left": -1, "center": -1, "right": -1}  # -1 = nothing near
    for i in infos:
        if i.name not in OBSTACLE_CLASSES or i.name == "door":
            continue
        if i.proximity == "far":
            continue
        r = _PROX_RANK[i.proximity]
        if r > ranks[i.h_zone]:
            ranks[i.h_zone] = r
    # emptiest third wins; center-first so ties resolve to "ahead"
    best = min(("center", "left", "right"), key=lambda z: ranks[z])
    if ranks[best] >= _PROX_RANK["close"]:
        return "Stop, no clear path"
    return _PATH_WORD[best]


# --------------------------------------------------------------------------
# Directional query ("is there anything on my left?")
# --------------------------------------------------------------------------
# The question a blind user actually asks, and the one the old command set
# could not answer: walk mode volunteers ONE obstacle, describe() dumps the
# whole room, and neither answers "what is over there". This is deliberately
# DETERMINISTIC and lives in tier 0, so it works with the laptop switched off
# and its answer can never be a language model's invention.

_DIRECTIONS = ("left", "ahead", "right")
_DIR_ZONE = {"left": "left", "ahead": "center", "right": "right"}
_DIR_WORD = {"left": "on your left", "ahead": "ahead", "right": "on your right"}
_CHECK_LIMIT = 2   # two things is an answer; five is another cluster


def check_direction(infos, direction):
    """What is in one third of the frame, closest first.

    Reports everything detected there (not just OBSTACLE_CLASSES) — the user
    asked, so a cup on the table is a legitimate answer. Distance stays a
    bucket: this is an orientation question, not a navigation one.
    """
    if direction not in _DIR_ZONE:
        return None          # caller abstains; never guess a direction
    zone = _DIR_ZONE[direction]
    here = [i for i in infos if i.h_zone == zone]
    if not here:
        return _cap(f"nothing {_DIR_WORD[direction]}")
    here.sort(key=lambda i: (_PROX_RANK[i.proximity], i.area), reverse=True)
    first = here[0]
    parts = [f"{_article(_spoken_name(first))} {_spoken_name(first)} "
             f"{first.proximity} {_DIR_WORD[direction]}"]
    for extra in here[1:_CHECK_LIMIT]:
        name = _spoken_name(extra)
        parts.append(f"and {_article(name)} {name} {extra.proximity}")
    return _cap(", ".join(parts))


# --------------------------------------------------------------------------
# Find Mode
# --------------------------------------------------------------------------

def find_target(infos, target):
    """Best visible match for the asked-for class: biggest box wins
    (closest / most visible, per spec)."""
    matches = [i for i in infos if i.name == target]
    return max(matches, key=lambda i: i.area) if matches else None


def find_message(info, target, use_clock=False):
    if info is None:
        return _cap(f"{target} not visible")
    where = clock_phrase(info.center_x) if use_clock else info.phrase
    return _cap(f"{info.name} {where}, {_distance_or_bucket(info)}")


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


def count_message(infos, target):
    """Spoken count of one class currently visible (voice: 'how many chairs')."""
    n = sum(1 for i in infos if i.name == target)
    if n == 0:
        return _cap(f"no {_plural(target)}")
    if n == 1:
        return _cap(f"1 {target}")
    return _cap(f"{n} {_plural(target)}")


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
# Object memory (innovation feature: recall where a thing was last seen)
# --------------------------------------------------------------------------
# A blind user often loses track of an object the moment it leaves the frame.
# The engine remembers the last sighting of every class and can answer "where
# is my cup?" — or volunteer "last seen on your right" the instant a Find target
# drops out of view. Deliberately coarse (zone + how-long-ago, never metric):
# a memory older than memory_ttl is treated as stale and forgotten.

_MEM_WORD = {"left": "on your left", "center": "ahead", "right": "on your right"}


def _ago_phrase(seconds):
    """Human 'how long ago', spoken and vague on purpose."""
    s = int(round(seconds))
    if s <= 1:
        return "a moment ago"
    if s < 60:
        return f"{s} seconds ago"
    m = s // 60
    return f"{m} minute{'s' if m > 1 else ''} ago"


def recall_message(info, seconds_ago, name, use_clock=False):
    """Spoken memory of a class, or that there is none. `info` is the last
    ObjectInfo seen for `name` (None if never/expired)."""
    if info is None:
        article = "an" if name[0] in "aeiou" else "a"
        return _cap(f"no memory of {article} {name}")
    where = clock_phrase(info.center_x) if use_clock else _MEM_WORD[info.h_zone]
    return _cap(f"{name} last seen {where}, {_ago_phrase(seconds_ago)}")


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
                 repeat_cooldown=3.0, min_gap=1.5, persistence=2,
                 reminder_interval=10.0, use_clock=True, memory_ttl=30.0,
                 find_persistence=1, absence_grace=2.5, miss_decay=0.5):
        self.repeat_cooldown = repeat_cooldown  # s before repeating same message
        self.min_gap = min_gap                  # s between any two messages
        self.persistence = persistence          # frames a class must persist
        # Find mode is DELIBERATELY more eager than walk mode, because the
        # errors are not symmetric. The user ASKED for this object: announcing
        # a misdetection costs them one wasted look, while staying silent about
        # an object that is on screen reads as "the app is broken" — and a
        # blind user cannot glance at the screen to find out which it was.
        # Measured on the 2026-09-05 room walk: at the phone's real 2 FPS the
        # person was detected in runs of [1,1,1,1,2,2] frames, so requiring two
        # CONSECUTIVE frames missed four of six sightings and announced "not
        # visible" while the person was in frame.
        self.find_persistence = find_persistence
        # ...and the reverse claim needs MORE evidence, not less. Saying "not
        # visible" about something visible is the expensive error, so absence
        # is measured in SECONDS of continuous non-detection rather than in
        # frames, which also stops the threshold meaning different things on a
        # 2 FPS phone and a 6 FPS laptop.
        self.absence_grace = absence_grace
        # Evidence DECAYS, it is not erased. A single missed frame used to
        # reset a streak to zero, so an object detected on alternate frames
        # never accumulated anything. A lone misdetection still decays away
        # without ever reaching `persistence`, so false positives are not made
        # more likely by this.
        self.miss_decay = miss_decay
        self.reminder_interval = reminder_interval  # s between "still looking"
        self.use_clock = use_clock              # clock bearings vs left/right
        self.memory_ttl = memory_ttl            # s before a sighting goes stale
        self._streaks = {}        # class name -> consecutive frames seen
        self._memory = {}         # class name -> (last ObjectInfo, time seen)
        self._last_msg = None
        self._last_time = None
        self._last_obstacle = None  # (name, prox rank) of last walk warning
        self._absent_since = None   # find mode: when the target went missing
        self._said_not_visible = False
        self._not_visible_time = None  # when "not visible"/reminder last said
        self.set_mode(mode, target)

    def set_clock(self, on):
        """Toggle clock-face bearings (voice: 'clock mode' / 'zone mode')."""
        self.use_clock = bool(on)

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
        self._absent_since = None
        self._said_not_visible = False
        self._not_visible_time = None

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

    def _remember(self, infos, now):
        """Store the most visible sighting of each class this frame, so the
        object memory survives after things leave the frame."""
        best = {}
        for i in infos:
            if i.name not in best or i.area > best[i.name].area:
                best[i.name] = i
        for name, info in best.items():
            self._memory[name] = (info, now)

    def recall(self, name, now):
        """Object-memory query: where `name` was last seen. Runs in any mode
        (voice: 'where is my cup?'). Stale memories (> memory_ttl) are gone."""
        entry = self._memory.get(name)
        if entry is None or now - entry[1] > self.memory_ttl:
            return recall_message(None, 0, name, self.use_clock)
        info, seen = entry
        return recall_message(info, now - seen, name, self.use_clock)

    def update(self, infos, now):
        # persistence is tracked per class name (not per zone) so an object
        # keeps its streak while the user walks and it drifts across zones;
        # one-frame misdetections never reach `persistence` and stay silent.
        seen = {i.name for i in infos}
        cap = max(self.persistence, self.find_persistence) + 1.0
        decayed = {}
        for name in set(self._streaks) | seen:
            prev = self._streaks.get(name, 0.0)
            score = min(prev + 1.0, cap) if name in seen                 else prev - self.miss_decay
            if score > 0:
                decayed[name] = score
        self._streaks = decayed
        self._remember(infos, now)
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
        msg = walk_message(obstacle, infos, self.use_clock)
        if not self._clear_to_speak(msg, now, urgent):
            return None
        self._last_obstacle = (obstacle.name, rank)
        return self._speak(msg, now)

    def _update_find(self, infos, now):
        match = find_target(infos, self.target)
        if match is None:
            if self._absent_since is None:
                self._absent_since = now
            # Not "gone" until it has been continuously missing for a while.
            # One dropped frame — or one flicker in the detector — is not
            # evidence of absence, and calling it absence is what made the app
            # announce "Person not visible" with the person on screen.
            if now - self._absent_since < self.absence_grace:
                return None
            if self._said_not_visible:
                # target still missing: remind periodically so long silence
                # never reads as "the app stopped working" (a blind user
                # cannot glance at the screen to check)
                if now - self._not_visible_time < self.reminder_interval:
                    return None
                msg = _cap(f"still looking for {self.target}")
                if not self._clear_to_speak(msg, now):
                    return None
                self._not_visible_time = now
                return self._speak(msg, now)
            # object memory: the instant the target drops out, say where it
            # was — turns a dead-end "not visible" into a lead to follow.
            entry = self._memory.get(self.target)
            if entry is not None and now - entry[1] <= self.memory_ttl:
                info = entry[0]
                where = (clock_phrase(info.center_x) if self.use_clock
                         else _MEM_WORD[info.h_zone])
                msg = _cap(f"{self.target} not visible, last seen {where}")
            else:
                msg = find_message(None, self.target)
            if not self._clear_to_speak(msg, now):
                return None
            self._said_not_visible = True
            self._not_visible_time = now
            return self._speak(msg, now)
        self._absent_since = None
        if self._streaks.get(self.target, 0) < self.find_persistence:
            return None
        self._said_not_visible = False
        msg = find_message(match, self.target, self.use_clock)
        if not self._clear_to_speak(msg, now):
            return None
        # Search is COMPLETE once the target has been announced (user decision
        # 2026-07-16: repeating the position while the target stays in view
        # reads as "it's still searching"). Speak the position once, then drop
        # back to walk mode; asking again ("find person") starts a new search.
        spoken = self._speak(msg, now)
        self.set_mode("walk")
        return spoken

    def describe(self, infos, now):
        """On-demand scene summary; stamps the clock so the next walk/find
        message still respects min_gap."""
        return self._speak(summarize_scene(infos), now)

    def count(self, infos, target, now):
        """On-demand count of one class ('how many chairs'); stamps the clock
        like describe()."""
        return self._speak(count_message(infos, target), now)

    def path(self, infos, now):
        """On-demand clear-path guidance; stamps the clock like describe()."""
        return self._speak(clear_path(infos), now)

    def check(self, infos, direction, now):
        """On-demand directional query ('anything on my left?'); stamps the
        clock like describe(). None (unknown direction) is passed straight
        through so the caller can abstain instead of inventing an answer."""
        msg = check_direction(infos, direction)
        return self._speak(msg, now) if msg else None
