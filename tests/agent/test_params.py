"""The sentence is allowed to change the run.

Seventeen of the twenty-nine tools in the registry declare arguments, and until `src/agent/params.py`
existed every one of them was deaf: `rule_plan` handed the chain `{"tool": id, "args": {}}` and
`model_plan` read only the `tool` key out of the model's answer and threw the `args` away. So "put
this in spanish and do not translate GlucoLove" ran The Translator on whatever was last ticked on the
Languages page, and "give me 5 cunty ones for tiktok" ran the Writer on saved defaults. A command
centre that cannot hear the command is a row of buttons.

What is proved here, in that order: that a value only arrives from a word that *names* it; that her
casing survives the trip, because a locked token that gets lower-cased is a token the check will
then fail her for; that the counts she did not give, the day she did not name and the subject she
did not quote stay absent so the tool's own fallback and its own refusal still run; that what she
typed outranks what a planner read into it; and that the whole thing is wired - the recorded step for
a real ask carries the arguments the tool actually received.

`NOT_FROM_A_SENTENCE` is checked against the live registry on purpose. An argument someone adds
later has to be either extracted or refused in writing, not quietly ignored for a year.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from src import accounts
from src.agent import modes, orchestrator, params
from src.agent.tools import REGISTRY
from src.app import create_app
from src.config import Config

LINE = "thrifted fits all week, all in the same bag #thriftflip"
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def heard(asked: str, tool_id: str) -> dict:
    """What this sentence would say to one tool, in the shape the loop uses."""
    return params.fill(REGISTRY[tool_id], {}, asked)


@pytest.fixture
def world(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "params.sqlite3"))
    return client


def stage(client):
    client.app.state.db.save_staged(accounts.build(
        "tiktok", "Video post", caption=LINE, hashtags=["#thriftflip"], alt="", lines="",
        music="", source="a.jpg", file="outputs/a.mp4").as_dict(), "2026-11-14")


def run(client, asked, mode="operator"):
    client.post("/agent/run", data={"asked": asked, "mode": mode})
    return client.app.state.db.recent_runs(1)[0]


def step_of(run_record, tool_id):
    for step in run_record["steps"]:
        if step["tool"] == tool_id:
            return step
    raise AssertionError(f"{tool_id} was not in {[s['tool'] for s in run_record['steps']]}")


# -------------------------------------------------------------------------- naming a value

def test_a_language_she_says_becomes_the_language_the_tool_is_handed():
    assert heard("put this in spanish too", "lang.localise") == {"codes": "es"}
    assert heard("i want a french and portuguese version", "lang.localise") == {"codes": "fr pt"}
    assert heard("does the kreyol keep my tag", "lang.localise") == {"codes": "ht"}


def test_an_accented_endonym_answers_to_the_typing_a_phone_gives_her():
    """Kreyòl is stored with the accent. On a phone she writes kreyol, and a command centre that
    only matches the accented spelling is refusing her because of her keyboard."""
    assert heard("do the Kreyòl one", "lang.localise") == {"codes": "ht"}
    assert heard("do the kreyol one", "lang.localise") == {"codes": "ht"}
    assert heard("the creole version", "lang.localise") == {"codes": "ht"}


def test_two_languages_come_out_in_the_order_she_named_them():
    assert heard("french first then spanish", "lang.localise") == {"codes": "fr es"}


def test_a_sentence_that_names_no_language_names_no_language():
    """Absent is the whole feature: with nothing typed the tool falls back to her saved defaults,
    and if she never saved any it refuses. A finder that guessed would post to an audience she
    never picked."""
    assert heard("translate the caption for me", "lang.localise") == {}
    assert heard("make it shorter", "lang.localise") == {}


def test_her_keep_words_arrive_with_her_casing_intact():
    """The check fails a version for changing the casing of a locked token, so a finder that
    lower-cased GlucoLove on the way through would hand the model a word she never wrote."""
    assert heard("put it in spanish, do not translate GlucoLove", "lang.localise")["keep"] == \
        "GlucoLove"
    assert heard("dont translate #thriftflip and mi AMA", "lang.localise")["keep"] == \
        "#thriftflip mi AMA"
    assert heard("leave mi AMA alone", "lang.localise")["keep"] == "mi AMA"
    assert heard("translate everything but GlucoLove", "lang.localise")["keep"] == "GlucoLove"


def test_asking_for_the_hashtags_to_survive_is_not_a_keep_list():
    """Her locked tokens are already scanned off her own line. "keep the hashtags" names nothing
    new, and inventing one would put a word on the brief that she never said to protect."""
    assert "keep" not in heard("keep the hashtags in it", "lang.localise")
    assert "keep" not in heard("put this in spanish", "lang.localise")


def test_the_platform_she_names_is_the_platform_that_runs():
    assert heard("do this for tiktok", "copy.tags") == {"platform": "tiktok"}
    assert heard("would this work on ig", "copy.packs") == {"platform": "instagram"}
    assert heard("is it too long for twitter", "copy.tags") == {"platform": "x"}
    assert heard("post it on youtube shorts", "copy.tags") == {"platform": "youtube"}


def test_a_letter_x_inside_a_word_is_not_the_platform_x():
    assert heard("make my excel sheet look better", "copy.tags") == {}
    assert heard("xoxo that is so aesthetic", "copy.tone") == {"tone_id": "aesthetic"}
    assert heard("should i post it on x", "copy.tags") == {"platform": "x"}


def test_a_ratio_is_not_a_count_of_anything():
    assert heard("crop it 9:16 and give me 5 tags", "copy.tags") == {"limit": 5}
    assert heard("9:16 for the video", "lang.localise") == {"media": "video"}
    assert heard("give me 5 hashtags", "copy.tags") == {"limit": 5}
    assert heard("top three niches", "strategy.niches") == {"limit": 3}
    assert heard("about twelve cuts", "repurpose.cuts") == {"limit": 12}


def test_a_count_bigger_than_anything_this_app_hands_out_is_left_alone():
    """Refusing to invent is better than passing 40 to a tool that would answer with whatever it
    has: the tool's own default stays in charge and its own message stays true."""
    assert heard("give me 40 hashtags", "copy.tags") == {}
    assert "limit" not in heard("how many tags should i use", "copy.tags")


