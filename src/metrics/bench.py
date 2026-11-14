"""A benchmark she feeds herself: numbers read off real posts, and where hers lands.

"is this good?" cannot be answered inside one post. A 3% save rate is nothing until you know
what the posts that blew up in your niche were doing, and the only honest way to know that here
is to write down what you saw. This module never contacts a platform - it works on rows she
typed and says so out loud, because a percentile built from six numbers copied off a screen is
a rough guide, not a market measurement.
"""

import math
import re
import statistics
from dataclasses import dataclass, field

MIN_COMPARABLE = 5
MIN_VIEWS = 300

_KM = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*([kKmM]?)\s*[a-zA-Z]*\s*$")
_MULTIPLIER = {"": 1, "k": 1_000, "m": 1_000_000}
# A space written between digits is a thousands separator on several platforms' screens, and
# "1 234" is the same count as "1234". It must not be confused with "89 views", where the word
# after the space is a label rather than a separator.
_SPACED_DIGITS = re.compile(r"(?<=\d)[ ,]\s*(?=\d)")


def count(text) -> int:
    """A number the way it is actually written on a screen: 12.4k, 3,400, 1 234, "89 views".

    Blank is zero, because a platform only shows some of these counts and an invented digit is
    worse than a missing one. Anything that is not a number at all raises, so the page can name
    the field that was wrong instead of quietly posting a zero.
    """
    if text is None:
        return 0
    raw = _SPACED_DIGITS.sub("", str(text).strip())
    if not raw:
        return 0
    match = _KM.match(raw.replace(",", ""))
    if not match:
        raise ValueError(f"{raw!r} is not a number")
    value, suffix = match.groups()
    # "1.2.3" and "12o0" both fail the shape above; a plain digit string must still parse.
    number = float(value)
    if number < 0:
        raise ValueError(f"{raw!r} is negative, and a count cannot be")
    return int(round(number * _MULTIPLIER[suffix.lower()]))


@dataclass
class Row:
    id: int | None = None
    label: str = ""
    platform: str = ""
    origin: str = "saw it"
    views: int = 0
    likes: int = 0
    comments: int = 0
    saves: int = 0
    shares: int = 0
    follows: int = 0
    made_at: str = ""

    @property
    def reach(self) -> float:
        return float(self.views)

    @property
    def engagement(self) -> float:
        actions = self.likes + self.comments + self.saves + self.shares
        return actions / self.views * 100 if self.views else 0.0

    @property
    def saves_per_100(self) -> float:
        return self.saves / self.views * 100 if self.views else 0.0

    @property
    def shares_per_100(self) -> float:
        return self.shares / self.views * 100 if self.views else 0.0

    @property
    def follows_per_1k(self) -> float:
        return self.follows / self.views * 1000 if self.views else 0.0

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "platform": self.platform,
                "origin": self.origin, "views": self.views, "likes": self.likes,
                "comments": self.comments, "saves": self.saves, "shares": self.shares,
                "follows": self.follows, "made_at": self.made_at}

    @classmethod
    def from_dict(cls, data: dict) -> "Row":
        return cls(id=data.get("id"), label=data.get("label", ""),
                   platform=data.get("platform", ""), origin=data.get("origin", "saw it"),
                   views=int(data.get("views", 0) or 0), likes=int(data.get("likes", 0) or 0),
                   comments=int(data.get("comments", 0) or 0),
                   saves=int(data.get("saves", 0) or 0),
                   shares=int(data.get("shares", 0) or 0),
                   follows=int(data.get("follows", 0) or 0),
                   made_at=data.get("made_at", ""))


#: key -> (what the page calls it, how to read it, per what, and the field a target must beat)
METRICS = {
    "reach": ("Views", lambda r: r.reach, "views", ""),
    "engagement": ("Actions per 100 views", lambda r: r.engagement, "per 100 views",
                   "likes + comments + saves + shares"),
    "saves": ("Saves per 100 views", lambda r: r.saves_per_100, "per 100 views", "saves"),
    "shares": ("Shares per 100 views", lambda r: r.shares_per_100, "per 100 views", "shares"),
    "new": ("New followers per 1,000 views", lambda r: r.follows_per_1k, "per 1,000 views",
            "follows gained"),
}


@dataclass
class Place:
    metric: str
    label: str = ""
    value: float = 0.0
    n: int = 0
    dropped: int = 0
    ok: bool = False
    percentile: float | None = None
    median: float | None = None
    top_decile: float | None = None
    value_text: str = ""
    median_text: str = ""
    top_text: str = ""
    percentile_text: str = ""
    needed_to_median: float | None = None
    band: str = ""
    words: list[str] = field(default_factory=list)


def usable(row: Row) -> bool:
    """A post too small to carry a rate is not in the benchmark - its percentages are noise."""
    return row.views >= MIN_VIEWS


def pool(rows: list[Row], target: Row | None = None, platform: str = "",
         origin: str = "") -> tuple[list[Row], int]:
    """The comparable rows, and how many were set aside for being too small to read."""
    kept, dropped = [], 0
    for row in rows:
        if target is not None and row.id is not None and row.id == target.id:
            continue
        if platform and row.platform != platform:
            continue
        if origin and row.origin != origin:
            continue
        if usable(row):
            kept.append(row)
        else:
            dropped += 1
    return kept, dropped


def _decile(values: list[float]) -> float:
    """The value only the highest tenth of the list reaches."""
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(0.9 * len(ordered)) - 1))]


def _shown(metric: str, value: float) -> str:
    """Views are a head count, so they get commas and no decimals; a rate keeps one decimal."""
    return f"{value:,.0f}" if metric == "reach" else f"{value:.1f}"


