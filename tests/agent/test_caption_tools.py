"""The two caption tools, run the way the command centre runs them.

The generator is proved in tests/captions and the page in tests/app. What is proved here is the
delivery through the agent: that a bare ask with no description refuses instead of writing a
stock post, that the tone she names is the tone she gets and a tone that does not exist says so
with the list, that the placement is taken from the composer when she does not name one, that
the number in the summary is the number of lines in the payload, and that the tag tool would
rather return an empty list than a hashtag nobody can point at.
"""

import datetime
import re

import pytest
from fastapi.testclient import TestClient

from src.agent import orchestrator, roster
from src.agent.tools import catalogue
from src.app import create_app
from src.config import Config
from src.metrics.ingest import MetricRow
from src.strategist.daily import subject_of

TODAY = datetime.date(2026, 11, 14)
SHOT = "mirror selfie in the black ribbed tank"
COMPLETE = {
    "hours_per_week": "6", "existing_followers": "0",
    "what_you_actually_film": "outfits in my room and the odd street clip",
    "gear": "phone", "has_clips": "on", "on_camera": "on",
    "platforms": ["tiktok", "reels"], "comfort": ["talking", "text on screen"],
}


@pytest.fixture
def alone(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "cap.sqlite3"))
    return client, client.app.state.kit


def with_voice(kit):
    client, k = kit
    k.db.save_voice(["wore the tank again lol", "nobody asked for this but ok #thrifted"])
    return client, k


def test_both_tools_have_a_desk_and_the_voice_desk_routes_them(alone):
    ids = {t["id"] for t in catalogue()}
    assert {"copy.tone", "copy.tags"} <= ids
    assert roster.route("give me a cunty caption for a mirror selfie").id == "voice"
    assert roster.route("what hashtags should i use on this").id == "voice"
    for tool_id in ("copy.tone", "copy.tags"):
        assert roster.owner(tool_id) == "The Voice"


def test_a_bare_ask_with_no_description_refuses_rather_than_writing_a_stock_post(alone):
    client, kit = alone
    out = orchestrator.execute(kit, "copy.tone", {})
    assert out.kind == "skipped", out.summary
    assert "no description of the frame" in out.summary
    assert "interview" in out.summary, "it has to say where the sentence could have come from"


def test_the_interviews_footage_line_is_used_when_she_only_asks_for_a_caption(alone):
    client, kit = alone
    client.post("/interview", data=COMPLETE)
    out = orchestrator.execute(kit, "copy.tone", {})
    assert out.kind == "advised", out.summary
    assert out.detail["subject"] == subject_of(kit.answers())


def test_the_lines_it_counts_are_the_lines_it_hands_back(alone):
    client, kit = with_voice(alone)
    out = orchestrator.execute(kit, "copy.tone", {"subject": SHOT})
    assert out.kind == "advised", out.summary
    cards = out.detail["cards"]
    assert len(cards) == 6, [c["name"] for c in cards]
    counted = sum(len(c["lines"]) for c in cards)
    for card in cards:
        assert card["tone"] and card["name"] and card["lines"]
        for line in card["lines"]:
            assert line["text"] and line["words"] == len(line["text"].split())
            assert line["why"], f"{card['tone']} handed back a line with no account for it"
    assert out.summary.startswith(f"{counted} line"), out.summary
    assert out.detail["where"] == "/captions"
    assert "in the casing your samples show" in out.summary


def test_the_tone_she_names_is_the_tone_she_gets_and_a_wrong_one_says_so(alone):
    client, kit = alone
    one = orchestrator.execute(kit, "copy.tone", {"subject": SHOT, "tone_id": "cunty"})
    assert one.kind == "advised" and len(one.detail["cards"]) == 1
    assert one.detail["cards"][0]["tone"] == "cunty"
    wrong = orchestrator.execute(kit, "copy.tone", {"subject": SHOT, "tone_id": "rude"})
    assert wrong.kind == "skipped", wrong.summary
    assert "cunty" in wrong.summary and "aesthetic" in wrong.summary


