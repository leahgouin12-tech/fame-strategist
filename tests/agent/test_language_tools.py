"""The two Multilingual tools, run the way the command centre runs them.

tests/language proves the module and tests/app proves the page. What is proved here is delivery
through the agent, which is where a fake translation would do the most damage: that a desk owns
both tools and a sentence about a second language reaches that desk, that an ask with no caption
anywhere and no language picked refuses instead of inventing either one, that with no model
connected the answer is an advisory carrying the brief and never a `did`, that a model that does
answer has every version checked and every failure still listed, that her saved defaults and her
keep-words reach the prompt, and that the check tool says plainly that a clean report is a
comparison with her line rather than a native reader's opinion.
"""

import datetime

import pytest
from fastapi.testclient import TestClient

from src.agent import orchestrator, roster
from src.agent.tools import catalogue
from src.app import create_app
from src.config import Config
from src.engines.base import Engine
from src.language import localise

TODAY = datetime.date(2026, 11, 14)
LINE = "thrifted fits all week, all in the same bag #thriftflip"
ES = "los outfits que me puse esta semana, todos con la misma bolsa para el #thriftflip"
ES_REWORDED = "todos mis outfits de esta semana salieron de la misma bolsa #thriftflip"
LOST = "los outfits de esta semana, todos en la misma bolsa"


@pytest.fixture
def alone(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "lang-agent.sqlite3"))
    return client, client.app.state.kit


class Fake(Engine):
    """A model that answers in shape, so the tool has something to check rather than nothing."""

    name = "fake-model"

    def __init__(self, versions):
        self.versions = versions
        self.asked = []

    def complete_json(self, system, user, schema, images=None):
        self.asked.append((system, user, schema))
        return self.check({"versions": self.versions}, schema)


def connect(kit, versions):
    fake = Fake(versions)
    kit.engine.engine = fake
    return fake


def stage(kit, **over):
    fields = dict(platform="tiktok", caption=LINE, hashtags=["#thriftflip"],
                  alt="", lines="", music="", source="a.jpg", file="outputs/a.mp4")
    fields.update(over)
    kit.db.save_staged(fields, TODAY.isoformat())


def run(kit, tool="lang.localise", **args):
    return orchestrator.execute(kit, tool, args)


def test_both_tools_are_staffed_on_a_desk_a_language_ask_reaches(alone):
    client, kit = alone
    ids = {t["id"] for t in catalogue()}
    assert {"lang.localise", "lang.check"} <= ids
    for tool in ("lang.localise", "lang.check"):
        assert roster.owner(tool) == "The Translator", tool
    for asked in ("put this in spanish too", "i want a french version",
                  "check the kreyol against my line", "translate the caption"):
        assert roster.route(asked).id == "translator", asked


def test_no_line_typed_and_nothing_staged_refuses_rather_than_inventing_a_caption(alone):
    client, kit = alone
    out = run(kit, codes="es")
    assert out.kind == "skipped", out.summary
    assert "no caption to carry" in out.summary
    assert "composer" in out.summary, "it has to say where a line could have come from"


def test_the_composer_line_is_carried_when_she_names_no_text(alone):
    client, kit = alone
    stage(kit)
    out = run(kit, codes="es")
    assert out.detail["source"] == LINE, "the staged line is hers, so it is the one carried"
    assert out.detail["platform"] == "tiktok"


def test_no_language_picked_lists_the_ones_she_can_choose(alone):
    """Refusing to pick her audience is the point: defaulting to Spanish would put words in a
    language she does not post in, on a page that claims to only carry what she asked for."""
    client, kit = alone
    stage(kit)
    out = run(kit, codes="")
    assert out.kind == "skipped", out.summary
    assert "will not choose your audience" in out.summary
    for code in ("es", "fr", "ht", "pt"):
        assert f"{code} (" in out.summary, code
    assert "(Spanish)" in out.summary and "(Haitian Creole)" in out.summary


def test_her_saved_defaults_are_used_when_this_ask_names_nobody(alone):
    client, kit = alone
    stage(kit)
    kit.db.save_language({"targets": ["es", "ht"], "keep": ""})
    fake = connect(kit, [{"text": ES_REWORDED, "note": ""}])
    out = run(kit, codes="")
    assert len(fake.asked) == 2, "one call per saved language, not one per language in the app"
    assert "es" in out.summary and "ht" in out.summary, out.summary


def test_with_no_model_connected_it_advises_with_the_brief_and_never_claims_it_ran(alone):
    client, kit = alone
    stage(kit)
    out = run(kit, codes="es")
    assert out.kind == "advised", out.summary
    assert out.kind != "did", "an app with no dictionary has written no sentence in Spanish"
    assert "Nothing was written in another language." in out.summary
    assert "No model is connected" in out.summary
    assert "versions" not in out.detail, "nothing to show off as a version"
    brief = out.detail["briefs"][0]
    assert brief["language"] == "es" and brief["words"] == 30, brief
    assert "#thriftflip" in brief["locked"], brief
    assert out.detail["where"] == "/languages", "her report has to point at the page"


def test_a_model_that_answers_has_every_version_checked_and_every_failure_still_listed(alone):
    client, kit = alone
    stage(kit)
    connect(kit, [{"text": ES, "note": "kept the tag"}, {"text": LOST, "note": "tightened it"}])
    out = run(kit, codes="es")
    assert out.kind == "advised", out.summary
    assert out.detail["said_by"] == "fake-model"
    flags = [(v["language"], v["ok"]) for v in out.detail["versions"]]
    assert flags == [("es", True), ("es", False)], flags
    broken = out.detail["versions"][1]
    assert "#thriftflip is gone" in broken["problems"], broken
    assert "1 of 2 versions passed the check against your line" in out.summary, out.summary
    assert "listed with it" in out.summary, "the failure is reported, not quietly dropped"


