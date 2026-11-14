"""The tags, and the evidence each one is allowed to be shown with.

A trending-hashtag widget is the easiest feature in this category to fake and the fastest way to
lose the plot: no platform publishes a hashtag feed this app can read, and a scraped list would
be somebody else's account doing the ranking, not hers. So a tag appears here only when one of
four things put it there, and the page prints which one:

    your numbers   - the hypothesis your own imported posts ranked first
    your captions  - a tag already inside the writing you pasted
    your words     - made from the words you used to describe this shot
    the format     - the tag the plan's own format carries

The first two are evidence. The last two are guesses with a traceable origin, which is the most
an app on a laptop can honestly offer, and they are labelled as such instead of dressed up as
trends.
"""
import re

from src.captions.tone import phrases
from src.strategist.daily import BANNED_HASHTAGS, FORMATS
from src.experiment import ledger as experiment

# How many tags a placement carries before it reads as spam. This app's own reading of the
# formats, not a published limit - none of these platforms prints the number it uses.
TAG_LIMITS = {"instagram": 6, "tiktok": 5, "youtube": 3, "pinterest": 4, "x": 1,
              "threads": 3, "facebook": 3}
DEFAULT_LIMIT = 4
STEM = re.compile(r"[^a-z0-9_]+")


def limit_for(platform: str) -> int:
    return TAG_LIMITS.get((platform or "").strip().lower(), DEFAULT_LIMIT)


def slug(text: str) -> str:
    """One hashtag out of a phrase: letters, digits and underscores, nothing else, no spaces -
    a tag with a space in it is two tags and a broken link."""
    return ("#" + STEM.sub("", (text or "").lower().replace(" ", "")))[:26]


def usable(tag: str) -> bool:
    body = (tag or "").lstrip("#")
    return len(body) >= 3 and not body.isdigit() and tag.lower() not in BANNED_HASHTAGS


def candidates(platform: str, subject: str = "", profile=None, rows=None, arm: str = "",
               limit: int | None = None) -> list:
    """Every tag this app can put on the page, strongest evidence first, capped at the
    placement's own count."""
    cap = limit if limit is not None else limit_for(platform)
    out: list[dict] = []
    seen: set[str] = set()

    def add(tag, source, evidence):
        tag = (tag or "").strip()
        if not tag.startswith("#"):
            tag = slug(tag)
        if tag.lower() in seen or not usable(tag):
            return
        seen.add(tag.lower())
        out.append({"tag": tag, "source": source, "evidence": evidence})

    got = experiment.ledger(rows or [])
    top = got.arms[0] if got.arms else None
    if top is not None and top.n >= 3:
        add(slug(top.label), "your numbers",
            f"{top.n} of your posts ran under it - {top.rate_text}, {top.watch}% watched")
    if profile is not None:
        for tag in profile.tags:
            add(tag, "your captions", "already in the writing you pasted, so it is your habit")
    for run in reversed(phrases(subject)):
        add(run, "your words", f"made from the words you used for this shot: {run}")
    if arm:
        for tag in FORMATS.get(arm, (None, None, None, []))[3] or []:
            add(tag, "the format", f"the tag this week's format ({arm}) carries")
    return out[:cap]


def block(platform: str, picked: list) -> str:
    """The tag line as it goes in the caption - one space between each, nothing invented."""
    return " ".join(p["tag"] for p in picked[:limit_for(platform)])


def missing(rows, profile, subject) -> list:
    """What had to be absent for the list to be this short. Said out loud, because a short tag
    list looks like a small opinion rather than a missing input."""
    out = []
    got = experiment.ledger(rows or [])
    if not got.arms:
        out.append("No hypothesis is attached to your imported posts, so nothing here can be "
                   "ranked by what actually worked for you. The Lab files them.")
    elif got.arms[0].n < 3:
        out.append(f"Your best arm has {got.arms[0].n} post{'s' if got.arms[0].n != 1 else ''} on "
                   "it, which is not a signal, so it is not on the list.")
    if profile is None or not profile.tags:
        out.append("Nothing you have written is pasted, so there is no tag of yours to reuse.")
    if not (subject or "").strip():
        out.append("No description of the shot, so no tag can be made from your own words.")
    return out
