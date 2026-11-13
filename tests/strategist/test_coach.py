from datetime import date, timedelta

from src.engines.offline import OfflineEngine
from src.metrics.ingest import MetricRow
from src.strategist.coach import CADENCE_DAYS, GENERIC_UNDER, build_agenda
from src.strategist.niche import rank, score_candidates
from src.strategist.plan import compose_plan
from tests.strategist.test_niche import ANSWERS, ENTRIES

TODAY = date(2026, 11, 13)
PLAN = compose_plan(ENTRIES, ANSWERS, rank(score_candidates(ENTRIES, ANSWERS)),
                    OfflineEngine(), TODAY - timedelta(days=20))


def row(ref, watch, follows, views=1000, hypothesis=None):
    return MetricRow("tiktok", ref, TODAY - timedelta(days=3), views, views, watch, follows,
                     4, 1, hypothesis=hypothesis or PLAN.chosen)


def agenda(rows=(), days=(), landed=(), weak=(), offline=True, spend=None):
    return build_agenda(plan=PLAN, days=list(days), rows=list(rows), landed=list(landed),
                        weak=list(weak), entries=ENTRIES, today=TODAY,
                        engine_name="offline" if offline else "gemini", offline=offline,
                        spend=spend)


def test_the_window_is_a_fortnight_not_a_week():
    a = agenda()
    assert a.cadence_days == CADENCE_DAYS == 14
    assert a.start == (TODAY - timedelta(days=13)).isoformat()
    assert a.end == TODAY.isoformat()


def test_the_planned_count_comes_from_the_plan_prorated_to_the_window():
    assert agenda().coverage.planned > 0, "the plan's own target has to reach the coach"


def test_days_she_marked_posted_are_counted_and_the_others_are_named():
    days = [{"date": TODAY.isoformat(), "done": True},
            {"date": (TODAY - timedelta(days=4)).isoformat(), "done": False},
            {"date": "2020-01-01", "done": False}]
    c = agenda(days=days).coverage
    assert c.posted == 1
    assert c.missed == [(TODAY - timedelta(days=4)).isoformat()], "outside days are not this window"


def test_no_landed_files_is_stated_as_no_data_instead_of_a_zero_rate():
    c = agenda().coverage
    assert "no rejection rate" in c.note and "%" not in c.note


def test_two_frames_refuse_to_be_turned_into_a_percentage():
    c = agenda(landed=["a.png", "b.png"], weak=["a.png"]).coverage
    assert "not a rate" in c.note


def test_a_high_strike_of_weak_frames_names_both_explanations_without_choosing():
    c = agenda(landed=[f"f{i}.png" for i in range(5)], weak=[f"f{i}.png" for i in range(4)]).coverage
    assert "80%" in c.note and "only you can say which" in c.note


def test_a_sane_strike_rate_is_called_sane():
    c = agenda(landed=[f"f{i}.png" for i in range(5)], weak=["f0.png"]).coverage
    assert "sane strike rate" in c.note


def test_no_metrics_imported_is_not_invented_into_a_top_post():
    p = agenda().performance
    assert p.posts == 0 and p.top == {} and "never seen" in p.note


def test_the_top_bottom_line_states_the_specific_difference():
    rows = [row("post-a", 40.0, 20), row("post-b", 12.0, 2)]
    p = agenda(rows=rows).performance
    assert p.top["post_ref"] == "post-a" and p.bottom["post_ref"] == "post-b"
    assert "18.0 follows per 1000 views" in p.gap and "28.0 points of watch time" in p.gap


def test_below_twenty_five_posts_the_coach_calls_itself_generic():
    p = agenda(rows=[row(f"p{i}", 20.0, 5) for i in range(GENERIC_UNDER - 1)]).performance
    assert p.generic and "generic" in p.note


def test_the_coach_refuses_to_audit_its_ranking_on_noise():
    sc = agenda(rows=[row("p1", 20.0, 5)]).self_check
    assert sc.agreed is None and "cannot audit" in sc.note


def test_the_coach_audits_its_ranking_and_reports_which_way_it_went():
    other = [h for h in PLAN.hypotheses if h != PLAN.chosen][0]
    won = agenda(rows=[row(f"p{i}", 25.0, 30, hypothesis=PLAN.chosen) for i in range(5)]
                 + [row(f"q{i}", 25.0, 3, hypothesis=other) for i in range(5)]).self_check
    assert won.agreed is True and "has been right" in won.note
    lost = agenda(rows=[row(f"p{i}", 25.0, 3, hypothesis=PLAN.chosen) for i in range(5)]
                  + [row(f"q{i}", 25.0, 30, hypothesis=other) for i in range(5)]).self_check
    assert lost.agreed is False and lost.best == other and "ranking was wrong" in lost.note


def test_the_moves_come_from_the_same_analysis_the_numbers_page_uses():
    rows = [row(f"p{i}", 8.0, 1, hypothesis=PLAN.chosen) for i in range(9)]
    rows += [row(f"q{i}", 40.0, 30, hypothesis=[h for h in PLAN.hypotheses
                                                if h != PLAN.chosen][0]) for i in range(9)]
    kinds = {m.kind for m in agenda(rows=rows).moves}
    assert "stop" in kinds and "start" in kinds


def test_research_lists_only_the_claims_behind_this_week_and_dates_them():
    r = agenda().research
    assert {e["id"] for e in r.used} == {"algorithm-retention", "conversion-series",
                                         "format-need-face"}
    assert all(e["as_of"] and e["sources"][0]["url"].startswith("https://") for e in r.used)
    assert "no trend research is live" in r.note.lower()


def test_the_spend_line_is_zero_because_nothing_was_called():
    s = agenda(rows=[row("p", 20.0, 5)], landed=["a.png"]).spend
    assert s.credits.startswith("0 model calls on record")
    assert s.local == "1 frame scored and 1 post read, all local CPU."
    assert "credits, not quota" in s.next_time


def test_the_coach_reports_the_calls_this_app_counted_not_a_round_zero():
    s = agenda(rows=[row("p", 20.0, 5)], landed=["a.png"], offline=False,
               spend={"model_calls": 3, "credits": None}).spend
    assert "3 model calls on record" in s.credits
    assert "nothing here can read that balance" in s.credits


def test_a_key_without_a_call_is_still_reported_as_zero_calls():
    s = agenda(rows=[row("p", 20.0, 5)], landed=["a.png"], offline=False,
               spend={"model_calls": 0}).spend
    assert s.credits.startswith("0 model calls on record with the engine at gemini")


def test_there_is_always_something_to_propose_and_never_a_claim_to_have_acting():
    assert agenda().proposals, "an empty coach is a broken coach"
    text = " ".join(agenda().proposals).lower()
    assert "propose" in text