def test_the_keep_words_she_filed_reach_the_prompt_and_the_check(alone):
    client, kit = alone
    stage(kit)
    kit.db.save_language({"targets": ["es"], "keep": "GlucoLove AMA"})
    fake = connect(kit, [{"text": ES, "note": ""}])
    out = run(kit, codes="es")
    system, user, _ = fake.asked[0]
    assert "Keep these exactly as written: #thriftflip, GlucoLove, AMA." in system, system
    assert "Words she said not to translate: GlucoLove AMA." in user, user
    problems = out.detail["versions"][0]["problems"]
    assert problems == ["GlucoLove is gone", "AMA is gone"], problems
    assert out.detail["versions"][0]["ok"] is False


def test_the_word_budget_the_prompt_gives_is_the_one_the_check_uses(alone):
    """A version told to fit 12 words and then cut against 22 is the app failing its own arithmetic
    and charging her for it, so the number in the instruction and the number in the verdict match."""
    client, kit = alone
    stage(kit, platform="x")
    fake = connect(kit, [{"text": ES, "note": ""}])
    out = run(kit, codes="es", media="video")
    budget = localise.budget_for("x", "es", "video")
    assert budget == 12
    assert f"Fit inside {budget} words" in fake.asked[0][0], fake.asked[0][0]
    version = out.detail["versions"][0]
    assert version["words"] == len(ES.split()) == 15
    assert version["problems"] == [f"it is 15 words against the {budget} this page allows for a "
                                   "Spanish line here"], version
    assert out.summary.startswith("0 of 1 versions passed the check"), out.summary


def test_the_placement_she_names_beats_the_composer_and_the_one_she_does_not_is_taken_from_it(
        alone):
    """Platform comes from the staged post when she does not name it, because that is the app she
    is already in. The kind does not: nothing on the staged post says whether it is a story, so
    the tool uses the one kind the page and the tool agree on and reports it back."""
    client, kit = alone
    stage(kit, platform="x")
    out = run(kit, codes="es")
    assert out.detail["platform"] == "x" and out.detail["media"] == "photo", out.detail
    assert out.detail["briefs"][0]["words"] == localise.budget_for("x", "es", "photo")
    named = run(kit, codes="es", platform="tiktok", media="video")
    assert named.detail["platform"] == "tiktok" and named.detail["media"] == "video"
    assert named.detail["briefs"][0]["words"] == 22, named.detail["briefs"][0]


def test_the_check_needs_both_halves_and_says_which_one_is_missing(alone):
    client, kit = alone
    out = run(kit, "lang.check", version=ES)
    assert out.kind == "skipped" and "no line of yours" in out.summary, out.summary
    stage(kit)
    out = run(kit, "lang.check", text=LINE)
    assert out.kind == "skipped" and "no version was given" in out.summary, out.summary


def test_a_clean_version_is_reported_as_a_comparison_not_a_native_verdict(alone):
    client, kit = alone
    out = run(kit, "lang.check", text=LINE, version=ES_REWORDED, code="es",
              platform="tiktok", media="photo")
    assert out.kind == "advised", out.summary
    assert "Nothing to report" in out.summary
    assert "a Spanish photo on tiktok" in out.summary, out.summary
    assert "not a native reader's opinion" in out.summary
    assert out.detail["language"] == "es"
    assert out.detail["budget"] == 30 and out.detail["words"] == len(ES_REWORDED.split())


def test_the_language_is_read_off_her_line_when_she_does_not_name_one(alone):
    """She pasted two strings and no code. The line she gave is Spanish, so the budget is the
    Spanish one; had this app assumed English the same version would be judged against 16 words."""
    client, kit = alone
    found = run(kit, "lang.check", text=ES, version=ES_REWORDED, platform="tiktok")
    assert found.detail["language"] == "es", found.detail
    assert found.detail["budget"] == 30
    assumed = run(kit, "lang.check", text=LINE, version=ES_REWORDED, platform="tiktok")
    assert assumed.detail["language"] == "", "an English line names no target language"
    assert assumed.detail["budget"] == 22, "the English budget, with no language invented for it"


def test_a_version_that_kept_everything_but_ran_long_is_reported_by_the_numbers(alone):
    client, kit = alone
    long_one = ES_REWORDED + " y otra vez y otra vez y otra vez y otra vez"
    assert len(long_one.split()) == 24
    out = run(kit, "lang.check", text=LINE, version=long_one, code="es",
              platform="tiktok", media="video")
    assert "it is 24 words against the 22" in out.summary, out.summary
    assert "1 thing to look at" in out.summary, out.summary
    assert "#thriftflip is gone" not in out.summary, "the tag is in it; length is the only claim"
    assert out.detail["budget"] == 22 and out.detail["words"] == 24, out.detail


def test_naming_the_desk_under_researcher_refuses_the_writing_and_stops_at_the_reading(alone):
    """Researcher is allowed to compare two strings and not allowed to make an asset, so one step
    is refused outright and the other is recorded as planned-not-run rather than silently run."""
    client, kit = alone
    stage(kit)
    client.post("/agent/run", data={"asked": "", "mode": "researcher", "desk": "translator"})
    steps = {s["tool"]: s for s in kit.db.recent_runs(1)[0]["steps"]}
    assert set(steps) == {"lang.localise", "lang.check"}
    assert steps["lang.localise"]["kind"] == "skipped", steps["lang.localise"]
    assert "Researcher does not reach for" in steps["lang.localise"]["summary"]
    assert steps["lang.check"]["kind"] == "advised", steps["lang.check"]
    assert "until you press it" in steps["lang.check"]["summary"]
