from datetime import date

from src.db import DB
from src.engines.base import Engine
from src.playbook import live

TODAY = date(2026, 11, 13)

ANSWER = {"leads": [
    {"format": "Film the outfit twice, once before and once after the street.",
     "why_now": "Says the before/after cut holds a second watch.",
     "how_to_test": "One clip, same outfit, two locations, this week.",
     "what_it_could_be_wrong": "This could be a format that peaked last spring."},
    {"format": "Answer one comment per post, on camera.",
     "why_now": "Says reply videos pull the commenter's own followers.",
     "how_to_test": "Pick the longest comment you already have.",
     "what_it_could_be_wrong": "Could be a habit of big accounts, not a lever for small ones."},
]}


class Fake(Engine):
    name = "fake-model"

    def __init__(self, data=None, raises=None):
        self.data = ANSWER if data is None else data
        self.raises = raises
        self.asked = []

    def complete_json(self, system, user, schema, images=None):
        self.asked.append((system, user, schema))
        if self.raises:
            raise self.raises
        return self.check(self.data, schema)


def db(tmp_path):
    return DB(tmp_path / "l.sqlite3")


def test_an_offline_engine_is_not_asked_to_invent_a_trend(tmp_path):
    """The whole point of this layer: nobody is there, so nothing is produced."""
    assert live.ask(offline(), platforms=["tiktok"], hypotheses=[], chosen="", today=TODAY) == []


def offline():
    from src.engines.offline import OfflineEngine
    return OfflineEngine()


def test_a_live_answer_becomes_leads_with_the_model_and_date_attached():
    found = live.ask(Fake(), platforms=["tiktok", "reels"], hypotheses=["before/after"],
                     chosen="two locations", today=TODAY)
    assert len(found) == 2
    assert found[0].said_by == "fake-model"
    assert found[0].asked_on == "2026-11-13"
    assert found[0].could_be_wrong.startswith("This could be a format")


def test_the_ask_carries_her_lanes_and_forbids_an_invented_statistic():
    engine = Fake()
    live.ask(engine, platforms=["tiktok"], hypotheses=["x"], chosen="y", today=TODAY)
    system, user, _schema = engine.asked[0]
    assert "Do not invent a statistic" in system
    assert "tiktok" in user and "2026-11-13" in user


def test_a_model_that_defends_nothing_yields_no_leads_rather_than_fillers():
    assert live.ask(Fake({"leads": []}), platforms=[], hypotheses=[], chosen="",
                    today=TODAY) == []


def test_the_lead_count_is_capped_at_what_a_person_can_actually_test(tmp_path):
    many = {"leads": [{"format": f"Format {i}", "why_now": "w", "how_to_test": "h",
                       "what_it_could_be_wrong": "c"} for i in range(14)]}
    assert len(live.ask(Fake(many), platforms=[], hypotheses=[], chosen="", today=TODAY)) == 6


def test_a_round_trip_keeps_each_sentence_in_its_own_slot(tmp_path):
    """The order is the meaning: the sentence about how it could be wrong must not read
    as the reason to try it. A shared note kind came back newest-first and swapped them."""
    store = db(tmp_path)
    leads = live.ask(Fake(), platforms=["tiktok"], hypotheses=[], chosen="", today=TODAY)
    live.save(store, leads)
    back = {x.format: x for x in live.load(store)}
    assert set(back) == {x.format for x in leads}
    for lead in leads:
        got = back[lead.format]
        assert got.why_now == lead.why_now
        assert got.how_to_test == lead.how_to_test
        assert got.could_be_wrong == lead.could_be_wrong
        assert got.said_by == lead.said_by and got.asked_on == lead.asked_on


def test_an_ask_that_returned_nothing_still_counts_as_having_been_asked(tmp_path):
    """Never asked and asked-to-nothing are different answers and the page says them
    differently, so the difference has to survive the database."""
    store = db(tmp_path)
    assert not live.ran(store)
    live.save(store, [])
    assert live.ran(store) and live.load(store) == []


def test_the_page_wording_distinguishes_the_three_states(tmp_path):
    store = db(tmp_path)
    assert "No lead has been asked for" in live.note([], live.ran(store))
    live.save(store, [])
    assert "gave nothing it could defend" in live.note([], live.ran(store))
    live.save(store, live.ask(Fake(), platforms=[], hypotheses=[], chosen="", today=TODAY))
    text = live.note(live.load(store), live.ran(store))
    assert "not from a source" in text and "playbook" in text


def test_a_lead_never_becomes_a_playbook_entry(tmp_path):
    """The store is citation-gated and this module writes to the notes table instead, so a
    model's recollection cannot reach the findings page by accident."""
    from src.playbook.store import Store
    store = db(tmp_path)
    live.save(store, live.ask(Fake(), platforms=[], hypotheses=[], chosen="", today=TODAY))
    kinds = {r["kind"] for r in store.recall(limit=500)}
    assert kinds == {"lead", "lead_why", "lead_test", "lead_wrong", "lead_run"}
    assert "trend" not in kinds
    shelf = tmp_path / "pb"
    shelf.mkdir()
    assert Store(TODAY).load(shelf) == []


def test_a_failing_ask_saves_nothing_and_the_caller_sees_the_error(tmp_path):
    store = db(tmp_path)
    engine = Fake(raises=RuntimeError("quota"))
    try:
        leads = live.ask(engine, platforms=[], hypotheses=[], chosen="", today=TODAY)
    except RuntimeError:
        leads = None
    assert leads is None
    assert not live.ran(store)


def test_re_asking_the_same_format_shows_the_latest_answer(tmp_path):
    store = db(tmp_path)
    once = [{"format": "Same sentence.", "why_now": "old reason", "how_to_test": "old test",
             "what_it_could_be_wrong": "old doubt"}]
    live.save(store, live.ask(Fake({"leads": once}), platforms=[], hypotheses=[], chosen="",
                              today=TODAY))
    twice = [{"format": "Same sentence.", "why_now": "new reason", "how_to_test": "new test",
              "what_it_could_be_wrong": "new doubt"}]
    live.save(store, live.ask(Fake({"leads": twice}), platforms=[], hypotheses=[], chosen="",
                              today=date(2026, 12, 1)))
    back = live.load(store)
    assert back[0].why_now == "new reason"
    assert back[0].could_be_wrong == "new doubt"
