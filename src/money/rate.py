"""What a paid post is worth here, worked out twice: once from her numbers, once from her cost.

Nothing in this file speaks to a brand, finds a deal, signs anything or converts a currency.
It reads three things that already exist - the metrics she imported, the priced claims in the
playbook, and two numbers she types herself - and does arithmetic she can check line by line:

    median views, from her own posts          x a published cost per thousand  = the band
    minutes she told the app it takes her    x the hourly she told the app    = the floor
    a caption she pastes                     read against the FTC's own words = the label check

The published bands are kept as separate rows with their own caveat rather than blended into
one friendly number, because the four sources do not agree with each other and a single figure
would hide that. Every CPM here names the playbook entry it came from, and an entry the library
cannot show - missing, or older than its own stale window - takes its number with it.
"""
from dataclasses import dataclass, field
from datetime import date
from statistics import median
import re

# A median struck from three posts is one good afternoon, not a rate a brand can be quoted on.
MIN_POSTS = 5
# This app's own reading of "hard to miss". No source gives a character count, so the number is
# labelled as ours on the page rather than dressed up as a rule.
FOLD_CHARS = 125
# The sources are published in US dollars and this app does not convert. Quoting in another
# currency is hers to do; inventing an exchange rate here would be the one way to be wrong twice.
UNIT = "$"

# Platforms whose deliverable is moving picture, where the guidance says a caption-only label is
# not enough and the disclosure has to be in the video.
VIDEO_SURFACES = ("tiktok", "reels", "shorts", "youtube", "story", "video")
# The three words the cited guidance actually names.
NAMED_TERMS = ("advertisement", "sponsored", "ad")
# Words in wide use that the cited guidance does not name. Accepted, marked unverified: the app
# has read the guidance, not the enforcement record.
OTHER_TERMS = ("paid partnership", "paid link", "in association with", "commissioned by",
               "gifted from", "pr")
# Signals that something of value changed hands even though no fee is mentioned anywhere.
COMPENSATION_HINTS = ("they sent me", "gifted", "brand sent", "no one paid me", "free product",
                      "they gave me", "in exchange for")


# The values the app's own readers write when a row never named its platform. Treating one of
# those as a platform would blend her tiktok views and her YouTube views into a single median
# and hand her a quote for a place that does not exist.
UNNAMED = ("", "logged", "unknown")


@dataclass(frozen=True)
class Band:
    """One published way of pricing, kept separate from the others on purpose."""
    label: str
    low: float
    high: float
    entry: str
    measured: str

    def per_thousand(self, views: int) -> tuple:
        return (round(views / 1000.0 * self.low, 2), round(views / 1000.0 * self.high, 2))


SHORT_FORM = (
    Band("benchmark median, first-month views", 15.46, 15.46, "money-per-view-basis",
         "a 2026 cross-platform benchmark report's median"),
    Band("executed campaigns by vertical", 4.46, 25.71, "money-per-view-basis",
         "four verticals on 3 to 38 campaigns each; none of them short-form fashion"),
)
YOUTUBE = SHORT_FORM + (
    Band("YouTube, by niche", 15.0, 80.0, "money-per-view-basis",
         "a 2026 YouTube sponsorship rate guide"),
    Band("YouTube, channels over 50K subscribers", 40.0, 53.0, "money-per-view-basis",
         "552 creators' median sponsor CPM - a subscriber floor this app cannot check for her"),
)
# Follower-tier pricing is the other basis in use, and the one a brand opens with. Shown as a
# shape, never as her number: this app has no follower count it trusts.
TIER_BASIS = "money-per-tier-basis"
RIGHTS_BASIS = "money-rights-add-ons"

ADDONS = (
    ("Usage rights - they reuse the asset as their own creative", 0.20, 0.50, "of the base fee",
     "impact.com, quoted as 20 to 50 percent"),
    ("Whitelisting - ads run from your handle", 0.20, 0.30, "of the base fee, per month",
     "two published guides, 20 to 30 percent per month"),
    ("Whitelisting, priced on their media instead", 0.04, 0.04, "of the ad spend",
     "a brand-facing guide offers 4 percent of spend - the shape to ask which they mean"),
    ("Boost fee - they put money behind the post", 0.05, 0.20, "of the ad spend",
     "5 to 20 percent of the spend behind the post"),
    ("Everything on top at once, as quoted", 0.15, 3.00, "on top of the base fee",
     "paid usage, whitelisting and exclusivity together, summed by one rate card"),
)


