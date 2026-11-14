"""The benchmark arithmetic: what she typed in, and where a post of hers lands among it.

The whole point of these tests is the refusal. A percentile out of two rows is a number with no
meaning, and this app has to say "not yet" instead of printing one; equally it must not pretend
a list somebody typed is a sample of a platform.
"""

import pytest

from src.metrics.bench import (METRICS, MIN_COMPARABLE, MIN_VIEWS, Row, count, ordinal,
                               parse_lines, place, pool, usable)


def row(label, views, likes=0, comments=0, saves=0, shares=0, follows=0, row_id=None,
        origin="saw it"):
    return Row(id=row_id, label=label, views=views, likes=likes, comments=comments,
               saves=saves, shares=shares, follows=follows, origin=origin)


def test_a_number_is_read_the_way_it_shows_on_a_screen():
    assert count("12.4k") == 12400
    assert count("3,400") == 3400
    assert count("1 234") == 1234
    assert count("2m") == 2_000_000
    assert count("89 views") == 89
    assert count("") == 0, "a count the platform never showed is blank, not zero-and-a-half"
    assert count(None) == 0


def test_a_non_number_is_named_not_silently_zeroed():
    for bad in ["lots", "1.2.3", "-400"]:
        with pytest.raises(ValueError):
            count(bad)


def test_every_rate_sits_on_the_view_count():
    r = row("a", 1000, likes=100, comments=20, saves=30, shares=10, follows=20)
    assert r.engagement == 16.0
    assert r.saves_per_100 == 3.0
    assert r.shares_per_100 == 1.0
    assert r.follows_per_1k == 20.0


def test_a_shorter_list_than_the_floor_refuses_a_percentile():
    target = row("mine", 4000, saves=120, row_id=1)
    others = [row(f"p{i}", 2000 + i * 500, saves=40 + i * 10, row_id=i + 2)
              for i in range(MIN_COMPARABLE - 2)]
    got = place(target, [target] + others, "saves")
    assert not got.ok
    assert got.percentile is None
    assert str(got.n) in got.words[0]
    assert "5 comparable" in got.words[0], got.words[0]


def test_enough_rows_and_it_says_where_the_post_sits():
    target = row("mine", 1000, saves=25, row_id=1)
    others = [row(f"p{i}", 1000, saves=(i + 1) * 10, row_id=i + 2) for i in range(8)]
    got = place(target, [target] + others, "saves")
    assert got.ok
    assert got.n == 8
    assert got.percentile == 25, "2.5 per 100 is under six of the eight"
    assert got.median == 4.5
    assert got.top_decile == 8.0
    assert "20 more saves" in " ".join(got.words), got.words
    assert any("posts you typed in" in w or "you wrote down" in w for w in got.words)


def test_beating_every_row_in_the_list_is_said_plainly():
    target = row("mine", 1000, saves=400, row_id=1)
    others = [row(f"p{i}", 1000, saves=(i + 1) * 10, row_id=i + 2) for i in range(8)]
    got = place(target, [target] + others, "saves")
    assert got.percentile == 100
    assert got.words[0].startswith("Above all 8 posts"), got.words[0]


def test_a_post_too_small_to_carry_a_rate_is_set_aside_and_counted():
    small = row("tiny", MIN_VIEWS - 1, saves=9, row_id=9)
    others = [row(f"p{i}", 5000, saves=(i + 1) * 40, row_id=i + 2) for i in range(6)]
    target = row("mine", 4000, saves=88, row_id=1)
    kept, dropped = pool([target] + others + [small], target)
    assert dropped == 1 and len(kept) == 6
    assert not usable(small) and usable(target)
    got = place(target, [target] + others + [small], "saves")
    assert got.ok and got.n == 6 and got.dropped == 1
    assert got.percentile == 33, "2.2 per 100 sits above 0.8 and 1.6 of the six"
    assert "300 views" in " ".join(got.words), got.words


def test_a_target_with_no_views_gets_no_invented_rate():
    got = place(row("mine", 0, saves=12, row_id=1),
                [row(f"p{i}", 4000, saves=90, row_id=i + 2) for i in range(6)] +
                [row("mine", 0, saves=12, row_id=1)], "saves")
    assert not got.ok
    assert "view count" in got.words[0].lower(), got.words[0]


def test_an_unknown_number_to_read_is_refused_not_guessed():
    with pytest.raises(ValueError):
        place(row("a", 100), [row("b", 100)], "reach_and_half")


def test_all_five_numbers_are_readable():
    target = row("mine", 5000, likes=200, comments=20, saves=90, shares=30, follows=40, row_id=1)
    others = [row(f"p{i}", 4000 + i * 400, likes=300, comments=60, saves=200, shares=90,
                  follows=70, row_id=i + 2) for i in range(7)]
    for key in METRICS:
        got = place(target, [target] + others, key)
        assert got.ok, key
        assert 0 <= got.percentile <= 100, key


def test_a_paste_reads_several_posts_and_names_the_line_it_could_not_use():
    rows, problems = parse_lines(
        "label, views, likes, comments, saves, shares, follows\n"
        "Outfit-07, 41000, 2100, 84, 410, 96, 61\n"
        "her reel\t180k\t9400\t220\t1100\t380\t540\n"
        "no counts here\n"
        "broken, 12o0, 40\n"
        "zero views, 0, 12\n"
    )
    assert [r.label for r in rows] == ["Outfit-07", "her reel"]
    assert rows[0].views == 41000 and rows[0].saves == 410 and rows[0].follows == 61
    assert rows[1].views == 180000
    assert len(problems) == 3, problems
    assert any("broken" in p for p in problems)
    assert any("views" in p for p in problems), problems


def test_a_trailing_comma_is_not_an_error():
    rows, problems = parse_lines("one, 5000, 300, 12, 90,")
    assert rows and rows[0].shares == 0 and rows[0].follows == 0
    assert not problems


def test_a_comma_inside_a_number_is_not_a_new_field():
    """A screen writes ninety-eight hundred as 9,800. Splitting on that comma used to make the
    view count 9 and the save rate 366 per 100 - a wrong number that looks confident."""
    rows, problems = parse_lines("vintage dress try-on, 9,800, 740, 33, 96, 21, 18")
    assert not problems, problems
    assert rows[0].views == 9800 and rows[0].likes == 740 and rows[0].comments == 33
    assert rows[0].saves == 96 and rows[0].shares == 21 and rows[0].follows == 18
    assert round(rows[0].saves_per_100, 2) == 0.98


def test_a_reading_writes_a_head_count_as_one():
    """31400.0 views is a formatting lie: nobody counts a tenth of a view."""
    target = row("mine", 31400, saves=210, row_id=1)
    others = [row(f"p{i}", 40000 + i * 1000, saves=(i + 1) * 300, row_id=i + 2)
              for i in range(6)]
    got = place(target, [target] + others, "reach")
    assert got.value_text == "31,400"
    assert got.median_text.endswith("00") and "," in got.median_text
    assert "31,400 views" in got.words[0], got.words[0]


def test_an_ordinal_is_spelled_the_way_a_person_spells_it():
    assert ordinal(1) == "1st" and ordinal(2) == "2nd" and ordinal(3) == "3rd"
    assert ordinal(11) == "11th" and ordinal(12) == "12th" and ordinal(13) == "13th"
    assert ordinal(21) == "21st" and ordinal(22) == "22nd" and ordinal(33) == "33rd"
    assert ordinal(0) == "0th" and ordinal(100) == "100th"
