"""The two collaboration tools, run the way the command centre runs them.

tests/collab proves the module and tests/app proves the page. What is proved here is delivery
through the agent: that both tools have a desk and that a sentence about collaboration reaches
that desk, that an app with no import and no list says so rather than producing a shortlist of
strangers, that a pitch for a name already filed is built out of what she filed and a pitch for a
name nobody filed without a reason is refused, that what she says now beats what was stored, that
the counts in the sentence are the counts in the payload, and that no step this desk records is
ever a `did` - because the only thing it can do is hand her the copy and the count.
"""

import datetime

import pytest
from fastapi.testclient import TestClient

from src.agent import orchestrator, roster
from src.agent.tools import catalogue
from src.app import create_app
from src.collab import store as collab_store
from src.config import Config
from src.metrics.ingest import MetricRow

TODAY = datetime.date(2026, 11, 14)
NAME = "@laurenmakesthefits"
WHY = "she answered a small account's comment with a 90-second tutorial"
ASK = "a swap, one cut each"


@pytest.fixture
def alone(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "collab-agent.sqlite3"))
    return client, client.app.state.kit


def posts(kit, **by_platform):
    """One save, the way the Numbers page leaves it: every platform in the same import, because
    a second save replaces the file rather than appending to it."""
    rows = [MetricRow(platform, f"{platform}{n}", TODAY, v, v, 40.0, 9, 3, 2)
            for platform, views in by_platform.items() for n, v in enumerate(views)]
    kit.save_rows(rows)


def file(kit, name=NAME, why=WHY, ask=ASK, fmt="one reel each", platform="tiktok"):
    ident, _ = collab_store.add(kit.db, {"name": name, "why": why, "ask": ask, "format": fmt,
                                         "platform": platform}, TODAY.isoformat())
    return ident


def run(kit, tool="collab.offer", **args):
    return orchestrator.execute(kit, tool, args)


def test_both_tools_are_staffed_on_a_desk_a_collaboration_ask_reaches(alone):
    client, kit = alone
    ids = {t["id"] for t in catalogue()}
    assert {"collab.offer", "collab.pitch"} <= ids
    for tool in ("collab.offer", "collab.pitch"):
        assert roster.owner(tool) == "The Broker", tool
    for asked in ("who should i pitch", "what can i offer in a pitch",
                  "should i do a collab with the vintage girl",
                  "is there a swap worth asking for"):
        assert roster.route(asked).id == "collab", asked


def test_with_nothing_on_file_it_says_so_instead_of_shortlisting_strangers(alone):
    client, kit = alone
    out = run(kit)
    assert out.kind == "advised", out.summary
    assert "Nothing has been imported" in out.summary
    assert "Nobody is on the list yet" in out.summary
    assert "find names" in out.summary, "an empty shortlist has to explain why it is empty"
    assert out.detail["offers"] == [] and out.detail["list"] == []
    assert out.detail["funnel"]["asked"] == 0
    assert len(out.detail["cannot"]) == 4, "the limits travel with the answer"


def test_the_numbers_it_quotes_are_hers_and_a_one_post_platform_is_named(alone):
    client, kit = alone
    posts(kit, tiktok=(1000, 2000, 3000, 4000), reels=(900,))
    out = run(kit)
    assert "2 platforms to quote from" in out.summary
    assert "tiktok (4 posts, median 2,500 views)" in out.summary
    assert out.detail["thin"] == ["reels"], "one afternoon is not a rate and it says which"
    assert out.detail["floor"] == 2


def test_the_list_it_reports_is_the_one_she_filled_in(alone):
    client, kit = alone
    ident = file(kit)
    kit.db.move_collab(ident, "replied", TODAY.isoformat())
    out = run(kit)
    assert f"on your list: {NAME}" in out.summary
    assert out.detail["list"][0]["status"] == "replied"
    assert out.detail["funnel"]["answered"] == 1
    assert "not a rate yet" in out.summary, "one ask is repeated as what it is, not rounded up"


def test_no_name_and_an_empty_list_refuse_with_the_words_she_needs(alone):
    client, kit = alone
    out = run(kit, "collab.pitch")
    assert out.kind == "skipped", out.summary
    assert "no name to write it for" in out.summary
    assert "the list is empty" in out.summary