@dataclass
class Quote:
    """A number she can say out loud, with the arithmetic and the caveat attached."""
    platform: str
    posts: int
    median_views: int
    low: float
    high: float
    anchor: float
    floor: float
    bands: list = field(default_factory=list)
    missing: list = field(default_factory=list)

    @property
    def under_floor(self) -> bool:
        return bool(self.floor) and self.anchor < self.floor

    @property
    def line(self) -> str:
        if self.floor:
            return (f"{UNIT}{self.anchor:,.0f} to quote from, on {self.posts} posts at a median "
                    f"{self.median_views:,} views - and never under {UNIT}{self.floor:,.0f}, "
                    f"which is what this post costs you.")
        return (f"{UNIT}{self.anchor:,.0f} to quote from, on {self.posts} posts at a median "
                f"{self.median_views:,} views.")


def views_band(platform: str) -> tuple:
    return YOUTUBE if platform in ("youtube",) else SHORT_FORM


def priceable(rows) -> dict:
    """Posts and median views per platform, from her own import and nothing else."""
    by: dict[str, list] = {}
    for r in rows:
        platform = (getattr(r, "platform", "") or "").strip().lower()
        views = int(getattr(r, "views", 0) or 0)
        if platform in UNNAMED or views <= 0:
            continue
        by.setdefault(platform, []).append(views)
    return {p: (len(v), int(median(v))) for p, v in by.items()}


def live(entries, today: date | None = None) -> dict:
    """The playbook entries this file depends on, keyed by id - or absent.

    A number whose claim has gone stale or left the library stops being quotable here: the band
    is dropped rather than shown with a dead citation.
    """
    today = today or date.today()
    want = {b.entry for p in (SHORT_FORM, YOUTUBE) for b in p} | {TIER_BASIS, RIGHTS_BASIS}
    out = {}
    for e in entries:
        if e.id in want and not e.is_stale(today):
            out[e.id] = e
    return out


def quotes(rows, entries, hourly=0, minutes=0, today=None) -> tuple:
    """One Quote per platform that has enough of her own posts to price, plus what was refused.

    hourly and minutes are hers. Left blank, there is no floor and the page says so instead of
    adopting a wage.
    """
    alive = live(entries, today)
    floor = round(float(hourly or 0) * float(minutes or 0) / 60.0, 2)
    out, thin, uncited = [], [], []
    for platform, (posts, med) in sorted(priceable(rows).items()):
        bands = [b for b in views_band(platform) if b.entry in alive]
        if not bands:
            uncited.append(platform)
            continue
        if posts < MIN_POSTS:
            thin.append(f"{platform}: {posts} post{'s' if posts != 1 else ''} imported, "
                        f"{MIN_POSTS} needed before a median means anything")
            continue
        lows_highs = [b.per_thousand(med) for b in bands]
        anchor = round(sum((lo + hi) / 2 for lo, hi in lows_highs) / len(lows_highs), 2)
        out.append(Quote(platform, posts, med,
                         low=round(min(lo for lo, _ in lows_highs), 2),
                         high=round(max(hi for _, hi in lows_highs), 2),
                         anchor=anchor, floor=floor,
                         bands=[b for b in bands],
                         missing=[b.measured for b in bands]))
    return tuple(out), tuple(thin), tuple(uncited)


def addon_lines(base: float) -> list:
    """What each permission is worth once a base fee exists - two shapes, so ask which one."""
    if base <= 0:
        return []
    out = []
    for name, low, high, shape, basis in ADDONS:
        if "ad spend" in shape:
            out.append({"name": name, "of_base": None, "shape": shape, "basis": basis,
                        "range": f"{low * 100:.0f} to {high * 100:.0f} percent of their spend"})
        else:
            out.append({"name": name, "of_base": (round(base * low, 2), round(base * high, 2)),
                        "shape": shape, "basis": basis,
                        "range": f"{UNIT}{base * low:,.0f} to {UNIT}{base * high:,.0f}"})
    return out


