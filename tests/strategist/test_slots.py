from src.metrics.ingest import MetricRow
from src.strategist.slots import BUCKET_FLOOR, SLOT_FLOOR, block_of, report


def row(hour, views, follows=2, ref=None, i=0):
    return MetricRow(platform="tiktok", post_ref=ref or f"clip-{i}", published_at=None,
                     reach=0, views=views, avg_watch_pct=40.0, follows_gained=follows,
                     comments=0, saves=0, posted_hour=hour)


def timed(counts: dict[int, list[int]], start=0):
    """counts maps an hour to the view counts posted in it."""
    rows, i = [], start
    for hour, views in counts.items():
        for v in views:
            i += 1
            rows.append(row(hour, v, i=i))
    return rows


def test_block_of_names_the_part_of_the_day_a_person_would_use():
    assert block_of(8) == "morning"
    assert block_of(12) == "midday"
    assert block_of(18) == "evening"
    assert block_of(22) == "late"
    assert block_of(2) == "late", "2am belongs to the night that started at 20:00, not to morning"
    assert block_of(5) == "morning"


def test_nothing_is_measured_before_the_floor():
    result = report(timed({18: [1000] * (SLOT_FLOOR - 1)}))
    assert not result.measured
    assert result.need == 1
    assert "1 more post with a clock time" in result.note or "19" in result.note


def test_an_import_without_a_single_time_says_so_instead_of_guessing():
    rows = [row(None, 1000 + i, i=i) for i in range(30)]
    result = report(rows)
    assert not result.measured and result.timed == 0
    assert "none of them carrying a time" in result.note


def test_the_floor_is_the_day_the_default_stops_being_the_answer():
    rows = timed({18: [1000] * SLOT_FLOOR})
    result = report(rows)
    assert result.measured and result.timed == SLOT_FLOOR
    assert "Replaced at 20 timed posts" in result.note


def test_windows_are_ranked_by_median_views_not_by_hope():
    rows = timed({9: [500, 600, 700, 800, 900, 1000, 1100],
                  19: [2000, 2100, 2200, 2300, 2400, 2500, 2600],
                  13: [100, 200, 300, 400, 500, 600, 700]})
    result = report(rows)
    assert [w.block for w in result.windows] == ["evening", "morning", "midday"]
    assert result.windows[0].median_views == 2300
    assert "evening against midday" in result.note


def test_a_window_of_two_posts_is_not_a_window():
    rows = timed({18: [1000] * (SLOT_FLOOR - 2), 9: [4000, 4001]})
    result = report(rows)
    assert result.measured
    assert [w.block for w in result.windows] == ["evening"]
    assert [w.block for w in result.thin] == ["morning"]
    assert all(w.posts >= BUCKET_FLOOR for w in result.windows)


def test_one_window_is_a_schedule_and_not_allowed_to_look_like_a_result():
    rows = timed({18: [1000] * SLOT_FLOOR})
    result = report(rows)
    assert result.measured and len(result.windows) == 1
    assert "schedule, not a comparison" in result.note


def test_the_measured_note_keeps_the_confound_in_the_sentence():
    rows = timed({9: [500] * 10, 19: [2000] * 10})
    result = report(rows)
    assert "is not what you post at another" in result.note
    assert "one test" in result.note, "the finding has to arrive with the move it supports"


def test_no_import_at_all_says_there_is_nothing_to_rank_yet():
    result = report([])
    assert not result.measured and result.total == 0
    assert "Nothing has been imported yet" in result.note
    assert "posts read" not in result.note, "it must not imply data she does not have"


def test_a_partial_import_names_both_numbers_it_is_short_of():
    rows = timed({18: [1000] * 15}) + [row(None, 900, i=90 + n) for n in range(9)]
    result = report(rows)
    assert not result.measured and result.timed == 15 and result.need == 5
    assert "15 of the 20 timed posts" in result.note
    assert "9 of them without a clock time" in result.note
