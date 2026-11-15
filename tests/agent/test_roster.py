"""The roster, checked against the catalogue it is drawn from.

The command centre promises specialists, which is the easiest place in this app to put a card
that does nothing. So the checks are arithmetic first - every desk owns a tool that exists, no
tool sits on two desks, nothing is left unassigned, and the import-time guard in `roster` fails
the moment that stops being true - and behaviour second: a sentence hands work to a named desk,
a named desk runs only its own bench, and neither can talk its way past the mode she set.
"""

import pytest
from fastapi.testclient import TestClient

from src.agent import roster
from src.agent.tools import REGISTRY
from src.app import create_app
from src.config import Config


@pytest.fixture
def world(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "roster.sqlite3"))
    return client


def steps(db):
    return {s["tool"]: s for s in db.recent_runs(1)[0]["steps"]}


def test_no_desk_is_hired_without_work_and_no_tool_is_left_unassigned():
    owned = [t for d in roster.desks() for t in d.tools]
    assert owned, "an empty org chart is not a roster"
    assert len(owned) == len(set(owned)), "a tool on two desks means two desks claim one step"
    assert set(owned) == set(REGISTRY), (
        f"unassigned: {sorted(set(REGISTRY) - set(owned))}; "
        f"invented: {sorted(set(owned) - set(REGISTRY))}")
    for desk in roster.desks():
        assert len(desk.tools) >= 1, f"{desk.name} owns nothing"
        assert len(desk.line) > 40 and desk.words, f"{desk.name} is a name without a description"


def test_a_guard_that_only_passes_today_is_not_a_guard():
    """The import check is the feature. It is reached the same way the app reaches it, with a
    desk naming a tool that does not exist and a tool claimed twice, and it has to name the
    offender rather than shrug."""
    ghost = roster.Desk("ghost", "The Ghost", "A desk with nothing behind it but a nice name.",
                        ("no.such.tool",), ("ghost",))
    with pytest.raises(RuntimeError) as raised:
        roster.check((ghost,))
    assert "no.such.tool" in str(raised.value)

    thief = roster.Desk("thief", "The Thief", "A desk that claims work another desk is doing.",
                        ("research.library",), ("steal",))
    with pytest.raises(RuntimeError) as raised:
        roster.check((roster.desks()[0], thief))
    assert "research.library" in str(raised.value)


@pytest.mark.parametrize("asked,desk", [
    ("judge my photos and tell me which one to post", "editor"),
    ("what is trending in my niche right now", "research"),
    ("when should i be posting", "metrics"),
    ("write me a caption for the street clip", "voice"),
    ("did the test work out", "experiment"),
    ("cut these into story frames", "repurpose"),
    ("rebuild my eight weeks", "strategy"),
    ("what do i shoot today", "producer"),
    ("who should i pitch for a collab", "collab"),
    ("translate the caption", "translator"),
    ("i want this in spanish too", "translator"),
    ("check the french version against my line", "translator"),
    ("seo check this caption", "seo"),
    ("how much should i charge a brand", "money"),
    ("give me trending hashtags", "voice"),
])
def test_a_sentence_names_the_desk_that_should_do_it(asked, desk):
    got = roster.route(asked)
    assert got is not None and got.id == desk, f"{asked!r} went to {got and got.name}"


def test_an_ask_that_names_two_rooms_goes_to_the_one_being_asked_for():
    """Counting matches equally handed every one of these to whichever desk is early in the
    tuple: `caption` is The Voice's word and `brand` is The Strategist's, and neither is what
    she asked for. The language, the audit and the price are."""
    for asked, wanted in (("translate the caption", "translator"),
                          ("write this in kreyol", "translator"),
                          ("seo check this caption", "seo"),
                          ("how much should i charge a brand", "money"),
                          ("give me trending hashtags", "voice")):
        assert roster.route(asked).id == wanted, asked
    # and a word that is only ever pointed at, not asked for, still counts as one.
    assert roster.route("what is trending in my niche").id == "research"


def test_a_weight_on_a_word_that_never_routes_is_caught():
    """A strong word has to be one of the desk's own words or the weight is never read, and the
    mistake is invisible: the desk just quietly loses every tie it was built to win."""
    lying = roster.Desk("lying", "The Liar", "A desk that weights a word it does not answer to.",
                        ("research.library",), ("trend",), ("spanish",))
    with pytest.raises(RuntimeError) as raised:
        roster.check((lying,))
    assert "spanish" in str(raised.value)


