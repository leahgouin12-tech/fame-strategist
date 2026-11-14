from datetime import date

import pytest
from fastapi.testclient import TestClient

from src.agent import modes, orchestrator, tools as agent_tools
from src.app import create_app
from src.config import Config
from src.db import DB

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
def kit_client(tmp_path):
    app = create_app(Config(api_key=None, engine_name="offline", model=""), tmp_path / "a.sqlite3")
    return TestClient(app), DB(tmp_path / "a.sqlite3"), tmp_path


@pytest.fixture
def planned(kit_client):
    client, db, tmp = kit_client
    client.post("/interview", data=COMPLETE)
    client.post("/plan/build")
    return client, db, tmp


def last_step(db, tool):
    for run in db.recent_runs():
        for step in run["steps"]:
            if step["tool"] == tool:
                return run, step
    raise AssertionError(f"{tool} never appeared in {db.recent_runs()}")


def test_the_command_centre_offers_every_mode_and_names_its_hands(kit_client):
    client, _, _ = kit_client
    got = client.get("/agent")
    assert got.status_code == 200
    body = got.text
    for label in ("Researcher", "Strategist", "Creator", "Manager", "Growth Operator",
                  "Autonomous Agency"):
        assert label in body
    assert "toolbox" in body.lower()


def test_a_run_says_which_planner_wrote_it_and_tallies_the_verdicts(kit_client):
    client, db, _ = kit_client
    client.post("/agent/run", data={"asked": "research what is working", "mode": "researcher"})
    run = db.recent_runs(1)[0]
    assert run["planner"] == "The Scout (rulebook)", \
        "offline means offline: the rulebook chose this, and the desk it chose is named"
    assert run["summary"] == "1 done, 1 advised, 1 skipped"


def test_a_tool_with_an_unmet_need_is_skipped_with_the_reason_not_faked(kit_client):
    client, db, _ = kit_client
    client.post("/agent/run", data={"asked": "research what is working", "mode": "researcher"})
    _, step = last_step(db, "research.week")
    assert step["kind"] == "skipped"
    assert "no eight-week plan" in step["summary"]


def test_a_capability_outside_the_mode_is_refused_rather_than_quietly_run(kit_client):
    client, db, _ = kit_client
    client.post("/agent/run", data={"asked": "build my plan", "mode": "researcher"})
    _, step = last_step(db, "strategy.niches")
    assert step["kind"] == "skipped"
    assert "Researcher does not reach for Strategy" in step["summary"]


def test_work_outside_the_auto_set_stops_at_advice_until_she_presses_it(planned):
    client, db, _ = planned
    client.post("/agent/run", data={"asked": "what should I shoot today", "mode": "strategist"})
    _, step = last_step(db, "day.list")
    assert step["kind"] == "advised"
    assert db.get_days("0000-01-01", "9999-12-31") == [], "advice must not have written the day"
    pressed = client.post("/agent/step", data={"step": str(step["id"])})
    assert "takes written" in pressed.text
    assert last_step(db, "day.list")[1]["kind"] == "did"
    assert db.get_days("0000-01-01", "9999-12-31"), "pressing it actually ran it"


def test_pressing_a_step_refused_by_the_mode_cannot_bypass_it(planned):
    client, db, _ = planned
    client.post("/agent/run", data={"asked": "build my plan", "mode": "researcher"})
    step = last_step(db, "strategy.niches")[1]
    assert orchestrator.carry_out(client.app.state.kit, step["id"]) is None
    assert last_step(db, "strategy.niches")[1]["kind"] == "skipped"


def test_authorising_a_capability_once_stops_it_asking_every_time(planned):
    client, db, _ = planned
    client.post("/grants", data={"cap": ["strategy"], "mode": "strategist"})
    client.post("/agent/run", data={"asked": "what should I shoot today", "mode": "strategist"})
    assert last_step(db, "day.list")[1]["kind"] == "did"


def test_staging_writes_the_day_out_and_says_in_the_file_that_it_cannot_post(planned):
    client, db, tmp = planned
    client.post("/agent/run", data={"asked": "stage today", "mode": "manager"})
    folder = tmp / "staged" / date.today().isoformat()
    assert {p.name for p in folder.iterdir()} == {
        "caption.txt", "shot-list.txt", "per-platform.txt", "this-day.md"}
    sheet = (folder / "this-day.md").read_text(encoding="utf-8")
    assert "It did not post" in sheet
    run, step = last_step(db, "queue.stage")
    assert step["kind"] == "did" and step["detail"]["files"]


def test_the_memory_keeps_what_it_learned_with_the_date_it_was_learned(planned):
    client, db, _ = planned
    client.post("/agent/run", data={"asked": "research what is working", "mode": "researcher"})
    notes = db.recall("finding")
    assert notes
    ids = {e.id for e in client.app.state.kit.entries()}
    assert {n["source"] for n in notes} <= ids, "every remembered claim cites its own playbook entry"
    assert all(n["seen_at"] for n in notes), "and says when it was read"


def test_a_tool_that_throws_is_a_failed_step_rather_than_a_silent_one(planned, monkeypatch):
    client, _, _ = planned

    def explode(kit):
        raise RuntimeError("the folder moved")

    monkeypatch.setitem(agent_tools.REGISTRY, "test.explode", agent_tools.Tool(
        "test.explode", "Explode", "Test", "research", (), (), "nothing", explode))
    out = orchestrator.execute(client.app.state.kit, "test.explode", {})
    assert out.kind == "failed"
    assert "RuntimeError" in out.summary and "the folder moved" in out.summary


def test_the_registry_describes_every_tool_in_a_department():
    rows = agent_tools.catalogue()
    assert len(rows) == len(agent_tools.REGISTRY) >= 12
    for row in rows:
        assert row["dept"] and len(row["describe"]) > 30, f"{row['id']} has no description"
        assert row["cap"] in modes.CAPS, f"{row['id']} reaches for a capability that is not a mode's"


def test_the_receipt_lines_are_english_not_json(planned):
    _, _, _ = planned
    lines = orchestrator.narrate({
        "picked": [{"id": "B-02", "claim": "Hooks land in the first line", "tier": "proven"}],
        "window": {"hours": "18:00-21:00", "posts": 4},
        "measured": True,
        "contested": 0,
    })
    text = " | ".join(f"{k}: {v}" for k, v in lines)
    assert "Hooks land in the first line" in text and "{" not in text and "'" not in text


def test_the_page_says_plainly_that_it_cannot_reach_an_account(kit_client):
    client, _, _ = kit_client
    body = client.get("/agent").text
    assert "cannot post, schedule, follow, like, comment, message" in body
