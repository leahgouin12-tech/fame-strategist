"""What one piece of advice has to carry before it counts as a playbook entry.

A PlaybookEntry is a claim, the mechanism behind it, an as-of date, the platforms and
formats it applies to, and - required, not optional - a does_not_claim line stating its
own limit. Confidence runs proven, strong, contested, folklore; SourceTier runs
platform_official, study, practitioner, secondhand; and validate_entry returns the list
of reasons an entry is not yet trustworthy, an empty list meaning it is.

The rules that cost something are the ones worth knowing: proven needs two sources with a
platform-official or a study among them, folklore has to explain in does_not_claim why it
is kept at all, an entry older than STALE_AFTER_MONTHS (18) is stale and must be
re-researched or re-dated, and a source still pointing at example.com is flagged by
PENDING_MARKER. Nothing in this file reads or writes a document; it only judges one.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

STALE_AFTER_MONTHS = 18


class Confidence(str, Enum):
    PROVEN = "proven"
    STRONG = "strong"
    CONTESTED = "contested"
    FOLKLORE = "folklore"


class SourceTier(str, Enum):
    PLATFORM_OFFICIAL = "platform_official"
    STUDY = "study"
    PRACTITIONER = "practitioner"
    SECONDHAND = "secondhand"


@dataclass
class Source:
    url: str
    title: str
    tier: SourceTier


@dataclass
class PlaybookEntry:
    id: str
    claim: str
    mechanism: str
    confidence: Confidence
    sources: list[Source]
    applies_to: list[str]
    as_of: date
    does_not_claim: str
    tags: list[str] = field(default_factory=list)

    def months_old(self, today: date) -> int:
        return (today.year - self.as_of.year) * 12 + (today.month - self.as_of.month)

    def is_stale(self, today: date) -> bool:
        return self.months_old(today) > STALE_AFTER_MONTHS

    def has_placeholder_source(self) -> bool:
        return any(PENDING_MARKER in s.url for s in self.sources)


PENDING_MARKER = "example.com"


def validate_entry(entry: PlaybookEntry, today: date | None = None) -> list[str]:
    """Return every reason this claim is not yet trustworthy. Empty means it is.

    Un-sourced advice must never enter the playbook: it is the only thing standing
    between this app and generic motivational output.
    """
    today = today or date.today()
    problems: list[str] = []

    if not entry.id or not entry.id.replace("-", "").isalnum():
        problems.append(f"id {entry.id!r} must be non-empty kebab-case")
    if len(entry.claim) < 20:
        problems.append("claim must be a real sentence, at least 20 characters")
    if not entry.mechanism.strip():
        problems.append("mechanism is required: why this is believed to work")
    if not entry.applies_to:
        problems.append("applies_to must name at least one platform or format")
    if entry.months_old(today) < -1:
        problems.append(f"as_of {entry.as_of} is in the future")
    if entry.is_stale(today):
        problems.append(f"as_of {entry.as_of} is stale; re-research or re-date this entry")

    if not entry.sources:
        problems.append("sources must not be empty; unsourced advice does not enter the playbook")
    for s in entry.sources:
        if not s.url.startswith(("http://", "https://")):
            problems.append(f"source url {s.url!r} must be an http(s) address")
        if not s.title.strip():
            problems.append("every source needs a title so the claim can be re-checked")

    strong = {SourceTier.PLATFORM_OFFICIAL, SourceTier.STUDY}
    if entry.confidence is Confidence.PROVEN and (
        len(entry.sources) < 2 or not any(s.tier in strong for s in entry.sources)
    ):
        problems.append("proven requires 2+ sources including a platform-official or study")
    if entry.confidence is Confidence.FOLKLORE and "folklore" not in entry.does_not_claim.lower():
        problems.append("does_not_claim must explain why folklore is kept")
    if not entry.does_not_claim.strip():
        problems.append("does_not_claim is required; every entry states its own limit")

    return problems
