from datetime import date

from src.engines.offline import OfflineEngine
from src.strategist.daily import BANNED_HASHTAGS, build_day
from src.strategist.niche import rank, score_candidates
from src.strategist.plan import compose_plan
from tests.strategist.test_niche import ANSWERS, ENTRIES

PLAN = compose_plan(
    ENTRIES, ANSWERS, rank(score_candidates(ENTRIES, ANSWERS)), OfflineEngine(), date(2026, 11, 9)
)
D = date(2026, 11, 20)


def day(d=D):
    return build_day(PLAN, ENTRIES, ANSWERS, d, OfflineEngine())


def test_a_day_is_doable_in_fifteen_minutes_of_filming():
    d = day()
    assert len(d.shots) <= 6
    assert sum(s.seconds for s in d.shots) <= 90


def test_hook_is_written_as_spoken_words_not_advice():
    d = day()
    assert d.hook and len(d.hook) <= 90
    assert "make it pop" not in d.hook.lower()


def test_caption_is_a_real_sentence_even_with_no_key():
    d = day()
    assert len(d.caption) > 20
    assert "[" not in d.caption


def test_no_key_means_real_copy_not_a_blank_to_fill_in():
    d = day()
    assert d.copy_origin == "local"
    assert "[" not in d.hook and "say this]" not in d.hook
    assert "copy written by: local" in d.cost_note


def test_local_copy_uses_their_own_footage_words_not_invented_ones():
    hooks = {day(date(2026, 11, n)).hook for n in range(9, 30)}
    assert len(hooks) > 1, "the same line every day is not a strategy"
    assert all("outfits" in h.lower() for h in hooks), hooks
    assert not any("viral" in h.lower() or "guarantee" in h.lower() for h in hooks)


def test_hashtags_are_three_to_five_and_niche_not_generic():
    d = day()
    assert 3 <= len(d.hashtags) <= 5
    assert not set(t.lower() for t in d.hashtags) & BANNED_HASHTAGS


def test_every_day_states_its_sourced_basis():
    assert day().sourced_from, "an unsourced day is a guess"


def test_cost_note_reports_engine_used():
    assert "offline" in day().cost_note.lower()


def test_checklist_is_what_the_user_acts_on():
    items = day().as_checklist()
    assert items[0].startswith("Hook:")
    assert len(items) >= 4


def test_seven_days_cover_at_least_two_hypotheses_in_experiment_phase():
    names = {day(date(2026, 11, d)).hypothesis for d in range(15, 22)}
    assert len(names) >= 2


def test_after_week_four_stops_rotating_hypotheses():
    late = {day(date(2026, 12, d)).hypothesis for d in range(14, 21)}
    assert len(late) == 1


def test_the_day_names_the_shots_it_needs_from_the_footage_they_have():
    d = day()
    assert all(s.framing and s.seconds > 0 for s in d.shots)
    assert d.beats, "a shot list with no narrative beats is a to-do list"


def test_a_week_seven_day_is_not_beyond_the_plan():
    assert day(date(2027, 5, 1)).week_no == 8


def test_the_placeholder_never_becomes_the_thing_she_is_told_to_say():
    from src.strategist.interview import FALLBACK_FOOTAGE, Interview

    d = build_day(PLAN, ENTRIES, Interview.defaults(""), D, OfflineEngine())
    assert FALLBACK_FOOTAGE not in d.hook.lower()
    assert FALLBACK_FOOTAGE not in d.caption.lower()
    assert "real life" in (d.hook + d.caption).lower()
