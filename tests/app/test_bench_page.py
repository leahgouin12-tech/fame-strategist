"""The benchmark page, driven the way she would drive it: type posts, ask where one sits.

The contract these tests hold is the refusal. With two rows in the list the page must not print
a percentile, and with enough rows it must not pretend the list is a measurement of the
platform - it says whose numbers these are on every reading.
"""

import re

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Config


@pytest.fixture
def world(tmp_path):
    return TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                 tmp_path / "b.sqlite3"))


def add(client, label, views, **rest):
    data = {"label": label, "platform": "", "origin": "saw it", "views": views,
            "likes": rest.get("likes", ""), "comments": rest.get("comments", ""),
            "saves": rest.get("saves", ""), "shares": rest.get("shares", ""),
            "gained": rest.get("gained", "")}
    return client.post("/bench/add", data=data)


def five_posts(client):
    for i in range(6):
        add(client, f"p{i}", "5,000", saves=str((i + 1) * 40), likes=str(300 + i * 20),
            gained=str(20 + i * 4))


def test_the_page_opens_and_says_what_it_wants(world):
    body = world.get("/bench").text
    assert "Benchmarks" in body
    assert "Write one down" in body, "the feeding action has to be on the page, not behind a link"
    assert "Nothing in the list yet" in body


def test_a_post_written_down_is_still_there_on_the_next_visit(world):
    add(world, "Outfit-07", "41k", saves="410", likes="2100", gained="61")
    body = world.get("/bench").text
    assert "Outfit-07" in body
    assert "41,000" in body, "typed as 41k, stored as a count"


def test_adding_a_row_reads_it_straight_back(world):
    five_posts(world)
    body = add(world, "mine", "4,000", saves="88", likes="200").text
    assert "mine" in body
    assert re.search(r"\d+(st|nd|rd|th)", body), body[:400]
    assert "Median" in body or "median" in body


def test_a_percentile_is_written_as_an_ordinal(world):
    """Two of six is 33rd. Printing "33th" is the kind of tell that a sentence was assembled by
    sticking a suffix on a number, and this page's headline sentence is read out loud."""
    five_posts(world)
    body = add(world, "mine", "4,000", saves="88").text
    assert "33rd" in body, "two of the six sit under 2.2 saves per 100"
    assert "33th" not in body


def test_a_short_list_is_refused_a_percentile(world):
    add(world, "one", "4,000", saves="90")
    body = add(world, "two", "6,000", saves="120").text
    assert "Not enough to say yet" in body, "the 2nd of 2 rows is not a percentile"
    assert not re.search(r"<span class=\"big\">\d+", body), "no invented number in the big slot"


def test_a_number_that_is_not_a_number_is_named(world):
    body = add(world, "typo", "lots").text
    assert "not counts" in body
    assert "typo" not in world.get("/bench").text, "the row that failed to parse was not stored"


def test_a_row_without_views_is_refused(world):
    body = add(world, "no reach", "").text
    assert "Views has to be above zero" in body
    assert "no reach" not in world.get("/bench").text


def test_a_row_needs_a_name_because_a_blank_list_cannot_be_read_back(world):
    body = add(world, "", "9,000", saves="200").text
    assert "something to be called" in body


def test_reading_switches_which_number_is_written_out(world):
    five_posts(world)
    add(world, "mine", "4,000", saves="88", likes="200")
    row_id = re.findall(r'name="bench_id" value="(\d+)"', world.get("/bench").text)
    body = world.post("/bench/read", data={"bench_id": row_id[-1], "metric": "reach"}).text
    assert "Views" in body
    assert "set aside" in body or "comparable" in body


def test_a_paste_adds_the_readable_lines_and_names_the_one_it_could_not_read(world):
    body = world.post("/bench/paste", data={"lines": (
        "her reel, 180k, 9400, 220, 1100, 380, 540\n"
        "another, 22000, 1400, 60, 300, 90, 40\n"
        "this one has no numbers\n")}).text
    assert "her reel" in body and "another" in body
    assert "2 posts added" in body
    assert "this one has no numbers" in body, "a line she typed is never dropped in silence"


def test_forget_takes_one_row_and_clear_takes_the_list(world):
    five_posts(world)
    row_id = re.findall(r'name="bench_id" value="(\d+)"', world.get("/bench").text)[0]
    world.post("/bench/forget", data={"bench_id": row_id})
    body = world.get("/bench").text
    assert "p0" not in body and "p5" in body
    cleared = world.post("/bench/clear").text
    assert "The typed list is empty" in cleared
    assert "5,000" not in world.get("/bench").text


def test_nothing_on_this_page_claims_to_have_reached_a_platform(world):
    five_posts(world)
    body = add(world, "mine", "4,000", saves="88").text
    for claim in ["pulled from instagram", "scraped", "fetched", "connected to", "posted for you"]:
        assert claim.lower() not in body.lower(), claim
    assert "posts you typed in" in body or "wrote numbers for" in body


def test_the_nav_carries_it_too(world):
    assert "/bench" in world.get("/today").text
