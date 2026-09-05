"""Long-term object memory: "where did I leave my keys?"

`GuidanceEngine` already remembers where each class was last seen, but on a
30-second timer and a monotonic clock, because it exists to answer a different
question: "it just went out of frame, which way do I turn". A user asking about
their keys means hours ago, possibly before the app was last closed.

So this is a separate store, deliberately:

  * **Wall-clock time**, not the engine's monotonic clock, because a memory has
    to survive the process that made it.
  * **A long horizon** (a day by default) instead of thirty seconds.
  * **Context**, not just a frame position. "at 11 o'clock" is meaningless an
    hour later, when the user has moved. What survives is what the object was
    NEAR and what else was in the room.

**Staleness is spoken first, and that is a safety decision.** A remembered
location is a claim about the past that the user will act on in the present, and
things move. "Keys near a table" invites a wasted trip; "Keys, about two hours
ago, near a table" lets them judge for themselves. The whole store is only
honest if the age is prominent, so `recall_sentence` puts it before the place.

Pure: no clock of its own, no I/O, no model. The caller supplies the time and
owns the file. Mirrored in `lib/logic/object_memory.dart`.
"""

# Two objects this close (as a fraction of the frame diagonal) are treated as
# being together. Generous on purpose: without depth we cannot say "on", only
# "near", and a near-miss is a far cheaper error than silence.
NEAR_DISTANCE = 0.28

# How long a sighting is worth reporting at all.
DEFAULT_TTL = 24 * 3600.0

# Cap on distinct classes held, so a long session cannot grow without bound.
MAX_ENTRIES = 200

# Other classes recorded per sighting.
MAX_NEAR = 2
MAX_CONTEXT = 3


class Sighting:
    """One remembered observation of a class."""

    __slots__ = ("name", "h_zone", "center_x", "center_y", "proximity",
                 "near", "context", "at")

    def __init__(self, name, h_zone, center_x, center_y, proximity,
                 near=(), context=(), at=0.0):
        self.name = name
        self.h_zone = h_zone
        self.center_x = center_x
        self.center_y = center_y
        self.proximity = proximity
        self.near = tuple(near)        # things it was touching/beside
        self.context = tuple(context)  # other things in the room at the time
        self.at = at                   # epoch seconds

    def to_dict(self):
        return {"name": self.name, "h_zone": self.h_zone,
                "center_x": round(self.center_x, 4),
                "center_y": round(self.center_y, 4),
                "proximity": self.proximity, "near": list(self.near),
                "context": list(self.context), "at": self.at}

    @classmethod
    def from_dict(cls, d):
        return cls(d["name"], d.get("h_zone", "center"),
                   float(d.get("center_x", 0.5)),
                   float(d.get("center_y", 0.5)),
                   d.get("proximity", "medium"),
                   tuple(d.get("near", ())), tuple(d.get("context", ())),
                   float(d.get("at", 0.0)))


def _distance(a, b):
    dx = a.center_x - b.center_x
    dy = a.center_y - b.center_y
    return (dx * dx + dy * dy) ** 0.5


def ago_phrase(seconds):
    """How long ago, spoken and deliberately vague.

    Vague because precision here would be false: the sighting is timestamped to
    the frame, but what the user needs is whether it is fresh enough to trust.
    """
    s = max(0, int(round(seconds)))
    if s <= 1:
        return "just now"
    if s < 60:
        return f"{s} seconds ago"
    if s < 3600:
        m = s // 60
        return f"{m} minute{'s' if m > 1 else ''} ago"
    if s < 86400:
        h = int(round(s / 3600.0))
        return f"about {h} hour{'s' if h > 1 else ''} ago"
    d = int(s // 86400)
    return "yesterday" if d == 1 else f"{d} days ago"


def _article(name):
    return "an" if name[0].lower() in "aeiou" else "a"


def _join(names):
    names = list(names)
    if not names:
        return ""
    if len(names) == 1:
        return f"{_article(names[0])} {names[0]}"
    parts = [f"{_article(n)} {n}" for n in names]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def recall_sentence(sighting, name, now):
    """The spoken answer to "where are my keys".

    Age comes FIRST. The place is a claim about the past; the age is what tells
    the user how much to trust it, and burying it at the end of the sentence
    means it arrives after they have already decided to walk somewhere.
    """
    if sighting is None:
        return f"No memory of {_article(name)} {name}"

    when = ago_phrase(now - sighting.at)
    if sighting.near:
        where = f"near {_join(sighting.near)}"
    elif sighting.context:
        where = f"with {_join(sighting.context)} in view"
    else:
        where = None

    if where is None:
        return f"{name.capitalize()}, {when}"
    return f"{name.capitalize()}, {when}, {where}"


class ObjectMemory:
    """Where each class was last seen, with context, across sessions."""

    def __init__(self, ttl=DEFAULT_TTL, max_entries=MAX_ENTRIES,
                 near_distance=NEAR_DISTANCE):
        self.ttl = ttl
        self.max_entries = max_entries
        self.near_distance = near_distance
        self._store = {}

    # -- writing ---------------------------------------------------------

    def remember(self, infos, at):
        """Record the most visible sighting of each class in this frame."""
        if not infos:
            return
        best = {}
        for i in infos:
            if i.name not in best or i.area > best[i.name].area:
                best[i.name] = i

        present = sorted(best.values(), key=lambda i: -i.area)
        for name, info in best.items():
            near = [o.name for o in present
                    if o.name != name
                    and _distance(o, info) <= self.near_distance][:MAX_NEAR]
            context = [o.name for o in present
                       if o.name != name and o.name not in near][:MAX_CONTEXT]
            self._store[name] = Sighting(
                name, info.h_zone, info.center_x, info.center_y,
                info.proximity, near, context, at)
        self._evict(at)

    def _evict(self, at):
        for name in [n for n, s in self._store.items()
                     if at - s.at > self.ttl]:
            del self._store[name]
        if len(self._store) > self.max_entries:
            for name, _ in sorted(self._store.items(),
                                  key=lambda kv: kv[1].at
                                  )[:len(self._store) - self.max_entries]:
                del self._store[name]

    # -- reading ---------------------------------------------------------

    def get(self, name, at):
        """The live sighting for `name`, or None if absent or expired."""
        s = self._store.get(name)
        if s is None or at - s.at > self.ttl:
            return None
        return s

    def recall(self, name, at):
        """Spoken answer for `name`."""
        return recall_sentence(self.get(name, at), name, at)

    def known(self, at):
        """Classes currently remembered, most recent first."""
        live = [s for s in self._store.values() if at - s.at <= self.ttl]
        return [s.name for s in sorted(live, key=lambda s: -s.at)]

    # -- persistence -----------------------------------------------------
    # The caller owns the file: this module stays pure so it can be tested
    # without a disk, and so the phone and the web UI can store it differently.

    def to_dict(self):
        return {"version": 1,
                "sightings": [s.to_dict() for s in self._store.values()]}

    def load_dict(self, data, at=None):
        """Replace the store from `to_dict` output. Malformed entries are
        skipped rather than raising: a corrupt memory file must not stop the
        app from starting."""
        if not isinstance(data, dict):
            return
        for raw in data.get("sightings", []):
            try:
                s = Sighting.from_dict(raw)
            except Exception:            # noqa: BLE001 - skip bad records
                continue
            if s.name:
                self._store[s.name] = s
        if at is not None:
            self._evict(at)
