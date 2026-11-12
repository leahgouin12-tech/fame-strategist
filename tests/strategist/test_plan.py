import pytest

from src.engines.offline import OfflineEngine
from src.strategist.niche import rank, score_candidates
from src.strategist.plan import compose_plan
from tests.strategist.test_niche import ANSWERS, ENTRIES


def plan(**over):
    return compose_plan(
        ENTRIES,
        **{
            **{
                "answers": ANSWERS,
                "hypotheses": rank(score_candidates(ENTRIES, ANSWERS)),
                "engine": OfflineEngine(),
            },
            **over,
        },
    )


def test_eight_weeks_are_produced():
    assert len(plan().weeks) == 8


def test_first_four_weeks_are_the_niche_experiment():
    assert all("experiment" in w.goal.lower() for w in plan().weeks[:4])


def test_every_week_cites_playbook_entries():
    for w in plan().weeks:
        assert w.focus_entry_ids, f"week {w.week_no} has no sourced basis"


def test_week_has_a_falsifiable_success_test():
    for w in plan().weeks:
        assert w.success_test and "%" in w.success_test


def test_experiment_and_concentration_weeks_do_not_share_a_success_test():
    p = plan()
    assert p.weeks[0].success_test != p.weeks[7].success_test


def test_target_posts_respects_hours_per_week():
    assert all(w.target_posts <= max(3, ANSWERS.hours_per_week) for w in plan().weeks)


def test_post_experiment_weeks_switch_to_concentration():
    p = plan()
    assert "concentrate" in p.weeks[6].goal.lower()
    assert p.weeks[4].experiment != p.weeks[0].experiment


def test_the_plan_says_why_it_only_commits_to_experiments_first():
    reason = plan().first_two_weeks_only_reason
    assert reason and "no data" in reason.lower()


def test_plan_survives_json_round_trip():
    p = plan()
    assert p.from_dict(p.to_dict()).weeks[0].goal == p.weeks[0].goal


def test_refuses_to_plan_below_minimum_hours():
    with pytest.raises(ValueError):
        compose_plan(
            ENTRIES,
            ANSWERS.__class__(**{**vars(ANSWERS), "hours_per_week": 1}),
            rank(score_candidates(ENTRIES, ANSWERS)),
            OfflineEngine(),
        )


def test_chosen_hypothesis_is_the_top_ranked_one():
    p = plan()
    assert p.chosen == p.hypotheses[0]
