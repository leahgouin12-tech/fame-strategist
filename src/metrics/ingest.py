import csv
import re
from dataclasses import dataclass
from datetime import date

REQUIRED = ["post_ref", "views", "avg_watch_pct", "follows_gained"]
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


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
        rows.append(
            MetricRow(
                platform=clean.get("platform", "unknown"),
                post_ref=clean["post_ref"],
                published_at=date.fromisoformat(clean["published_at"])
                if clean.get("published_at")
                else date.today(),
                reach=_num(clean, "reach"),
                views=_num(clean, "views"),
                avg_watch_pct=float(clean["avg_watch_pct"] or 0),
                follows_gained=_num(clean, "follows_gained"),
                comments=_num(clean, "comments"),
                saves=_num(clean, "saves"),
                hypothesis=clean.get("hypothesis", ""),
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
        nums = [float(n) for n in _NUMBER.findall(line.replace(",", ""))]
        if len(nums) < 3:
            bad.append(f"line {i} needs views, watch %, follows")
            continue
        head = line.replace(",", "").strip().split()[0]
        rows.append(
            MetricRow(
                platform="logged",
                post_ref=head if not _NUMBER.fullmatch(head) else f"post {i}",
                published_at=date.today(),
                reach=0,
                views=int(nums[0]),
                avg_watch_pct=nums[1],
                follows_gained=int(nums[2]),
                comments=0,
                saves=0,
            )
        )
    if not rows or bad:
        raise ValueError("Could not read: " + "; ".join(bad or ["no lines"]))
    return rows