def test_a_video_ask_reports_the_media_it_wrote_for(alone):
    client, kit = alone
    out = orchestrator.execute(kit, "copy.tone", {"subject": SHOT, "platform": "tiktok",
                                                 "media": "story"})
    assert out.detail["media"] == "story" and out.detail["platform"] == "tiktok"
    assert out.detail["fills"]["thing"] == "black ribbed tank"
    assert out.detail["fills"]["form"] == "story"
    for card in out.detail["cards"]:
        for line in card["lines"]:
            assert not re.search(r"\bphoto\b", line["text"]), line["text"]
            assert line["words"] <= 16, line["text"]


def test_the_payload_carries_no_number_she_did_not_give(alone):
    client, kit = alone
    bare = orchestrator.execute(kit, "copy.tone", {"subject": "clips of the same latte"})
    assert bare.detail["fills"]["count"] == ""
    said = " ".join(line["text"] for c in bare.detail["cards"] for line in c["lines"])
    assert "tries" not in said, said
    three = orchestrator.execute(kit, "copy.tone", {"subject": "three clips of the same latte",
                                                    "tone_id": "lit"})
    assert three.detail["fills"]["count"] == "3", three.detail["fills"]
    counted = " ".join(line["text"] for c in three.detail["cards"] for line in c["lines"])
    assert set(re.findall(r"\b\d+\b", counted)) <= {"3"}, counted


def test_an_unlearned_voice_is_announced_in_the_summary_not_hidden(alone):
    client, kit = alone
    out = orchestrator.execute(kit, "copy.tone", {"subject": SHOT})
    assert "your voice is unlearned" in out.summary
    assert out.detail["voice"] == 0


def test_the_composer_decides_the_placement_when_she_does_not_name_one(alone):
    client, kit = alone
    kit.db.save_staged({"platform": "x", "caption": "the staged line"}, TODAY.isoformat())
    out = orchestrator.execute(kit, "copy.tone", {"subject": SHOT})
    assert out.detail["platform"] == "x", "a caption cut for the app she is already in"
    for card in out.detail["cards"]:
        for line in card["lines"]:
            assert line["words"] <= 11, line["text"]
    named = orchestrator.execute(kit, "copy.tone", {"subject": SHOT, "platform": "pinterest"})
    assert named.detail["platform"] == "pinterest", "what she says beats what is staged"


def test_tags_are_returned_with_the_evidence_that_put_them_there(alone):
    client, kit = with_voice(alone)
    kit.save_rows([MetricRow("instagram", f"i{i}", TODAY, 900, 900, 40.0, 9, 3, 2,
                             "outfit-and-style") for i in range(4)])
    out = orchestrator.execute(kit, "copy.tags", {"subject": SHOT, "platform": "instagram"})
    assert out.kind == "advised", out.summary
    assert out.detail["tags"][0]["source"] == "your numbers"
    for tag in out.detail["tags"]:
        assert tag["tag"].startswith("#") and tag["evidence"]
    assert len(out.detail["tags"]) <= 6
    assert out.detail["block"] == " ".join(t["tag"] for t in out.detail["tags"])
    assert "from your numbers" in out.summary
    assert out.detail["where"] == "/captions"


def test_one_platform_one_tag_and_the_limit_she_asks_for(alone):
    client, kit = with_voice(alone)
    out = orchestrator.execute(kit, "copy.tags", {"subject": SHOT, "platform": "x"})
    assert len(out.detail["tags"]) == 1, out.detail["tags"]
    five = orchestrator.execute(kit, "copy.tags", {"subject": SHOT, "platform": "instagram",
                                                   "limit": 2})
    assert len(five.detail["tags"]) == 2, five.detail["tags"]


def test_no_evidence_means_no_tags_rather_than_an_invented_one(alone):
    client, kit = alone
    out = orchestrator.execute(kit, "copy.tags", {})
    assert out.kind == "advised", out.summary
    assert out.detail["tags"] == []
    assert "invented" in out.summary
    assert len(out.detail["missing"]) == 3, out.detail["missing"]


def test_the_interviews_platforms_are_the_fallback_before_the_default(alone):
    client, kit = alone
    client.post("/interview", data=COMPLETE)
    out = orchestrator.execute(kit, "copy.tags", {"subject": "the new boots"})
    assert out.detail["platform"] == "tiktok", out.detail["platform"]
