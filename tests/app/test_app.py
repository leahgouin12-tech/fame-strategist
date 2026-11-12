from datetime import date

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


@pytest.fixture
def client(tmp_path):
    app = create_app(Config(api_key=None, engine_name="offline", model=""), tmp_path / "a.sqlite3")
    return TestClient(app)


@pytest.fixture
def planned(client):
    client.post("/interview", data=COMPLETE)
    client.post("/plan/build")
    return client


def test_the_app_states_what_it_cannot_promise(client):
    assert "cannot promise" in client.get("/").text.lower()


def test_offline_mode_is_announced_not_hidden(client):
    assert "without a model key" in client.get("/").text.lower()


def test_home_lists_the_loaded_evidence(client):
    body = client.get("/").text
    assert "claims" in body and "engine: offline" in body


def test_the_interview_refuses_an_unusable_answer_and_saves_nothing(client):
    body = client.post("/interview", data={**COMPLETE, "hours_per_week": "1"}).text
    assert "hours_per_week must be at least 2" in body
    assert "take the interview" in client.get("/niches").text.lower()


def test_a_blank_field_is_named_not_filled_in(client):
    body = client.post("/interview", data={**COMPLETE, "what_you_actually_film": ""}).text
    assert "what_you_actually_film" in body
    assert 'value="outfits in my room' not in body


def test_scoring_returns_ranked_hypotheses_with_numbers(planned):
    body = planned.get("/niches").text
    assert "total" in body and "saturation read" in body


def test_the_plan_shows_eight_weeks_and_their_sourced_basis(planned):
    body = planned.get("/plan").text
    assert body.count("<tr>") >= 9
    assert "Weeks 1-4 measure" in body


def test_today_shows_the_shot_list_and_says_who_wrote_the_copy(planned):
    body = planned.get("/today", params={"on": "2026-11-20"}).text
    assert "Say this first" in body
    assert "Shots" in body
    assert "copy written by: local" in body
    assert "engine: offline" in body
    assert "[" not in body.split("Say this first")[1][:220]


def test_one_click_replaces_the_whole_setup(client):
    """The interview is optional. One POST adopts the stated assumptions and lands on
    a day that is actually filmable."""
    assert "Assuming:" in client.get("/").text
    body = client.post("/start", data={"what_you_actually_film": "outfits in my room"}).text
    assert "Say this first" in body
    assert "outfits" in body.lower()
    assert "Week" in body and "copy written by" in body


def test_the_one_click_page_lists_every_assumption_it_is_making(client):
    body = client.get("/").text
    for line in ["hours a week", "on camera", "starting from 0 followers"]:
        assert line in body


def test_three_numbers_typed_off_the_phone_beat_a_csv_export(planned):
    lines = "\n".join(f"{1000 + i} {12 if i % 2 else 40} {1 if i % 2 else 9}" for i in range(9))
    body = planned.post("/numbers", data={"quick": lines}).text
    assert "9 posts read" in body
    assert "adjust" in body or "stop" in body or "amplify" in body
    assert planned.post("/numbers/apply").status_code == 200


def test_a_line_that_is_not_three_numbers_is_named_not_guessed(planned):
    body = planned.post("/numbers", data={"quick": "1200 41 3\ni forgot this one"}).text
    assert "line 2" in body


def test_marking_a_day_posted_persists(planned):
    planned.post("/today/done", data={"on": "2026-11-20"})
    assert "marked posted" in planned.get("/today", params={"on": "2026-11-20"}).text


def test_metrics_below_the_data_floor_are_met_with_an_admission(planned):
    csv = "post_ref,views,avg_watch_pct,follows_gained\na,500,30,2\nb,400,12,1\nc,900,44,4\n"
    body = planned.post("/numbers", files={"csv": ("m.csv", csv, "text/csv")}).text
    assert "below the floor" in body
    assert "amplify" not in body


def test_metrics_above_the_floor_produce_a_reading(planned):
    rows = "\n".join(f"p{i},1000,{12 if i % 2 else 40},{1 if i % 2 else 9}" for i in range(9))
    csv = "post_ref,views,avg_watch_pct,follows_gained\n" + rows
    body = planned.post("/numbers", files={"csv": ("m.csv", csv, "text/csv")}).text
    assert "adjust" in body or "stop" in body


def test_every_claim_page_shares_who_said_it_and_what_it_misses(client):
    body = client.get("/sources").text
    assert "Does not establish" in body
    assert 'href="https://' in body


def test_no_page_offers_the_forbidden_actions(planned):
    # /sources is excluded on purpose: it quotes the platforms' own policy text, which
    # names these behaviours in order to say they cost reach.
    pages = [planned.get(p).text for p in ["/", "/niches", "/plan", "/today", "/numbers"]]
    joined = " ".join(pages).lower()
    for verb in ["unfollow", "auto-follow", "buy followers", "mass follow", "public url", "dm"]:
        assert verb not in joined, verb


def test_no_form_or_endpoint_implements_account_automation(planned):
    import re

    html = " ".join(planned.get(p).text for p in ["/", "/niches", "/plan", "/today", "/numbers"])
    actions = re.findall(r'action="([^"]+)"', html)
    assert actions
    assert not any(re.search(r"follow|dm|message|publish|scrape", a) for a in actions)


def test_the_app_binds_nothing_public(client):
    paths = {getattr(r, "path", "") for r in client.app.routes}
    assert not any(p.startswith("/media") or "public" in p for p in paths)
    assert not any("follow" in p for p in paths)
