"""The pitch, built only out of what she gave and what her own import says.

Three questions get answered here and no others: what she has to offer (arithmetic on the posts
she imported, never a number from someone else's account), what the message should say (her reason
for wanting this particular person, her ask, one line of her own numbers), and where her asks
actually got to (the stages she moves herself, because nothing here can see a reply).

The two rules that cost something: a reason this file invented is a lie she would have to send, so
`why` and `ask` come from her or the pitch is not written; and a median struck from one post is one
afternoon that went well, so it is printed as that and the pitch is told not to lean on it.
"""

from dataclasses import dataclass
from statistics import median

# One post is not a rate. Below this the number is still shown, labelled for what it is.
MIN_POSTS = 2
# Below this, "answered out of asked" is an anecdote about specific people, not a reply rate.
MIN_ASKS = 5
# The stages are hers to move: this app cannot see a reply, so it never moves one by itself.
STATUSES = ("to pitch", "pitched", "replied", "no answer", "made something")
UNNAMED = ("", "logged", "unknown")

CANNOT = (
    "what the other account reaches - this app reads your exports, not theirs, and no platform "
    "publishes another account's numbers to an app with no server and no login",
    "whether a pitch was sent, seen or answered - a stage moves only when you say it did",
    "who to pitch: nothing here searches, scrapes or ranks creators, so every name on the list "
    "is one you found yourself",
    "what any of it is worth in followers: a collaboration is two audiences meeting once, and "
    "which way it moves is decided by the thing you make, not by this list",
)


@dataclass(frozen=True)
class Offer:
    platform: str
    posts: int
    median_views: int
    watch_pct: float
    follows_per_1000: float
    thin: bool

    def line(self) -> str:
        """The one sentence a pitch could carry, phrased to what the number can actually hold."""
        posts = f"{self.posts} post{'' if self.posts == 1 else 's'}"
        if self.thin:
            return (f"{posts} on {self.platform}, the best of them {self.median_views:,} views - "
                    "that is one afternoon that went well, not a rate, so the work has to do the "
                    "talking")
        return (f"a median of {self.median_views:,} views across {posts} on {self.platform}, "
                f"{self.watch_pct}% watched through, {self.follows_per_1000} follows per 1000 "
                "views")

    def as_dict(self) -> dict:
        return {"platform": self.platform, "posts": self.posts, "median_views": self.median_views,
                "watch_pct": self.watch_pct, "follows_per_1000": self.follows_per_1000,
                "thin": self.thin, "line": self.line()}


def offers(rows) -> list:
    """Her own numbers per platform, from the import and nothing else."""
    by: dict[str, list] = {}
    for r in rows or []:
        platform = (getattr(r, "platform", "") or "").strip().lower()
        views = int(getattr(r, "views", 0) or 0)
        if platform in UNNAMED or views <= 0:
            continue
        by.setdefault(platform, []).append(r)
    out = []
    for platform, items in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        views = sorted(int(getattr(r, "views", 0) or 0) for r in items)
        watch = sorted(round(float(getattr(r, "avg_watch_pct", 0) or 0), 1) for r in items)
        follows = sum(max(0, int(getattr(r, "follows_gained", 0) or 0)) for r in items)
        total = sum(views)
        out.append(Offer(platform=platform, posts=len(items), median_views=int(median(views)),
                         watch_pct=float(median(watch)) if watch else 0.0,
                         follows_per_1000=round(follows / total * 1000, 2) if total else 0.0,
                         thin=len(items) < MIN_POSTS))
    return out


def best(offers_got, platform: str = ""):
    """The offer to lead with: the one she named, or the platform with the most posts behind it."""
    if not offers_got:
        return None
    if platform:
        want = (platform or "").strip().lower()
        for o in offers_got:
            if o.platform == want:
                return o
    return offers_got[0]


