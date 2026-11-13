"""Follower-graph insight - the diagnosis, never the button.

Both platforms hand the account owner her own follower and following lists through the
official download-your-data export. Read two of those, weeks apart, and the difference is
real churn: who left, between which dates, and what the posting ledger says she was doing
in that window. What no export contains is the reason - the platform never tells you which
post somebody left over - so this module pairs churn with the calendar and stops there.

Nothing here follows, adds, removes, messages or sorts people into actions. The lists are
other human beings' handles, so they live in one table she can wipe with one click.
"""

from dataclasses import dataclass, field
from datetime import date
import json
import re

NAME_KEYS = ("username", "user_name", "handle", "name", "value", "follower", "account")
TIME_KEYS = ("addTimestamp", "addtimestamp", "added", "timestamp", "time")

STANCE = ("Insight, no action: this page names people who left and places the window against "
          "your own posting days. It does not suggest who to follow, who to let go, who to "
          "message or who to avoid, and no button on it touches an account.")

MIN_NAMES = 1


@dataclass
class Snapshot:
    taken: str = ""
    source: str = "pasted"
    names: tuple[str, ...] = ()
    added: dict[str, str] = field(default_factory=dict)
    error: str = ""


def _clean(raw) -> str:
    return str(raw or "").strip().lstrip("@").strip().lower()


HANDLE = re.compile(r"^[a-z0-9][a-z0-9._]{1,28}$")


def _looks_like_a_handle(text: str) -> bool:
    """A pasted line has to earn its place: column headers and stray prose are dropped
    rather than counted as people."""
    return bool(HANDLE.match(_clean(text)))


def _item_name(item) -> str:
    if isinstance(item, str):
        return _clean(item)
    if isinstance(item, dict):
        for key in NAME_KEYS:
            if key in item and _clean(item[key]) and not str(item[key]).isdigit():
                return _clean(item[key])
        for key in NAME_KEYS:
            if key in item and _clean(item[key]):
                return _clean(item[key])
    return ""


def _item_time(item) -> str:
    if not isinstance(item, dict):
        return ""
    for key in TIME_KEYS:
        if key in item:
            try:
                value = float(item[key])
            except (TypeError, ValueError):
                continue
            if value > 1e11:  # real exports mix seconds and milliseconds
                value /= 1000.0
            try:
                return date.fromtimestamp(value).isoformat()
            except (OverflowError, OSError, ValueError):
                continue
    return ""


def _lists_out_of(node, depth: int = 0):
    """An export is a list, or a dict with one list somewhere inside it. TikTok nests its
    list under a label; Instagram is a bare list of objects."""
    if isinstance(node, list):
        return [node]
    if isinstance(node, dict) and depth < 3:
        found = []
        for value in node.values():
            found += _lists_out_of(value, depth + 1)
        return found
    return []


def parse_export(text: str, taken: str = "", source: str = "pasted") -> Snapshot:
    raw = (text or "").strip()
    if not raw:
        return Snapshot(taken, source, error="Nothing was pasted or uploaded.")
    items = []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        data = None
    if data is None:
        items = [line for line in raw.splitlines() if _clean(line)]
    else:
        for candidate in _lists_out_of(data):
            items += candidate
    names: list[str] = []
    added: dict[str, str] = {}
    for item in items:
        if isinstance(item, str):
            if not _looks_like_a_handle(item):
                continue
            name = _clean(item)
        else:
            name = _item_name(item)
        if not name or name in names:
            continue
        names.append(name)
        when = _item_time(item)
        if when:
            added[name] = when
    if len(names) < MIN_NAMES:
        return Snapshot(taken, source, error=f"0 names read from {source} - a shape this app "
                                             "does not recognise, not an empty account.")
    return Snapshot(taken, source, tuple(names), added)


def _diff(a: Snapshot, b: Snapshot) -> dict:
    before, after = set(a.names), set(b.names)
    return {"from": a.taken, "to": b.taken,
            "lost": [n for n in a.names if n not in after],
            "gained": [n for n in b.names if n not in before],
            "kept": len(before & after)}


def _window(start: str, end: str, lost: int, days) -> dict:
    inside = [d for d in days if start <= d["date"] <= end]
    posted = [d["date"] for d in inside if d.get("done")]
    missed = [d["date"] for d in inside if not d.get("done")]
    labels = []
    for d in inside:
        label = d.get("hypothesis") or "an unlabelled slot"
        labels.append(f"{label} was marked posted" if d.get("done")
                      else f"{label} was not")
    note = (f"{lost} {'account' if lost == 1 else 'accounts'} left between {start} and {end}. "
            f"In that window {len(posted)} of {len(inside)} slots were posted"
            + (f" - {'; '.join(labels)}." if labels else "."))
    if inside:
        note += (" The export never says which post anybody left over, so this is a pairing, "
                 "not a cause. Take it as a question to answer with your own reading.")
    else:
        note += " Nothing was on the ledger in that window, so there is nothing to pair it with."
    return {"start": start, "end": end, "posted": posted, "missed": missed, "note": note}


def churn_report(snaps, days=None) -> dict:
    """Consecutive snapshots only: diffing the first against the last would hide everything
    that happened in the middle, which is exactly where her own answer lives."""
    days = days or []
    usable = [s for s in snaps if not s.error]
    broken = [s for s in snaps if s.error]
    diffs = []
    for a, b in zip(usable, usable[1:]):
        d = _diff(a, b)
        d["window"] = _window(a.taken, b.taken, len(d["lost"]), days)
        diffs.append(d)
    if not usable:
        note = (broken[0].error if broken else
                "No export read yet. On Instagram: Settings and privacy › Download your "
                "information › Followers (and Following). On TikTok: Settings › Account › "
                "Download your data, then the followers/following JSON. Open the file, then "
                "upload it or paste the names - this app never asks for your password.")
    elif len(usable) < 2:
        note = (f"{len(usable)} export read ({usable[0].source}, {len(usable[0].names)} names). "
                "One snapshot is a list, not a trend: request a second export in a week "
                "or two and the diff appears here by itself.")
    else:
        note = f"{len(usable)} snapshots, {len(diffs)} diffs between them."
    if broken and usable:
        note = f"{'; '.join(s.error for s in broken)} - skipped, not counted. " + note
    return {"snapshots": [{"taken": s.taken, "source": s.source, "names": len(s.names),
                           "added": len(s.added)} for s in usable],
            "diffs": diffs, "note": note, "stance": STANCE}
