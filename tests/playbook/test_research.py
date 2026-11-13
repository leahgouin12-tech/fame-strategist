from datetime import date, timedelta

from src.playbook.research import DEAD_DAYS, FRESH_DAYS, brief, run
from src.playbook.schema import Confidence, PlaybookEntry, Source, SourceTier
from src.playbook.store import Store

ROOT = None

BASE = dict(
    id="trend-some-format",
    claim="A format somebody published, stated as one filmable sentence.",
    mechanism="Because the mechanism is a separate claim from the finding.",
    confidence=Confidence.CONTESTED,
    sources=[Source("https://example.org/report", "The report", SourceTier.STUDY)],
    applies_to=["tiktok"],
    as_of=date(2026, 11, 10),
    does_not_claim="That the report measured accounts like hers.",
    tags=["trend", "format"],
)

TODAY = date(2026, 11, 13)


def make(**over):
    return PlaybookEntry(**{**BASE, **over})


def test_a_dated_trend_entry_is_a_live_finding():
    result = run([make()], TODAY)
    assert result.ran and result.count == 1
    assert result.findings[0].days_old == 3
    assert result.findings[0].age_words == "3 days old"


def test_a_library_claim_without_the_tag_is_not_research():
    result = run([make(tags=["format"])], TODAY)
    assert not result.ran
    assert result.findings == []
    assert "No trend research is live" in result.note


def test_a_finding_outlives_its_window_and_settles_into_the_library():
    old = make(as_of=TODAY - timedelta(days=FRESH_DAYS + 20))
    result = run([old], TODAY)
    assert not result.ran
    assert result.findings == []
    assert result.settled[0].days_old == FRESH_DAYS + 20


def test_the_window_boundary_is_the_day_the_finding_stops_being_one():
    inside = make(as_of=TODAY - timedelta(days=FRESH_DAYS))
    outside = make(id="trend-just-late", as_of=TODAY - timedelta(days=FRESH_DAYS + 1))
    result = run([inside, outside], TODAY)
    assert [f.id for f in result.findings] == ["trend-some-format"]
    assert [f.id for f in result.settled] == ["trend-just-late"]


def test_findings_are_ordered_newest_first():
    newer = make(as_of=TODAY)
    older = make(id="trend-older", as_of=date(2026, 10, 20))
    result = run([older, newer], TODAY)
    assert [f.id for f in result.findings] == ["trend-some-format", "trend-older"]
    assert result.newest_days == 0


def test_a_finding_already_in_todays_slot_is_marked():
    result = run([make()], TODAY, focus_ids={"trend-some-format", "metr-3-second-hook-rule"})
    assert result.findings[0].in_this_week is True


def test_age_words_read_like_a_person_saying_them():
    from src.playbook.research import age_words
    assert age_words(0) == "dated today"
    assert age_words(1) == "one day old"
    assert age_words(13) == "13 days old"
    assert age_words(14) == "2 weeks old"
    assert age_words(60) == "8 weeks old"
    assert age_words(DEAD_DAYS) == "6 months old"


def test_the_brief_asks_for_the_shape_this_page_can_read():
    text = brief(platforms=["tiktok", "reels"], hypotheses=["outfit-and-style"],
                 chosen="lifestyle-day-in-life", hours_per_week=5, today=TODAY)
    assert "outfit-and-style" in text
    assert "lifestyle-day-in-life" in text
    assert "as-of date" in text
    assert "trend-" in text
    assert "Do not give me a hashtag list." in text


def test_the_brief_carries_no_address_because_the_app_fetches_nothing():
    text = brief(platforms=[], hypotheses=[], chosen="", hours_per_week=0, today=TODAY)
    assert "http" not in text
    assert "not chosen yet" in text


def test_the_playbook_ships_with_dated_research_behind_it():
    entries = Store().load(_playbook_dir())
    trended = [e for e in entries if "trend" in e.tags]
    assert len(trended) >= 3, "spec 5.10 is meant to ship with research, not with a promise"
    for entry in trended:
        assert entry.sources, f"{entry.id} has no citation"
        assert not entry.has_placeholder_source(), f"{entry.id} is still unverified"
        assert entry.does_not_claim.strip(), f"{entry.id} states no limit"


def _playbook_dir():
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / "data" / "playbook"