def test_photo_and_video_come_from_the_words_she_used_not_from_the_file_extension():
    assert heard("caption for this selfie", "copy.tone") == {"media": "photo"}
    assert heard("caption for the clip", "copy.tone") == {"media": "video"}
    assert heard("the video, not the photo", "lang.localise")["media"] == "video"


def test_a_quoted_line_is_the_text_and_only_a_quoted_line_is():
    """She can paste the line into the command itself. Apostrophes are out of bounds: she writes
    don't and idc inside single quotes every day, so only double quotes count as quoting."""
    assert heard('check "los outfits de esta semana" against my line',
                 "lang.check")["text"] == "los outfits de esta semana"
    assert heard('translate "thrifted fits, all in the same bag" into spanish',
                 "lang.localise")["text"] == "thrifted fits, all in the same bag"
    assert heard("check the spanish against my line", "lang.check") == {"code": "es"}


def test_a_tone_and_a_look_are_named_or_not_at_all():
    assert heard("give me the cunty ones", "copy.tone") == {"tone_id": "cunty"}
    assert heard("make it aesthetic for a selfie", "copy.tone") == {"tone_id": "aesthetic",
                                                                   "media": "photo"}
    assert heard("make it pop", "media.polish") == {}
    assert heard("run the moody look on it", "media.polish") == {"look": "moody"}


def test_a_day_only_counts_when_it_means_one_day():
    assert heard("what am i shooting tomorrow", "day.list") == {"on": TOMORROW}
    assert heard("did i post today", "queue.stage") == {"on": date.today().isoformat()}
    assert heard("check 2026-11-02", "day.list") == {"on": "2026-11-02"}
    assert heard("how is friday looking", "day.list") == {}, \
        "next friday is an inference, and a shot list for a day she did not name is a plan she " \
        "did not ask for"


# --------------------------------------------------------------------------- the honest limits

def test_the_arguments_this_app_refuses_to_read_out_of_a_sentence_stay_refused():
    """These seven are the ones where the honest source is something the app already holds - the
    staged line, the interview, the collab list - not something a word scan could find."""
    asked = ("write a caption about my thrift haul for the collage shop, mention GlucoLove, "
             "topic is summer, on the version with the red bag, name of brand is 8TH HOUSE")
    for tool_id in ("copy.tags", "copy.tone", "research.library", "lang.check", "collab.pitch"):
        got = heard(asked, tool_id)
        for key in params.NOT_FROM_A_SENTENCE:
            assert key not in got, f"{tool_id} took {key} out of a sentence: {got}"


def test_a_tool_that_takes_no_platform_never_hears_one():
    assert heard("post this on tiktok tomorrow", "metrics.window") == {}
    assert heard("what do you know about me from instagram", "memory.recall") == {}


def test_every_argument_the_registry_declares_is_decided_about():
    """The guard against this file quietly falling behind the tools. Nine arguments are extracted,
    seven are refused in writing, and an argument that is neither is a bug someone will find in a
    year from now, when a command does nothing with the words she typed."""
    declared = {key for tool in REGISTRY.values() for key in tool.args}
    undecided = sorted(declared - set(params.FINDERS) - set(params.NOT_FROM_A_SENTENCE))
    assert undecided == [], f"declared arguments nobody has decided about: {undecided}"
    assert set(params.FINDERS) <= declared | {"keep"}, "a finder for an argument no tool takes"


# ------------------------------------------------------------------------------- precedence

