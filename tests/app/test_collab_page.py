"""The collaboration page as she uses it: file a name, read the pitch, move the stage herself.

What is proved here is the page's behaviour rather than the module's: that the room is in the
rail where she would look for it, that an empty page invents neither a name nor a number, that
the four lines of a pitch are built out of what she typed and nothing else, that a reasonless
entry is told why it has no pitch instead of being handed a plausible one, that the reply
percentage stays off the page until enough asks are behind it, that reading the page writes
nothing, and that no sentence on it claims a message ever left her machine.
"""

import re
from datetime import date
from html import unescape

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.collab import store as collab_store
from src.config import Config
from src.metrics.ingest import MetricRow

TODAY = date(2026, 11, 14)
NAME = "@laurenmakesthefits"
WHY = "she answered a comment from a small account with a 90-second tutorial"
ASK = "a swap: I film the try-on in your jacket, you film mine, one cut each"


def flat(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(html))


@pytest.fixture
def world(tmp_path):
    return TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                 tmp_path / "collab.sqlite3"))


def file_somebody(world, name=NAME, why=WHY, ask=ASK, fmt="one reel each, filmed the same week",
                  platform="tiktok"):
    return world.post("/collab/add", data={"name": name, "why": why, "ask": ask,
                                           "format": fmt, "platform": platform},
                      follow_redirects=True)


def imported(world, platform, views, follows=9):
    """Her own import, the way the Numbers page leaves it: one row per post."""
    world.app.state.kit.save_rows([
        MetricRow(platform, f"{platform}{n}", TODAY, v, v, 40.0, follows, 3, 2)
        for n, v in enumerate(views)])


def listed(world):
    return collab_store.load(world.app.state.db)


def body(world):
    return flat(world.get("/collab").text)


def mark(world, row, status):
    return flat(world.post("/collab/move", data={"id": row["id"], "status": status},
                           follow_redirects=True).text)


def test_the_room_is_in_the_rail_where_she_would_already_be_looking_for_it(world):
    from_other_page = flat(world.get("/today").text)
    assert "Pitch" in from_other_page and 'href="/collab"' in from_other_page, \
        "the page has to be reachable, not only addressable"
    assert 'href="/collab"' in body(world), "and stay in the rail when she is on it"


def test_an_empty_page_invents_neither_a_name_nor_a_number(world):
    got = body(world)
    assert "Nobody is on the list" in got
    assert "no number of yours to quote" in got
    assert "Numbers page" in got, "it has to say where a number would come from"
    assert "reason this app made up" in got, "and why the reason has to be hers"


def test_reading_the_page_writes_nothing_at_all(world):
    body(world)
    body(world)
    assert listed(world) == []
    assert "Nobody is on the list" in body(world), "still empty after two visits"


def test_filing_somebody_puts_the_pitch_under_their_own_name(world):
    got = flat(file_somebody(world).text)
    assert NAME in got
    assert f"Here is the specific thing: {WHY}" in got, "her reason goes in verbatim"
    assert ASK in got and "one reel each, filmed the same week" in got
    assert got.count("If it is not a fit, no worries") == 1
    assert "On my side: the work, because I would rather you judged it than a number." in got, \
        "with nothing imported the pitch says so rather than quoting a figure"
    assert "no number: nothing has been imported for that platform" in got, \
        "and the refusal is named, not left implied"


def test_a_saved_entry_says_why_it_has_no_pitch_rather_than_getting_an_invented_reason(world):
    got = flat(world.post("/collab/add", data={"name": "@onlyaname"},
                          follow_redirects=True).text)
    assert "@onlyaname" in got, "what she typed is not thrown away because a field was short"
    assert "No reason typed yet" in got
    assert "Here is the specific thing" not in got, "and no sentence is written for it"
    assert "Nobody is on the list" not in got, "the name is filed, so this is not an empty page"


