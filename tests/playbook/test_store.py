from datetime import date
from pathlib import Path

import pytest

from src.playbook.schema import (
    Confidence,
    PlaybookEntry,
    Source,
    SourceTier,
    validate_entry,
)
from src.playbook.store import PlaybookError, Store

GOOD = dict(
    id="hook-first-second",
    claim="Distribution is decided mainly in the first 1-2 seconds.",
    mechanism="Platforms sample early retention and gate further reach on it.",
    confidence=Confidence.STRONG,
    sources=[
        Source("https://example.com/a", "TikTok on signals", SourceTier.PLATFORM_OFFICIAL)
    ],
    applies_to=["tiktok", "reels", "shorts"],
    as_of=date(2026, 10, 1),
    does_not_claim="That a strong hook guarantees reach.",
)


def make(**over):
    return PlaybookEntry(**{**GOOD, **over})


def today():
    return date(2026, 11, 12)


def test_valid_entry_has_no_problems():
    assert validate_entry(make(), today()) == []


def test_folklore_needs_a_reason_it_is_kept():
    problems = validate_entry(make(confidence=Confidence.FOLKLORE), today())
    assert "does_not_claim must explain why folklore is kept" in " ".join(problems)


def test_proven_needs_two_sources_including_one_strong():
    entry = make(confidence=Confidence.PROVEN)
    assert any("proven" in p for p in validate_entry(entry, today()))


def test_proven_accepts_two_sources_with_an_official_one():
    entry = make(
        confidence=Confidence.PROVEN,
        sources=[
            Source("https://example.com/a", "platform page", SourceTier.PLATFORM_OFFICIAL),
            Source("https://example.com/b", "a study", SourceTier.STUDY),
        ],
    )
    assert validate_entry(entry, today()) == []


def test_stale_entry_is_reported():
    entry = make(as_of=date(2020, 1, 1))
    assert any("stale" in p for p in validate_entry(entry, today()))


def test_future_dated_entry_is_reported():
    entry = make(as_of=date(2030, 1, 1))
    assert any("future" in p for p in validate_entry(entry, today()))


def test_source_url_must_be_http():
    entry = make(sources=[Source("example.com", "t", SourceTier.STUDY)])
    assert any("url" in p for p in validate_entry(entry, today()))


def test_claim_without_a_source_is_rejected():
    entry = make(sources=[])
    assert any("unsourced" in p for p in validate_entry(entry, today()))


SEED = """---
id: hook-first-second
confidence: strong
as_of: 2026-10-01
applies_to: tiktok, reels
tags: hook, retention
does_not_claim: That a strong hook guarantees reach.
sources:
  - https://example.com/a | TikTok on signals | platform_official
---
claim: Distribution is decided mainly in the first 1-2 seconds.
mechanism: Platforms sample early retention and gate further reach on it.
"""


def test_load_reads_a_playbook_file(tmp_path):
    (tmp_path / "hook-first-second.md").write_text(SEED, encoding="utf-8")
    entries = Store(today()).load(tmp_path, allow_pending=True)
    assert entries[0].id == "hook-first-second"
    assert entries[0].confidence is Confidence.STRONG
    assert entries[0].applies_to == ["tiktok", "reels"]
    assert entries[0].tags == ["hook", "retention"]
    assert entries[0].sources[0].tier is SourceTier.PLATFORM_OFFICIAL


def test_load_rejects_a_sourceless_entry(tmp_path):
    (tmp_path / "bad.md").write_text(
        "---\nid: bad\nconfidence: strong\nas_of: 2026-10-01\n"
        "applies_to: tiktok\nsources:\n---\n"
        "claim: Claims here need a number of characters to pass.\n"
        "mechanism: y\ndoes_not_claim: z\n",
        encoding="utf-8",
    )
    with pytest.raises(PlaybookError) as exc:
        Store(today()).load(tmp_path)
    assert "bad" in str(exc.value)


def test_load_names_every_problem_in_one_pass(tmp_path):
    (tmp_path / "a.md").write_text(SEED, encoding="utf-8")
    (tmp_path / "b.md").write_text(
        SEED.replace("id: hook-first-second", "id: second-entry").replace(
            "confidence: strong", "confidence: folklore"
        ),
        encoding="utf-8",
    )
    with pytest.raises(PlaybookError) as exc:
        Store(today()).load(tmp_path, allow_pending=True)
    assert "second-entry" in str(exc.value)


def test_placeholders_are_refused_unless_explicitly_allowed(tmp_path):
    (tmp_path / "hook-first-second.md").write_text(SEED, encoding="utf-8")
    with pytest.raises(PlaybookError) as exc:
        Store(today()).load(tmp_path)
    assert "placeholder" in str(exc.value)


def test_seed_playbook_loads():
    entries = Store().load(Path("data/playbook"), allow_pending=True)
    assert len(entries) >= 2
    assert all(e.tags for e in entries), "every seed entry needs tags; scoring reads them"
