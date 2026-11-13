"""Spec 5.7: the scheduler starts on a default it admits to, then stops guessing.

The default is not a reach claim. It is one window she can hold for three weeks, chosen for the
same reason a shift is chosen - because it exists in her week. The measured side stays silent
until at least SLOT_FLOOR posts carry a clock time on them, which is roughly where a median stops
being one lucky afternoon.

No vendor chart is quoted here. The two biggest published ones name opposite days for the same
platform, which is the whole reason this app refuses to pick a time off somebody else's account.
"""

from dataclasses import dataclass, field
from statistics import median

# Spec §5.7: "after roughly 20 posts, defaults are replaced by observed data".
SLOT_FLOOR = 20
# A window holding two posts has no median, it has an anecdote.
BUCKET_FLOOR = 3

# Coarse on purpose. An hour-by-hour table from twenty posts is noise dressed as a histogram.
BLOCKS = [("morning", 5, 11), ("midday", 11, 15), ("evening", 15, 20), ("late", 20, 29)]


def block_of(hour: int) -> str:
    h = hour if hour >= 5 else hour + 24
    for name, start, end in BLOCKS:
        if start <= h < end:
            return name
    return "morning"


@dataclass
class Window:
    block: str
    hours: str
    posts: int
    median_views: int
    median_follow_rate: float
    share: float

    @property
    def thin(self) -> bool:
        return self.posts < BUCKET_FLOOR


@dataclass
class SlotReport:
    timed: int
    total: int
    measured: bool
    windows: list[Window] = field(default_factory=list)
    thin: list[Window] = field(default_factory=list)
    note: str = ""

    @property
    def need(self) -> int:
        return max(0, SLOT_FLOOR - self.timed)


def _window(items, timed: int) -> Window:
    rates = [r.follow_rate_per_1000 for r in items]
    return Window(
        block=block_of(items[0].posted_hour),
        hours=next(f"{s:02d}:00-{e % 24:02d}:00" for n, s, e in BLOCKS if n == block_of(items[0].posted_hour)),
        posts=len(items),
        median_views=int(median(r.views for r in items)),
        median_follow_rate=round(median(rates), 2),
        share=round(len(items) / timed, 2) if timed else 0.0,
    )


def report(rows) -> SlotReport:
    """Rank her own posting windows, or refuse to and say what is missing."""
    timed_rows = [r for r in rows if getattr(r, "posted_hour", None) is not None]
    total, timed = len(rows), len(timed_rows)

    if timed < SLOT_FLOOR:
        if not total:
            note = ("Nothing has been imported yet, so there is no window here - not a guessed "
                    "one and not a measured one.")
        elif not timed:
            note = (f"{total} posts read, none of them carrying a time. Until a post knows the "
                    "hour it went out, there is nothing to rank: add the clock time to the "
                    "numbers you paste (a trailing 18:40 on the line is enough).")
        else:
            missing = total - timed
            note = f"{timed} of the {SLOT_FLOOR} timed posts this page needs"
            note += (f", from {total} read, {missing} of them without a clock time on the row."
                     if missing else ".")
        if total:
            note += (" Until then the slot on your plan stays a default - the window that fits "
                     "your week, which is a decision about your week, not a claim about reach.")
        return SlotReport(timed=timed, total=total, measured=False, note=note)

    groups: dict[str, list] = {}
    for row in timed_rows:
        groups.setdefault(block_of(row.posted_hour), []).append(row)
    built = sorted((_window(items, timed) for items in groups.values()),
                   key=lambda w: w.median_views, reverse=True)
    # There is no "every window is too thin" branch: four coarse blocks and twenty posts cannot
    # be spread that way, and finer buckets would be reading a pattern out of one afternoon.
    solid = [w for w in built if not w.thin]
    if len(solid) == 1:
        only = solid[0]
        note = (f"Replaced at {timed} timed posts, and every solid one sits in the same window: "
                f"{only.block} {only.hours}, {only.posts} posts, median {only.median_views} views. "
                "That is a schedule, not a comparison - nothing went out anywhere else, so this "
                "page cannot claim the window works, only that it is where your posts are. The "
                "test that would say something is your usual format once in a different block.")
        return SlotReport(timed=timed, total=total, measured=True, windows=solid,
                          thin=[w for w in built if w.thin], note=note)

    top, bottom = solid[0], solid[-1]
    note = (f"Replaced at {timed} timed posts. Median views by window: "
            + ", ".join(f"{w.block} {w.median_views} ({w.posts})" for w in solid)
            + f". The gap worth acting on is {top.block} against {bottom.block} - "
            f"{top.median_views} against {bottom.median_views}. What you post at one hour is not "
            "what you post at another, and your export cannot separate the two, so the move this "
            "supports is one test: put your best-performing format in the weaker window and see "
            "whether the window or the format was doing the work.")
    return SlotReport(timed=timed, total=total, measured=True, windows=solid,
                      thin=[w for w in built if w.thin], note=note)
