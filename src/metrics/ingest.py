import csv
import re
from dataclasses import dataclass
from datetime import date

REQUIRED = ["post_ref", "views", "avg_watch_pct", "follows_gained"]
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# A clock time, told apart from a date's own digits by the colon it must not sit inside.
_CLOCK = re.compile(r"(?<![\d:])([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
_HOUR = re.compile(r"^\s*([01]?\d|2[0-3])\s*(?::[0-5]\d)?\s*$")


def when(text) -> tuple[date, int | None]:
    """A date, and the hour if the row carried one.

    The hour is what spec 5.7 is built on, so an export that names a time has to keep it and a
    paste that does not must not invent one.
    """
    raw = str(text or "").strip()
    if not raw:
        return date.today(), None
    clock = _CLOCK.search(raw)
    head = raw.replace("T", " ").split(" ")[0]
    try:
        day = date.fromisoformat(head)
    except ValueError:
        raise ValueError(f"{text!r} is not a date")
    if clock:
        return day, int(clock.group(1))
    if day.isoformat() != raw:
        tail = raw[len(day.isoformat()):].strip()
        hour = _HOUR.match(tail)
        if hour:
            return day, int(hour.group(1))
    return day, None


@dataclass
class MetricRow:
    platform: str
    post_ref: str
    published_at: date
    reach: int
    views: int
    avg_watch_pct: float
    follows_gained: int
    comments: int
    saves: int
    hypothesis: str = ""
    posted_hour: int | None = None

    @property
    def follow_rate_per_1000(self) -> float:
        return round(self.follows_gained / max(self.views, 1) * 1000, 2)


def read_csv(path) -> list[MetricRow]:
    """A file the user drops in, not an API. Headers are matched loosely so a platform
    export with different casing still loads; a genuinely absent column is named."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        raw_rows = list(csv.DictReader(fh))
    if not raw_rows:
        raise ValueError(f"{path}: no rows")
    keys = {k.strip().lower() for k in raw_rows[0] if k}
    missing = [c for c in REQUIRED if c not in keys]
    if missing:
        raise ValueError(f"{path}: missing required column(s): {', '.join(missing)}")

    rows = []
    for raw in raw_rows:
        clean = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        day, hour = when(clean.get("published_at"))
        stated = clean.get("posted_at") or clean.get("hour") or clean.get("posting_time")
        if stated:
            clock = _CLOCK.search(stated)
            match = _HOUR.match(stated)
            hour = int(clock.group(1)) if clock else (int(match.group(1)) if match else hour)
        rows.append(
            MetricRow(
                platform=clean.get("platform", "unknown"),
                post_ref=clean["post_ref"],
                published_at=day,
                reach=_num(clean, "reach"),
                views=_num(clean, "views"),
                avg_watch_pct=float(clean["avg_watch_pct"] or 0),
                follows_gained=_num(clean, "follows_gained"),
                comments=_num(clean, "comments"),
                saves=_num(clean, "saves"),
                hypothesis=clean.get("hypothesis", ""),
                posted_hour=hour,
            )
        )
    return rows


def _num(clean, key) -> int:
    value = clean.get(key, "")
    return int(float(value)) if value not in ("", "-") else 0


def read_quick(text: str) -> list[MetricRow]:
    """Three numbers per line, typed off the app's own insights screen: views, watch %,
    follows. No export, no headers. A line that does not carry three numbers is named."""
    rows, bad = [], []
    for i, line in enumerate(text.strip().splitlines(), 1):
        if not line.strip():
            continue
        parts = line.replace(",", "").split()
        # A leading number is not a reference, it is the view count: only a non-numeric first
        # token is a name she typed. And a reference like clip-0042 must not donate its digits.
        named = not re.fullmatch(r"\d+(?:\.\d+)?", parts[0])
        head = parts[0] if named else f"post {i}"
        numbers, hour = [], None
        for token in (parts[1:] if named else parts):
            clock = _CLOCK.fullmatch(token)
            if clock:
                hour = int(clock.group(1))
                continue
            found = _NUMBER.search(token)
            if found:
                numbers.append(float(found.group()))
        if len(numbers) < 3:
            bad.append(f"line {i} needs views, watch %, follows")
            continue
        rows.append(
            MetricRow(
                platform="logged",
                post_ref=head,
                published_at=date.today(),
                reach=0,
                views=int(numbers[0]),
                avg_watch_pct=numbers[1],
                follows_gained=int(numbers[2]),
                comments=0,
                saves=0,
                posted_hour=hour,
            )
        )
    if not rows or bad:
        raise ValueError("Could not read: " + "; ".join(bad or ["no lines"]))
    return rows
