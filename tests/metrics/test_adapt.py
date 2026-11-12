from datetime import date

import pytest

from src.engines.offline import OfflineEngine
from src.metrics.adapt import DATA_FLOOR, analyse, apply
from src.metrics.ingest import MetricRow, read_csv, read_quick
from src.strategist.niche import rank, score_candidates
from src.strategist.plan import compose_plan
from tests.strategist.test_niche import ANSWERS, ENTRIES

PLAN = compose_plan(
    ENTRIES, ANSWERS, rank(score_candidates(ENTRIES, ANSWERS)), OfflineEngine(), date(2026, 11, 9)
)


def row(ref, watch, follows, views=1000, hypothesis="tutorial-value"):
    return MetricRow("tiktok", ref, date(2026, 11, 1), views * 3, views, watch, follows, 4, 1,
                     hypothesis=hypothesis)


def test_read_csv_parses_the_export_shape(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text(
        "post_ref,reach,views,avg_watch_pct,follows_gained,comments,saves\n"
        "a,100,50,20,2,1,1\n",
        encoding="utf-8",
    )
    assert read_csv(p)[0].avg_watch_pct == 20


def test_read_csv_tolerates_a_platform_column_and_headers_in_any_order(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text(
        "views,follows_gained,post_ref,platform,reach,avg_watch_pct,comments,saves\n"
        "500,9,a,x,22,3,1\n",
        encoding="utf-8",
    )
    r = read_csv(p)[0]
    assert (r.platform, r.views, r.follows_gained) == ("x", 500, 9)


def test_read_csv_reports_a_missing_column_by_name(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("post_ref,views\na,10\n", encoding="utf-8")
    import pytest

    with pytest.raises(ValueError, match="avg_watch_pct"):
        read_csv(p)


def test_low_watch_high_follow_is_not_called_a_problem():
    assert not [a for a in analyse([row("a", 15, 40)], PLAN) if a.kind == "stop"]


def test_refuses_conclusions_below_the_data_floor():
    adjustments = analyse([row("a", 30, 1)], PLAN)
    assert any(a.kind == "insufficient_data" for a in adjustments)
    assert len(adjustments) == 1, "it should say one thing: not enough data"


def test_flags_the_weakest_format_when_volume_is_enough():
    rows = [row(f"{i}", 12 if i % 2 else 40, 1) for i in range(8)]
    assert {a.kind for a in analyse(rows, PLAN)} & {"adjust", "stop"}


def test_a_winning_hypothesis_is_named_for_amplification():
    rows = [row(f"a{i}", 45, 12, hypothesis="tutorial-value") for i in range(5)] + [
        row(f"b{i}", 18, 1, hypothesis="comedy-sketch-pov") for i in range(5)
    ]
    amps = [a for a in analyse(rows, PLAN) if a.kind == "amplify"]
    assert amps and "tutorial-value" in amps[0].target


def test_every_adjustment_cites_entries_and_names_a_number():
    for a in analyse([row(f"{i}", 10, 0) for i in range(10)], PLAN):
        if a.kind in ("adjust", "stop", "amplify"):
            assert a.evidence_ids, a.kind
            assert any(c.isdigit() for c in a.reason), a.reason


def test_apply_never_reduces_below_one_post_a_week():
    shrunk = apply(PLAN, analyse([row(f"{i}", 5, 0, views=100) for i in range(10)], PLAN))
    assert all(w.target_posts >= 1 for w in shrunk.weeks)


def test_apply_produces_a_plan_that_still_round_trips():
    shrunk = apply(PLAN, analyse([row(f"{i}", 40, 3) for i in range(10)], PLAN))
    assert PLAN.__class__.from_dict(shrunk.to_dict()).weeks[0].week_no == 1


def test_hold_says_so_instead_of_inventing_a_change():
    rows = [row(f"{i}", 40, 2) for i in range(10)]
    assert not [a for a in analyse(rows, PLAN) if a.kind in ("adjust", "stop")]


def test_three_numbers_a_line_need_no_export(tmp_path):

    rows = read_quick("1200 41 3\n860 18 0\n2400 52 11")
    assert len(rows) == 3
    assert rows[0].views == 1200 and rows[0].avg_watch_pct == 41
    assert rows[2].follow_rate_per_1000 == round(11 / 2400 * 1000, 2)


def test_commas_and_percent_signs_are_ignored():

    row = read_quick("1,200 views, 41%, 3")[0]
    assert (row.views, row.avg_watch_pct, row.follows_gained) == (1200, 41.0, 3)
    assert row.post_ref == "post 1"


def test_a_short_line_is_named_rather_than_filled_with_zero():

    with pytest.raises(ValueError, match="line 2"):
        read_quick("1200 41 3\njust a note to self")
