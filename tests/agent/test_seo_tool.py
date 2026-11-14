"""The discoverability tool, run the way the command centre runs it.

tests/seo proves the module and tests/app proves the page. What is proved here is the delivery
through the agent: that a bare ask with no post anywhere refuses rather than reading an invented
post, that the phrases it checks against carry her own evidence and none are made up when the file
is empty, that the staged post is read when she names no text and the text she pastes beats it,
that the platform comes from the composer rather than a guess, that the numbers in the summary are
the counts in the payload, and that what this app cannot know travels in the answer instead of
being quietly dropped.
"""

import datetime

import pytest
from fastapi.testclient import TestClient

from src.agent import orchestrator, roster
from src.agent.tools import catalogue
from src.app import create_app
from src.config import Config
from src.metrics.ingest import MetricRow

TODAY = datetime.date(2026, 11, 14)
CAPTION = "thrifted tank again, worn to six places"
TAGS = ["#thrifted", "#outfitandstyle"]


@pytest.fixture
def alone(tmp_path):
    app = create_app(Config(api_key=None, engine_name="offline", model=""),
                     tmp_path / "seo-agent.sqlite3")
    client = TestClient(app)
    return client, client.app.state.kit


def stage(kit, **over):
    fields = dict(platform="tiktok", caption=CAPTION, hashtags=TAGS,
                  alt="a person in a worn thrifted tank top")
    fields.update(over)
    kit.db.save_staged(fields, TODAY.isoformat())


def posts(kit, count=4, hypothesis="outfit-and-style"):
    kit.save_rows([MetricRow("tiktok", f"t{i}", TODAY, 900, 900, 40.0, 9, 3, 2,
                             hypothesis) for i in range(count)])


def run(kit, **args):
    return orchestrator.execute(kit, "seo.audit", args)


def test_the_tool_has_a_desk_and_the_desk_answers_a_searchable_ask(alone):
    client, kit = alone
    assert "seo.audit" in {t["id"] for t in catalogue()}
    assert roster.owner("seo.audit") == "The Signpost"
    for asked in ("is this caption searchable", "what should i put in the alt text",
                  "am i getting found on search"):
        assert roster.route(asked).id == "seo", asked


def test_a_bare_ask_with_no_post_anywhere_refuses_rather_than_reading_an_invented_one(alone):
    client, kit = alone
    out = run(kit)
    assert out.kind == "skipped", out.summary
    assert "no post to read" in out.summary
    assert "composer" in out.summary, "it has to say where a post could have come from"


def test_with_nothing_on_file_it_checks_no_phrase_it_cannot_point_at(alone):
    client, kit = alone
    stage(kit)
    out = run(kit)
    assert out.kind == "advised", out.summary
    assert out.detail["terms"] == [], "a keyword this app did not earn is a made-up keyword"
    assert out.detail["carried"] == [] and out.detail["front"] == []


def test_the_hypothesis_on_her_imported_posts_is_a_phrase_with_its_evidence_attached(alone):
    client, kit = alone
    stage(kit)
    posts(kit, 4)
    out = run(kit)
    first = out.detail["terms"][0]
    assert first["phrase"] == "outfit and style"
    assert first["source"] == "your posts"
    assert "4 of your posts ran under 'outfit-and-style'" in first["evidence"], first
    assert "median 900 views" in first["evidence"], first


def test_the_staged_post_is_read_when_she_names_no_text_and_the_read_says_so(alone):
    client, kit = alone
    stage(kit)
    posts(kit)
    out = run(kit)
    assert out.detail["checked_from"] == "the post staged in the composer"
    assert "the post staged in the composer" in out.summary
    assert out.detail["alt"] == "a person in a worn thrifted tank top"


def test_the_text_she_gives_beats_whatever_the_composer_is_holding(alone):
    client, kit = alone
    stage(kit)
    posts(kit)
    out = run(kit, text="the latte art is the post today #latteart", platform="instagram")
    assert out.detail["checked_from"] == "the text you gave"
    assert out.detail["platform"] == "instagram", "what she says beats what is staged"
    assert all("thrifted tank" not in c["phrase"] for c in out.detail["carried"])


def test_the_platform_comes_from_the_composer_when_she_does_not_name_one(alone):
    client, kit = alone
    stage(kit, platform="x")
    posts(kit)
    out = run(kit, text=CAPTION + " #thrifted")
    assert out.detail["platform"] == "x", "a read cut for the app she is already in"


def test_the_counts_in_the_summary_are_the_counts_in_the_payload(alone):
    client, kit = alone
    stage(kit)
    posts(kit)
    out = run(kit)
    got = out.detail
    assert out.summary.startswith(
        f"Read the post staged in the composer against the {len(got['terms'])} "
        f"phrase{'' if len(got['terms']) == 1 else 's'} this app can account for: "
        f"{len(got['carried'])} on it, {len(got['missed'])} not, {len(got['front'])} in front "
        "of the fold."), out.summary
    assert {f["check"] for f in got["checks"]} <= {"words a search could land on",
                                                   "said before the fold", "alt field",
                                                   "caption length", "text on the post"}
    assert all(f["line"] for f in got["checks"]), "a check with no sentence is a silent check"


def test_a_phrase_that_only_lives_in_a_tag_is_not_reported_as_said_before_the_fold(alone):
    client, kit = alone
    kit.db.save_voice(["thrifted and proud", "still the thrifted tank", "a latte this morning"])
    out = run(kit, text="worn to six places this week #thrifted")
    got = out.detail
    assert "thrifted" in [t["phrase"] for t in got["terms"]], got["terms"]
    assert got["front"] == [] and got["late"] == [], got
    assert "thrifted" in got["tag_only"], got
    fold = [f for f in got["checks"] if f["check"] == "said before the fold"][0]
    assert fold["verdict"] == "weak", fold
    assert "not only inside a tag" in fold["fix"], fold


def test_what_this_app_cannot_know_travels_in_the_answer_instead_of_being_dropped(alone):
    client, kit = alone
    stage(kit)
    posts(kit)
    out = run(kit)
    cannot = " ".join(out.detail["cannot"])
    for line in ("volume", "indexed", "sits for any phrase", "not theirs", "exports"):
        assert line in cannot, line
    assert out.detail["where"] == "/seo", "the answer has to point at the page that shows it"


def test_no_number_that_looks_like_a_search_volume_can_reach_the_summary(alone):
    client, kit = alone
    stage(kit)
    posts(kit)
    out = run(kit)
    assert "volume" not in out.summary, out.summary
    assert "rank" not in out.summary, out.summary
    assert not any(k in out.detail for k in ("volume", "searchVolume", "rank", "position")), list(
        out.detail)


def test_the_rules_it_quotes_are_the_sourced_ones_and_folklore_stays_out(alone):
    client, kit = alone
    stage(kit)
    posts(kit)
    out = run(kit)
    for rule in out.detail["rules"]:
        assert rule["confidence"] in ("proven", "strong", "contested"), rule
        assert rule["does_not_claim"], rule
        assert rule["source"]
    assert out.detail["why_short"], "a short phrase list has to be explained, not just shown"
