from datetime import date

import pytest

from src.metrics.ingest import read_csv, read_quick



def test_a_published_at_that_carries_a_clock_keeps_the_hour(tmp_path):
    path = tmp_path / "insights.csv"
    path.write_text(
        "post_ref,published_at,views,avg_watch_pct,follows_gained\n"
        "clip-1,2026-11-12T18:40:00Z,1200,41,3\n"
        "clip-2,2026-11-11 09:05,900,12,1\n"
        "clip-3,2026-11-10,800,20,2\n",
        encoding="utf-8")
    rows = read_csv(path)
    assert [r.posted_hour for r in rows] == [18, 9, None]
    assert rows[2].published_at == date(2026, 11, 10)


def test_a_separate_hour_column_is_read_as_the_hour(tmp_path):
    path = tmp_path / "insights.csv"
    path.write_text(
        "post_ref,published_at,posted_at,views,avg_watch_pct,follows_gained\n"
        "clip-1,2026-11-12,21,1200,41,3\n", encoding="utf-8")
    assert read_csv(path)[0].posted_hour == 21


def test_a_quick_line_may_end_with_the_time_it_went_out():
    rows = read_quick("clip-1 1200 41 3 18:40\nclip-2 900 12 1\n")
    assert [r.posted_hour for r in rows] == [18, None]
    assert rows[0].views == 1200 and rows[0].avg_watch_pct == 41
    assert rows[0].post_ref == "clip-1"


def test_a_time_alone_is_still_not_three_numbers():
    with pytest.raises(ValueError):
        read_quick("clip-1 18:40\n")


def test_a_reference_full_of_digits_does_not_become_the_view_count():
    rows = read_quick("clip-0042 1200 41 3\n1200 41 3\n")
    assert rows[0].post_ref == "clip-0042" and rows[0].views == 1200
    assert rows[0].follows_gained == 3, "the time is not the fourth number"
    assert rows[1].post_ref == "post 2" and rows[1].views == 1200