def test_what_she_typed_outranks_what_a_planner_read_into_it():
    """The plan is a reading of the same sentence. Where the two disagree the sentence is the
    evidence, and a line sent to the wrong platform is her account, not the model's mistake."""
    tool = REGISTRY["copy.tags"]
    assert params.fill(tool, {"platform": "x"}, "give me hashtags for tiktok")["platform"] == \
        "tiktok"
    assert params.fill(tool, {"platform": "x", "limit": 3}, "hashtags for tiktok") == \
        {"platform": "tiktok", "limit": 3}
    assert params.fill(tool, {"limit": 3}, "give me 8 hashtags") == {"limit": 8}


def test_a_value_she_did_not_name_is_left_exactly_as_the_planner_set_it():
    tool = REGISTRY["copy.tags"]
    assert params.fill(tool, {"platform": "x", "limit": 3}, "give me hashtags") == \
        {"platform": "x", "limit": 3}


def test_the_model_s_own_arguments_survive_the_planner(world):
    """`model_plan` used to read the tool id out of the answer and drop the args, which made the
    prompt's own instruction to answer with args a lie to the model."""
    kit = world.app.state.kit
    open_ids = orchestrator.available(kit, modes.get("operator"))
    chosen = next(i for i in open_ids if REGISTRY[i].args)
    key = REGISTRY[chosen].args[0]
    given = 3 if key == "limit" else "x"

    class Planner:
        name = "planner-model"

        def complete_json(self, system, user, schema, images=None):
            assert f"{chosen} (takes: " in system, "the catalogue must say what each tool takes"
            return {"steps": [{"tool": chosen, "args": {key: given}}], "because": "one"}

    kit.engine.engine = Planner()
    steps, planner = orchestrator.plan_steps(kit, "do the thing", modes.get("operator"))
    assert steps == [(chosen, {key: given})]
    assert "planner-model" in planner


# --------------------------------------------------------------------------------- wired

def test_the_arguments_recorded_for_a_real_ask_are_the_ones_the_tool_ran(world):
    """The end-to-end claim: she types a sentence into the command centre, and the run history
    shows the languages and the placement she said - not the empty dict the planner picked with."""
    stage(world)
    record = run(world, "put this in spanish and kreyol for tiktok", "agency")
    step = step_of(record, "lang.localise")
    assert step["args"] == {"codes": "es ht", "platform": "tiktok"}
    assert step["kind"] == "advised", "no model is connected, so nothing was translated"
    briefs = step["detail"]["briefs"]
    assert [b["language"] for b in briefs] == ["es", "ht"]


def test_naming_everything_does_not_upgrade_her_grants(world):
    """The sentence reaches the tool; the policy still decides whether the tool runs. Under
    Operator a make-action is advised with her words in the history, waiting for her press - and
    that boundary is the point of the modes, so it is pinned here rather than drifted past."""
    stage(world)
    step = step_of(run(world, "put this in spanish and kreyol for tiktok"), "lang.localise")
    assert step["args"] == {"codes": "es ht", "platform": "tiktok"}
    assert step["kind"] == "advised"
    assert "until you press it" in step["summary"]
    assert "briefs" not in step["detail"], "nothing ran, so there is nothing to show off it"


def test_a_keep_word_typed_in_the_command_lands_on_the_brief_as_she_wrote_it(world):
    stage(world)
    step = step_of(run(world, "put this in spanish, do not translate GlucoLove", "agency"),
                   "lang.localise")
    assert step["args"]["keep"] == "GlucoLove"
    locked = step["detail"]["briefs"][0]["locked"]
    assert "GlucoLove" in locked, "the word she protected is on the sheet she hands a person"
    assert "glucolove" not in locked


def test_a_named_platform_changes_the_word_budget_the_brief_is_cut_against(world):
    """Not decoration: tiktok and x get different budgets, and a brief cut against the wrong one
    is this app's arithmetic charged to her."""
    budgets = []
    for asked in ("put this in spanish for tiktok", "put this in spanish for x"):
        stage(world)
        step = step_of(run(world, asked, "agency"), "lang.localise")
        budgets.append(step["detail"]["briefs"][0]["words"])
    assert budgets[0] != budgets[1], budgets
    assert budgets[1] < budgets[0], "x runs shorter than tiktok"


def test_a_typed_day_is_the_day_the_planner_was_handed(world):
    step = step_of(run(world, "what am i shooting tomorrow"), "day.list")
    assert step["args"]["on"] == TOMORROW


def test_the_offline_refusal_stays_a_refusal_because_arguments_arrived(world):
    """Everything she named got through, and the answer is still honest about what this machine
    cannot do: two briefs, no sentence in another language."""
    stage(world)
    step = step_of(run(world, "put this in french and spanish", "agency"),
                        "lang.localise")
    assert step["args"]["codes"] == "fr es"
    assert "versions" not in step["detail"]
    assert "Nothing was written in another language" in step["summary"]