def ordinal(value: int) -> str:
    """33rd, not 33th. A percentile is the one number on this page that gets read out loud, and
    a wrong suffix makes the whole sentence look machine-written."""
    if 11 <= value % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def place(target: Row, rows: list[Row], metric: str, platform: str = "",
          origin: str = "") -> Place:
    """Where this post sits among the ones she wrote down - or why that cannot be said yet."""
    if metric not in METRICS:
        raise ValueError(f"unknown benchmark metric: {metric}")
    name, getter, per, _ = METRICS[metric]
    out = Place(metric=metric, label=name, value=float(getter(target)),
                value_text=_shown(metric, getter(target)))
    if not target.views:
        out.words = [f"{target.label or 'This post'} has no view count, and every rate here sits "
                     "on top of one. Without views the number is invented, so nothing is compared."]
        return out
    comparable, dropped = pool(rows, target, platform, origin)
    out.dropped = dropped
    out.n = len(comparable)
    if out.n < MIN_COMPARABLE:
        need = MIN_COMPARABLE - out.n
        out.words = [
            f"Not enough to say yet. {name} needs {MIN_COMPARABLE} comparable posts and this "
            f"list offers {out.n}"
            + (f", with {dropped} more set aside for having under {MIN_VIEWS} views"
               if dropped else "")
            + f". Add {need} more - the honest alternative is a percentile invented out of "
              f"{out.n or 1} numbers."]
        if dropped:
            out.words.append(f"A post under {MIN_VIEWS} views is left out of the comparison: at "
                             "that reach one friend can move the percentage more than the format "
                             "did.")
        return out
    values = [float(getter(row)) for row in comparable]
    below = sum(1 for v in values if v < out.value)
    out.ok = True
    out.percentile = round(below / out.n * 100)
    out.percentile_text = ordinal(out.percentile)
    out.median = round(statistics.median(values), 2)
    out.top_decile = round(_decile(values), 2)
    out.median_text = _shown(metric, out.median)
    out.top_text = _shown(metric, out.top_decile)
    if out.percentile >= 90:
        out.band = "top of this list"
    elif out.percentile >= 60:
        out.band = "above the middle of this list"
    elif out.percentile >= 40:
        out.band = "in the middle of this list"
    else:
        out.band = "under the middle of this list"
    words = [f"{out.percentile_text} of {out.n} posts you wrote down on {name.lower()} "
             f"({out.band}) - {out.value_text} {per}."]
    if out.percentile == 100:
        words[0] = (f"Above all {out.n} posts on this list on {name.lower()} - {out.value_text} "
                    f"{per}, and the highest of the ones you wrote down is {out.top_text}.")
    if out.percentile == 0:
        lowest = min(values)
        words[0] = (f"Level with the lowest of the {out.n} posts you wrote down on "
                    f"{name.lower()} - {out.value_text} {per}." if out.value == lowest else
                    f"Under all {out.n} posts on this list on {name.lower()} - {out.value_text} "
                    f"{per} against their lowest of {_shown(metric, lowest)}.")
    words.append(f"Median of the list: {out.median_text} {per}. The top post you recorded: "
                 f"{out.top_text} {per}.")
    if dropped:
        words.append(f"{dropped} of the rows in your list took no part in this, because under "
                     f"{MIN_VIEWS} views a post's percentages are decided by a handful of people "
                     "rather than by the format.")
    if out.value < out.median and "per 100" in per:
        want = out.median / 100 * target.views
        have = {"saves": target.saves, "shares": target.shares,
                "engagement": target.likes + target.comments + target.saves + target.shares}[metric]
        gap = int(round(want - have))
        if gap > 0:
            out.needed_to_median = float(gap)
            words.append(f"To sit at the median of this list you would need {gap} more "
                         f"{METRICS[metric][3]} at the same {target.views:,} views.")
    elif out.value >= out.median and "per 1,000" in per:
        words.append("That is the number the format is actually doing; whether it holds at "
                     "higher reach is a question this list cannot answer.")
    words.append("This is a comparison against the posts you typed in, not a sample of the "
                 "platform: it is only as wide as the list.")
    out.words = words
    return out


PASTE_COLUMNS = ["label", "views", "likes", "comments", "saves", "shares", "follows"]
# A screen writes ninety-eight hundred as "9,800", and a plain comma split turns that into two
# posts' worth of numbers. A comma with three digits after it and a non-digit after those is a
# thousands separator, so it is taken out before the line is ever split.
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?:\D|$))")


def parse_lines(text: str) -> tuple[list[Row], list[str]]:
    """Several posts at once, one per line, in the order printed above the box.

    A paste is the way this list actually gets filled - she is reading a screen with numbers on
    it, not filling a form six times. Trailing columns may be left off; a line that cannot be
    read is reported with its own text rather than dropped in silence.
    """
    rows, problems = [], []
    for raw in str(text or "").splitlines():
        line = _THOUSANDS.sub("", raw.strip())
        if not line:
            continue
        if line.lower().startswith("label"):
            continue
        parts = [p.strip() for p in re.split(r"[,;\t]", line) if p.strip() != ""]
        if len(parts) < 2:
            problems.append(f"{raw!r}: needs a label and at least one number, separated by a "
                            "comma.")
            continue
        try:
            numbers = [count(p) for p in parts[1:7]]
        except ValueError as exc:
            problems.append(f"{raw!r}: {exc}")
            continue
        numbers += [0] * (6 - len(numbers))
        views, likes, comments, saves, shares, follows = numbers
        if views <= 0:
            problems.append(f"{raw!r}: the first number is views, and it has to be above zero - "
                            "every other figure on the line is a share of it.")
            continue
        rows.append(Row(label=parts[0][:80], views=views, likes=likes, comments=comments,
                        saves=saves, shares=shares, follows=follows))
    return rows, problems
