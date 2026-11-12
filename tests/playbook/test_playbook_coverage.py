from pathlib import Path

from src.playbook.schema import Confidence
from src.playbook.store import Store

REQUIRED_TAGS = {
    "hook",
    "retention",
    "format",
    "niche",
    "cadence",
    "profile",
    "series",
    "engagement",
    "algorithm",
    "conversion",
    "failure-modes",
}
MIN_PER_TAG = 2


def entries():
    return Store().load(Path("data/playbook"))


def test_playbook_has_enough_entries():
    found = len(entries())
    assert found >= 28, f"only {found} entries; the playbook is too thin to advise"


def test_every_required_topic_is_covered_twice():
    seen: dict[str, int] = {}
    for e in entries():
        for t in e.tags:
            seen[t] = seen.get(t, 0) + 1
    missing = {t for t in REQUIRED_TAGS if seen.get(t, 0) < MIN_PER_TAG}
    assert not missing, f"topics with fewer than {MIN_PER_TAG} entries: {sorted(missing)}"


def test_some_entries_are_contested_or_folklore():
    honest = [e for e in entries() if e.confidence in (Confidence.CONTESTED, Confidence.FOLKLORE)]
    assert len(honest) >= 4, "a playbook with no contested claims is overclaiming, not knowledgeable"


def test_no_entry_is_left_on_a_placeholder_url():
    pending = [e.id for e in entries() if e.has_placeholder_source()]
    assert not pending, f"still unverified: {pending}"


def test_every_claim_names_what_it_does_not_prove():
    assert all(e.does_not_claim.strip() for e in entries())