def test_the_offer_is_arithmetic_on_the_import_and_uses_the_median_not_the_mean(world):
    imported(world, "tiktok", [1000, 2000, 3000, 40000])
    got = body(world)
    assert ("a median of 2,500 views across 4 posts on tiktok, 40.0% watched through, 0.78 "
            "follows per 1000 views") in got
    assert "11,500" not in got, "one post that went off must not be averaged into her typical"


def test_a_platform_with_one_post_behind_it_is_quoted_as_one_afternoon(world):
    imported(world, "reels", [900])
    got = body(world)
    assert ("1 post on reels, the best of them 900 views - that is one afternoon that went well, "
            "not a rate") in got
    assert "a median of" not in got, "there is no median in a list of one"


def test_a_filed_pitch_leads_with_the_platform_she_named_not_the_biggest_one(world):
    imported(world, "tiktok", [1000, 2000, 3000, 4000])
    imported(world, "reels", [900])
    got = flat(file_somebody(world, platform="reels").text)
    pitch = got.split("Here is the specific thing")[1]
    assert "the best of them 900 views" in pitch, \
        "she filed the name under reels, so the pitch quotes reels and not her biggest platform"
    assert "2,500" not in pitch


def test_a_stage_moves_only_when_she_moves_it_and_the_page_counts_what_she_said(world):
    file_somebody(world)
    got = mark(world, listed(world)[0], "replied")
    assert "replied: 1" in got
    assert "to pitch: 0" in got, "the stage moved, it was not copied"
    assert "something you typed" in got, "and the page says whose record this is"


def test_a_stage_the_app_cannot_see_is_refused_out_loud_with_the_five_it_knows(world):
    file_somebody(world)
    got = mark(world, listed(world)[0], "sent")
    assert "is not one of the stages" in got
    for stage in ("to pitch", "pitched", "replied", "no answer", "made something"):
        assert stage in got, "the refusal lists what she can actually type"
    assert "to pitch: 1" in got, "and nothing moved"


def test_a_stage_button_on_the_page_offers_only_the_five(world):
    file_somebody(world)
    got = body(world)
    assert 'name="status" value="sent"' not in got
    for stage in ("to pitch", "pitched", "replied", "no answer", "made something"):
        assert f'name="status" value="{stage}"' in got


def test_the_reply_percentage_is_off_the_page_until_enough_asks_are_behind_it(world):
    for index in range(3):
        file_somebody(world, name=f"@three{index}")
    rows = listed(world)
    mark(world, rows[1], "pitched")
    mark(world, rows[2], "pitched")
    got = mark(world, rows[0], "replied")
    assert "not a rate yet" in got
    assert "came back." in got, "the sentence closes without a percentage"
    assert "1 answered out of 3 sent is not a rate yet" in got
    assert "33.3%" in got and "came back (33.3%)" not in got, \
        "the number appears only inside the sentence that refuses to call it a rate"


def test_once_there_are_enough_asks_the_same_page_prints_the_number_it_just_refused(world):
    for index in range(6):
        file_somebody(world, name=f"@six{index}")
    rows = listed(world)
    for row in rows[1:5]:
        mark(world, row, "pitched")
    got = mark(world, rows[0], "replied")
    assert "enough asks" in got
    assert "came back (20.0%)" in got, "five asks is enough to print, and it says that it is"


def test_taking_a_name_off_the_list_says_there_was_nothing_to_unsend(world):
    file_somebody(world)
    got = flat(world.post("/collab/forget", data={"id": listed(world)[0]["id"]},
                          follow_redirects=True).text)
    assert NAME not in got
    assert "nothing to unsend" in got
    assert listed(world) == []


def test_no_line_on_the_page_claims_a_message_left_or_a_creator_was_found(world):
    file_somebody(world)
    imported(world, "tiktok", [1000, 2000, 3000])
    got = body(world).lower()
    for claim in ("sent for you", "we sent", "i have sent", "contacted them", "auto-sent",
                  "found creators", "creators you should", "recommended partners",
                  "dm them for you", "logged in"):
        assert claim not in got, claim
    assert "no login" in got, "it says instead what it cannot do and why"