@dataclass
class Disclosure:
    """The label check. Text in, verdict out - and the part this app cannot see, named."""
    status: str          # clear | unverified | missing
    found: tuple = ()
    not_named: tuple = ()
    first_at: int = -1
    behind_fold: bool = False
    needs_video: bool = False
    in_video: bool = False
    compensated: bool = False
    notes: list = field(default_factory=list)

    @property
    def safe_to_post(self) -> bool:
        return (self.status == "clear" and not self.behind_fold
                and (not self.needs_video or self.in_video))

    @property
    def line(self) -> str:
        if self.status == "missing":
            return ("Nothing in this text says it is an ad. The guidance names advertisement, ad "
                    "and sponsored, and if anything of value changed hands - cash, product, a "
                    "fee, a relationship - this post is advertising and has to say so.")
        if self.status == "unverified":
            return (f"Says {self.not_named[0]!r}, which the guidance this app cites does not "
                    f"name. It may well read clearly; the three words the guidance names are "
                    f"advertisement, ad and sponsored.")
        return f"Carries {self.found[0]!r} at character {self.first_at + 1}."


def _hit(text: str, terms):
    """The longest-listed term present, tried first so "advertisement" wins over "ad" and the
    position reported is the real start of the label."""
    for term in sorted(terms, key=len, reverse=True):
        m = re.search(r"(?i)\b" + re.escape(term) + r"\b", text)
        if m:
            return term, m
    return None, None


SEPARATORS = ("\n", " | ", " - ", ". ", "; ", "! ", "? ")


def _piece(text: str, start: int, end: int) -> str:
    """The run of text the label sits in, between the nearest separators either side."""
    begin = max([text.rfind(sep, 0, start) for sep in SEPARATORS] + [-1]) + 1
    ends = [text.find(sep, end) for sep in SEPARATORS]
    ends = [e for e in ends if e > -1]
    return text[begin:min(ends) if ends else len(text)].strip()


def check_disclosure(text: str, surface: str = "", in_video: bool = False) -> Disclosure:
    """Read one caption the way the guidance would, and report what it cannot see."""
    body = text or ""
    named, match = _hit(body, NAMED_TERMS)
    other, other_match = _hit(body, OTHER_TERMS)
    hint = next((h for h in COMPENSATION_HINTS if h in body.lower()), "")
    d = Disclosure("missing", in_video=bool(in_video),
                   compensated=bool(hint),
                   needs_video=surface.strip().lower() in VIDEO_SURFACES)
    if named:
        at = match.start()
        d.status, d.found, d.first_at = "clear", (named,), at
        # Only "ad" is a word that turns up in ordinary sentences, so only "ad" gets asked
        # whether it is standing as the label or just appearing in her prose.
        if named == "ad" and _piece(body, at, match.end()).lower().lstrip("#").strip(".!,") != "ad":
            d.notes.append('"ad" appears inside a sentence rather than standing as the label. '
                           "The guidance is about a disclosure that is hard to miss, so check it "
                           "reads as one.")
    elif other:
        d.status, d.not_named, d.first_at = "unverified", (other,), other_match.start()
    d.behind_fold = d.first_at >= FOLD_CHARS
    if hint and d.status == "missing":
        d.notes.append(f'"{hint}" is a material connection: product or a favour counts as '
                       f"compensation, so the label is owed even with no fee in the post.")
    if d.behind_fold:
        d.notes.append(f"The label sits at character {d.first_at + 1}, past the "
                       f"{FOLD_CHARS}-character line this app treats as the fold - a number of "
                       f"our own, not a published one. Move it to the front.")
    if d.needs_video and not d.in_video:
        d.notes.append("This is a video placement. The guidance puts the disclosure in the video, "
                       "not only the caption, and repeats it across a live stream - which no text "
                       "check can confirm.")
    if not d.in_video and not d.needs_video:
        d.notes.append("Nothing here can see the crop, so check that the label survives it.")
    return d