def pitch(name: str, why: str, ask: str = "", offer: Offer = None,
          format_: str = "") -> dict:
    """The message, in four moves, with nothing in it that did not come from her or her import.

    A specific reason, what she would actually make, one line of her own numbers, and a yes small
    enough to say. `held` lists what the pitch could not say and why - including the common case
    of having no number worth quoting yet, which is a reason to lead with the work rather than a
    reason to invent a figure.
    """
    lines, held = [], []
    why = (why or "").strip()
    ask = (ask or "").strip()
    format_ = (format_ or "").strip()
    if not why:
        held.append("no reason: a pitch with a reason this app made up is a lie you would have "
                    "to send, so nothing is written")
        return {"lines": [], "held": held, "text": "", "numbers": "",
                "name": (name or "").strip(), "ask": ask, "cannot": list(CANNOT)}

    lines.append(f"Here is the specific thing: {why}")
    if ask:
        lines.append(f"What I would make with you: {ask}"
                     + (f" - {format_}, one version, your call on the rest" if format_ else ""))
    else:
        lines.append("I would rather ask for one thing than say 'let's collab sometime', so: "
                     "tell me what would be easy to say yes to")
        held.append("no ask: you did not say what you want out of this, and a pitch without one is "
                    "the most common way they stall")

    if offer is not None:
        lines.append(f"On my side: {offer.line()}.")
        if offer.thin:
            held.append(f"the {offer.platform} number is {offer.posts} post"
                        f"{'s' if offer.posts != 1 else ''}, so it is quoted as what it is rather "
                        "than as a rate")
    else:
        lines.append("On my side: the work, because I would rather you judged it than a number.")
        held.append("no number: nothing has been imported for that platform, so the pitch leads "
                    "with the work instead of an invented figure")

    lines.append("If it is not a fit, no worries - I'll keep posting either way.")
    return {"lines": lines, "held": held, "text": "\n".join(lines),
            "numbers": offer.line() if offer else "",
            "name": (name or "").strip(), "ask": ask, "cannot": list(CANNOT)}


def brief_for(candidate: dict, offers_got) -> dict:
    """The pitch for a candidate already on the list, led by the platform she filed it under.

    Kept as one call rather than three lines at each caller because the field names differ on
    purpose: a stored row says `format`, which is a Python keyword, so the argument it becomes
    is `format_` - and a caller that got that wrong would quietly drop the shape of the work.
    """
    return pitch(str(candidate.get("name", "") or ""), str(candidate.get("why", "") or ""),
                 str(candidate.get("ask", "") or ""),
                 best(offers_got, str(candidate.get("platform", "") or "")),
                 str(candidate.get("format", "") or ""))


def usable(status: str) -> bool:
    return (status or "").strip().lower() in STATUSES


def funnel(candidates) -> dict:
    """Where her own asks got to, and whether there are enough of them to mean anything."""
    counts = {s: 0 for s in STATUSES}
    for c in candidates or []:
        status = (c.get("status") or "").strip().lower()
        if status in counts:
            counts[status] += 1
    asked = counts["pitched"] + counts["replied"] + counts["no answer"] + counts["made something"]
    answered = counts["replied"] + counts["made something"]
    rate = round(answered / asked * 100, 1) if asked else None
    if not asked:
        meaning = ("nothing has been marked as sent yet, so there is no reply rate to work out - "
                   "the list is a list of people you want to work with, which is its own use")
    elif asked < MIN_ASKS:
        meaning = (f"{answered} answered out of {asked} sent is not a rate yet: at {asked} ask"
                   f"{'s' if asked != 1 else ''} one friendly person or one bad week moves the "
                   f"number to {rate}% on its own")
    else:
        meaning = (f"{answered} of {asked} answered, {rate}% - enough asks that the number could "
                   "be worth comparing the next batch against")
    return {"counts": counts, "asked": asked, "answered": answered, "rate": rate,
            "list_n": len(candidates or []), "meaning": meaning,
            "waiting": counts["to pitch"], "min_asks": MIN_ASKS}
