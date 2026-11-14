"""The lab, driven the way she would drive it: post, type three numbers, come back and ask
what the test showed.

What these tests hold is the refusal, not the arithmetic. A page that always finds a winner
would be the most convincing way to lie to her, so the checks are: an arm comes from the week
the plan names, never from a guess; three posts do not call a test; the tag button only fills
the empty cells; and a decision is written to memory only when the stored posts themselves
support it - the form's hidden fields are not trusted with it.
"""

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Config

COMPLETE = {
    "hours_per_week": "6",
    "existing_followers": "0",
    "what_you_actually_film": "outfits in my room and the odd street clip",
    "gear": "phone",
    "has_clips": "on",
    "on_camera": "on",
    "platforms": ["tiktok", "reels"],
    "comfort": ["talking", "text on screen"],
}

HEADERS = "post_ref,views,avg_watch_pct,follows_gained,hypothesis,posted_at"


def lines(rows):
    return "\n".join(f"{ref},{views},{watch},{gained},{arm}," for ref, views, watch, gained, arm
                     in rows)


@pytest.fixture
def world(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "lab.sqlite3"))
    client.folder = tmp_path
    return client


def plan_built(client):
    client.post("/interview", data=COMPLETE)
    client.post("/plan/build")
    plan = client.app.state.kit.plan()
    return plan.weeks[0].experiment, plan.weeks[1].experiment


def store(client, rows):
    (client.folder / "metrics-last.csv").write_text(HEADERS + "\n" + lines(rows) + "\n",
                                                    encoding="utf-8")


def flat(html: str) -> str:
    """The page as she reads it: the markup wraps sentences across lines and escapes an
    apostrophe into `&#39;`, so a test that compares raw html to a sentence would be checking
    the template's line length and its entity table instead of the words."""
    return re.sub(r"\s+", " ", unescape(html))


def test_the_lab_names_the_hypothesis_the_plan_is_running_this_week(world):
    arm, other = plan_built(world)
    body = flat(world.get("/lab").text)
    assert "The lab" in body
    assert arm in body, "the week's own hypothesis is the headline of the page"
    assert "week 1 of 8" in body
    assert "What would count:" in body, "a test without a success condition is a wish"
    assert other not in body, "the arm she is not on yet must not look like it is running"


def test_with_no_plan_it_says_what_is_missing_instead_of_an_empty_table(world):
    body = world.get("/lab").text
    assert "No plan yet" in body
    assert "nothing has an arm to belong to" in body.lower()
    assert "Build the plan" in body, "the way out of the empty state is on the page"


def test_typing_numbers_files_them_under_the_week_that_was_running(world):
    arm, _ = plan_built(world)
    note = world.post("/numbers", data={"quick": "clip-1 1200 40 12\nclip-2 900 33 9\n"
                                                "clip-3 1500 45 21"}).text
    stored = (world.folder / "metrics-last.csv").read_text(encoding="utf-8")
    assert arm in stored, "the hypothesis column was the one nothing ever filled in"
    assert "filed under this week" in note.lower()
    assert arm in world.get("/lab").text, "the lab reads what the ledger stored"


def test_eight_posts_on_one_arm_are_called_a_habit_not_a_result(world):
    arm, _ = plan_built(world)
    store(world, [(f"a{i}", 1000, 30.0, 14, arm) for i in range(8)])
    body = flat(world.get("/lab").text)
    assert "One arm is a habit, not a test." in body
    assert "kept" not in body.split("The arms")[0].lower(), \
        "nothing has been kept when nothing was compared"
    assert "Run the week's alternative" in body