def test_a_word_only_counts_when_it_starts_one():
    """`lab` belongs to The Experimenter and `collab` to The Broker, and plain substring
    matching sent every pitch ask to the lab on the strength of the three letters inside it."""
    assert roster.route("should i do a collab with the vintage girl").id == "collab"
    assert roster.route("what did the lab say").id == "experiment"
    assert roster.route("what is trending in my niche").id == "research", \
        "the ending stays open, so a word with a suffix on it still counts"


def test_an_ask_that_names_nobody_routes_to_no_desk():
    """The fallback has to stay reachable: a sentence about nothing in particular runs the
    whole growth loop, and a router that always picks a desk would quietly narrow every run."""
    assert roster.route("do the thing") is None
    assert roster.route("") is None
    assert roster.route("   ") is None


def test_naming_a_desk_runs_that_bench_and_nothing_else(world):
    world.post("/agent/run", data={"asked": "", "mode": "operator", "desk": "editor"})
    run = world.app.state.kit.db.recent_runs(1)[0]
    assert run["planner"] == "The Editor (you named the desk)", run["planner"]
    assert {s["tool"] for s in run["steps"]} == set(roster.by_id("editor").tools), \
        "the bench is what ran: no extra tool slipped in because the loop knows it"


def test_a_desk_cannot_be_named_past_the_mode_she_set(world):
    """Naming a desk is a choice about who works, not a licence to work. Researcher does not
    reach for posting or assets, so all three steps come back refused with the reason."""
    world.post("/agent/run", data={"asked": "", "mode": "researcher", "desk": "producer"})
    got = steps(world.app.state.kit.db)
    assert got, "the desk still has to appear in the history"
    for tool, step in got.items():
        assert step["kind"] == "skipped", f"{tool} ran under Researcher: {step}"
        assert "Researcher does not reach for" in step["summary"], step["summary"]


def test_a_desk_whose_bench_is_shut_says_what_it_is_waiting_for(world):
    """Nothing is stored and no photo is in the inbox, so the Analyst has one runnable tool and
    three that are not. It records each, with the sentence she would have to satisfy."""
    world.post("/agent/run", data={"asked": "", "mode": "operator", "desk": "metrics"})
    got = steps(world.app.state.kit.db)
    assert got["metrics.take"]["kind"] in ("did", "advised", "skipped")
    shut = [s for s in got.values() if s["kind"] == "skipped"]
    assert shut, "three of these four need numbers or a plan"
    for step in shut:
        assert step["summary"].strip(), f"{step['tool']} skipped without a reason"
        assert any(w in step["summary"].lower() for w in ("no numbers", "no eight-week plan",
                                                          "not run")), step["summary"]
    assert not [s for s in got.values() if s["kind"] == "failed"], "a waiting tool is not a crash"


def test_the_page_staves_every_desk_with_a_way_to_ask_it(world):
    body = world.get("/agent").text
    assert "toolbox" in body.lower(), "the command centre still names its own hands"
    for desk in roster.desks():
        assert desk.name in body, f"{desk.name} is not on the page"
        assert f'name="desk" value="{desk.id}"' in body, f"{desk.name} cannot be asked"
    for tool in REGISTRY.values():
        assert tool.id in body, f"{tool.id} has no line on the page it is registered in"


def test_the_history_says_who_did_the_work(world):
    world.post("/agent/run", data={"asked": "research what is working", "mode": "operator"})
    body = world.get("/agent").text
    assert "The Scout" in body, "a step with no desk beside it is the loop, not a specialist"
    assert "planned by" in body


def test_the_ready_count_is_the_bench_she_can_actually_use(world):
    """The number on the card moves when the app is given something to work on, not when the
    plan happens to mention a tool. The Editor reads the inbox, so an empty inbox is an
    off-duty bench and one photo is a full one."""
    from PIL import Image

    kit = world.app.state.kit
    editor = roster.by_id("editor")
    assert "0 of 3 ready" in " ".join(world.get("/agent").text.split())
    assert [t.id for t in editor.staffed(kit)] == [], "nothing to open, so nobody to send"
    folder = kit.paths["inbox"]
    folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 500), (120, 110, 100)).save(folder / "one.jpg", "JPEG")
    assert {t.id for t in editor.staffed(kit)} == set(editor.tools)
    assert "3 of 3 ready" in " ".join(world.get("/agent").text.split())