def test_no_name_with_a_list_shows_her_what_she_could_have_asked_for(alone):
    client, kit = alone
    file(kit)
    out = run(kit, "collab.pitch")
    assert out.kind == "skipped"
    assert NAME in out.summary, "the refusal names what is already on the list"


def test_an_unfiled_name_with_no_reason_gets_a_refusal_not_an_invented_compliment(alone):
    client, kit = alone
    out = run(kit, "collab.pitch", name="@astranger")
    assert out.kind == "skipped", "a guessed compliment is a line she would have to send"
    assert "@astranger is not on the list" in out.summary
    assert "you would have to send" in out.summary
    assert "put them on the list first" in out.summary, "and it says what would unblock it"
    assert out.detail == {}, "a refusal carries no pitch payload"


def test_a_name_already_on_the_list_needs_nothing_more_than_the_name(alone):
    client, kit = alone
    file(kit)
    posts(kit, tiktok=(1000, 2000, 3000, 4000))
    out = run(kit, "collab.pitch", name=NAME)
    assert out.kind == "advised", out.summary
    assert out.detail["from_list"] is True
    assert out.detail["lines"][0] == f"Here is the specific thing: {WHY}", "her words came back"
    assert "led by your own numbers" in out.summary
    assert out.detail["platform"] == "tiktok", "the platform she filed it under"
    assert out.detail["held"] == [], "a filed reason, ask, shape and four posts leave nothing out"


def test_what_she_says_now_beats_what_was_filed(alone):
    client, kit = alone
    file(kit)
    posts(kit, tiktok=(1000, 2000, 3000, 4000))
    out = run(kit, "collab.pitch", name=NAME, why="their fitting room series is the only one i "
                                                 "wait for", ask="a two-part split",
                shape="one 30s each")
    joined = " ".join(out.detail["lines"])
    assert "their fitting room series" in joined
    assert WHY not in joined, "the stored reason is the fallback, not the answer"
    assert "a two-part split - one 30s each" in joined


def test_a_pitch_with_no_import_counts_its_held_back_lines_in_the_sentence(alone):
    client, kit = alone
    out = run(kit, "collab.pitch", name="@anyone", why="they reply to every comment")
    held = out.detail["held"]
    assert "with no number in it" in out.summary
    assert any(h.startswith("no number") for h in held), held
    assert f"{len(held)} thing{'s' if len(held) != 1 else ''} held back" in out.summary


def test_the_copy_comes_back_as_text_she_can_paste(alone):
    client, kit = alone
    out = run(kit, "collab.pitch", name="@anyone", why="they reply to every comment",
              ask="a swap, one cut each")
    assert out.detail["text"] == "\n".join(out.detail["lines"])
    assert out.detail["pitch"]["text"] == out.detail["text"]


def test_nothing_this_desk_reaches_for_is_ever_reported_as_done(alone):
    client, kit = alone
    file(kit)
    posts(kit, tiktok=(1000, 2000, 3000, 4000))
    for tool in ("collab.offer", "collab.pitch"):
        out = run(kit, tool, name=NAME)
        assert out.kind in ("advised", "skipped"), f"{tool} claimed to have finished something"
        if out.kind == "advised":
            assert out.detail["where"] == "/collab", "and it points at the page instead"
    for claim in ("sent", "contacted", "reached out", "followed", "dm'd"):
        assert claim not in run(kit, "collab.pitch", name=NAME).summary.lower(), claim


def test_naming_the_broker_runs_its_own_bench_and_records_both_outcomes(alone):
    """The desk has to be reachable from the command centre, not only from the page."""
    client, kit = alone
    client.post("/collab/add", data={"name": NAME, "why": WHY, "ask": ASK,
                                     "format": "one reel each", "platform": "tiktok"})
    client.post("/agent/run", data={"asked": "", "mode": "operator", "desk": "collab"})
    run = kit.db.recent_runs(1)[0]
    assert run["planner"] == "The Broker (you named the desk)", run["planner"]
    assert {s["tool"] for s in run["steps"]} == set(roster.by_id("collab").tools)
    for step in run["steps"]:
        assert step["kind"] != "failed", step
        assert step["kind"] != "did", f"{step['tool']} reported finishing a message"
        assert step["summary"].strip(), f"{step['tool']} ran without saying anything"
