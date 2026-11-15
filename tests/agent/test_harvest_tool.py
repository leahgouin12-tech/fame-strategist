"""The export harvest as the agent does it, which is the same staging the Writer page reads.

Two things are worth proving here rather than in the parser tests. The first is that the tool
stops at the list: an agent that decided a caption was hers without asking is the exact failure
this feature exists to avoid, so `get_voice()` has to still be empty after a green run. The
second is that the two entry points share one contract - a batch staged by way of the inbox
appears on `/write` for her tick, with no second copy of the truth anywhere.
"""

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.agent import orchestrator, roster
from src.agent.tools import catalogue
from src.app import create_app
from src.config import Config
from src.captions import harvest

MINE = ["wore the tank again lol", "nobody asked for this but ok #thrifted",
        "wait why is the lighting like this"]
THEIRS = "you look great!! omg"


def export_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("captions.json", json.dumps(
            {"mediaList": [{"caption": MINE[0], "comments": [{"text": THEIRS}]},
                          {"caption": MINE[1]}, {"description": MINE[2]}]}))
    return buf.getvalue()


@pytest.fixture
def world(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "agent.sqlite3"))
    return client, client.app.state.kit


def drop(kit, name="captions.zip", data=None):
    Path(kit.paths["inbox"]).mkdir(parents=True, exist_ok=True)
    (Path(kit.paths["inbox"]) / name).write_bytes(data if data is not None else export_bytes())


def test_the_tool_has_a_desk_and_the_voice_desk_answers_it(world):
    assert "voice.harvest" in {t["id"] for t in catalogue()}
    assert roster.owner("voice.harvest") == "The Voice"
    assert roster.route("learn my voice from the export i downloaded").id == "voice"
    assert roster.route("make the captions sound like me").id == "voice"


def test_with_nothing_in_the_inbox_it_says_where_to_put_the_file(world):
    client, kit = world
    out = orchestrator.execute(kit, "voice.harvest", {})
    assert out.kind == "skipped", out.summary
    assert "data/inbox" in out.summary
    assert kit.db.get_voice() == []


def test_a_green_run_stages_the_lines_and_remembers_nothing(world):
    client, kit = world
    drop(kit)
    out = orchestrator.execute(kit, "voice.harvest", {})
    assert out.kind == "did", out.summary
    assert out.detail["lines"] == 3 and out.detail["file"] == "captions.zip"
    assert "staged, not learned" in out.summary
    assert kit.db.get_voice() == [], "the agent decided for her"
    assert THEIRS not in json.dumps(harvest.staged(kit.paths["root"]), ensure_ascii=False)
    assert THEIRS not in "".join(s["text"] for s in harvest.staged(kit.paths["root"])["lines"])


def test_what_the_agent_staged_is_the_list_the_writer_page_shows(world):
    client, kit = world
    drop(kit)
    orchestrator.execute(kit, "voice.harvest", {})
    body = client.get("/write").text
    for line in MINE:
        assert line in body, line
    keep = client.post("/write/harvest/keep", data={"keep": ["0"]}, follow_redirects=False)
    assert keep.status_code == 303
    assert kit.db.get_voice() == [MINE[0]]


def test_a_stray_json_with_no_captions_does_not_hide_her_export(world):
    """The inbox holds her pictures and whatever the app wrote beside them. A sidecar file that
    happens to end in .json must not become the reason the export is reported as unreadable."""
    client, kit = world
    (Path(kit.paths["inbox"]) / "layers.json").write_text(json.dumps({"note": "a sidecar"}),
                                                          encoding="utf-8")
    drop(kit, name="instagram-export.zip")
    out = orchestrator.execute(kit, "voice.harvest", {})
    assert out.kind == "did", out.summary
    assert out.detail["file"] == "instagram-export.zip"


def test_naming_a_file_that_is_not_there_shows_what_it_can_see(world):
    client, kit = world
    drop(kit)
    out = orchestrator.execute(kit, "voice.harvest", {"name": "other-thing.zip"})
    assert out.kind == "skipped", out.summary
    assert "captions.zip" in out.summary, "it should say what is actually in the folder"


def test_an_export_of_nothing_hers_says_so_and_leaves_the_profile_alone(world):
    client, kit = world
    drop(kit, name="followers.json",
         data=json.dumps({"followers": [{"name": "kyle"}]}).encode())
    out = orchestrator.execute(kit, "voice.harvest", {})
    assert out.kind == "skipped", out.summary
    assert "caption" in out.summary.lower()
    assert kit.db.get_voice() == []
    assert harvest.staged(kit.paths["root"]) is None