def test_a_called_test_writes_the_decision_and_its_numbers_to_memory(world):
    arm, other = plan_built(world)
    store(world, [(f"a{i}", 1000, 30.0, 14, arm) for i in range(5)]
                + [(f"b{i}", 1000, 30.0, 5, other) for i in range(5)])
    body = world.post("/lab/decide", data={"winner": arm, "loser": other}).text
    assert f"Remembered: kept {arm}, dropped {other}." in body
    stored = world.app.state.kit.db.recall("verdict")
    assert len(stored) == 1 and arm in stored[0]["body"] and other in stored[0]["body"]
    assert "2.8" in stored[0]["body"], "a decision in memory without its numbers is a rumour"
    assert "Decisions this lab has already written down" in body


def test_the_form_cannot_write_a_verdict_the_stored_posts_do_not_support(world):
    arm, other = plan_built(world)
    store(world, [(f"a{i}", 1000, 30.0, 14, arm) for i in range(6)]
                + [(f"b{i}", 1000, 30.0, 5, other) for i in range(2)])
    body = flat(world.post("/lab/decide", data={"winner": arm, "loser": other}).text)
    assert "Nothing was written." in body
    assert world.app.state.kit.db.recall("verdict") == []
    assert f"1 more under {other}" in body, "the refusal has to say what would change it"


def test_the_button_rewrites_only_the_rows_with_no_hypothesis(world):
    arm, other = plan_built(world)
    store(world, [(f"a{i}", 1000, 30.0, 9, other) for i in range(2)]
                + [(f"n{i}", 1000, 30.0, 9, "") for i in range(4)])
    body = world.post("/lab/tag", data={"arm": arm}).text
    stored = (world.folder / "metrics-last.csv").read_text(encoding="utf-8")
    assert "Filed 4 posts under" in body
    assert stored.count(f",{other},") == 2, "a post she labelled keeps that label"
    assert stored.count(f",{arm},") == 4
    assert "no hypothesis was given" in world.post("/lab/tag", data={"arm": ""}).text.lower()


def test_nothing_is_offered_to_file_when_every_post_already_has_an_arm(world):
    arm, other = plan_built(world)
    store(world, [(f"a{i}", 1000, 30.0, 9, arm) for i in range(3)]
                + [(f"b{i}", 1000, 30.0, 9, other) for i in range(3)]
                + [(f"c{i}", 1000, 30.0, 9, arm) for i in range(2)])
    body = flat(world.get("/lab").text)
    assert 'action="/lab/tag"' not in body
    assert "across 2 arms" in body, "eight posts split over two labelled arms"
    assert "already carries a hypothesis" in flat(
        world.post("/lab/tag", data={"arm": arm}).text)


def test_the_arms_table_shows_which_posts_sit_under_which_hypothesis(world):
    arm, other = plan_built(world)
    store(world, [(f"a{i}", 1000, 30.0, 14, arm) for i in range(4)]
                + [(f"b{i}", 1000, 30.0, 5, other) for i in range(4)])
    body = world.get("/lab").text
    assert "follows per 1000 views" in body
    assert "a0, a1, a2, a3" in body, "she has to be able to check which posts made the claim"
    assert "14.0 per 1000 views" in body and "5.0 per 1000 views" in body


def test_the_lab_is_reachable_from_the_rail_like_every_other_room(world):
    assert 'href="/lab"' in world.get("/today").text


def test_a_written_verdict_takes_its_arm_out_of_the_next_plan_built(world):
    """The page promises that a dropped arm does not get a week back, so the promise is
    checked end to end: decide on the lab, rebuild the plan, read the plan page."""
    arm, other = plan_built(world)
    store(world, [(f"a{i}", 1000, 30.0, 14, arm) for i in range(5)]
                + [(f"b{i}", 1000, 30.0, 5, other) for i in range(5)])
    world.post("/lab/decide", data={"winner": arm, "loser": other})
    world.post("/plan/build")
    rebuilt = world.app.state.kit.plan()
    assert other not in [w.experiment for w in rebuilt.weeks[:4]], \
        "the arm the lab dropped is still scheduled"
    assert rebuilt.weeks[0].experiment == arm, "the kept arm keeps its week"
    body = flat(world.get("/plan").text)
    assert f"Week 2 was {other}" in body, "the plan says which week moved and why"
