"""The model key and the leads it can be asked for - the two halves of #36.

Everything here is about not lying: a key that is never echoed back, a page that says
"offline" instead of inventing an answer, and a lead that stays a lead.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Config
from src.engines.base import Engine
from src.playbook import live

LEADS = {"leads": [{
    "format": "Say the outcome in the first second, then show how you got it.",
    "why_now": "Says the hook test is decided before the caption is read.",
    "how_to_test": "Film the result first, then the three steps that got there.",
    "what_it_could_be_wrong": "Could be true of tutorial accounts and not of outfit posts.",
}]}


class Fake(Engine):
    name = "fake-model"

    def __init__(self, data=None):
        self.data = LEADS if data is None else data
        self.calls = 0

    def complete_json(self, system, user, schema, images=None):
        self.calls += 1
        return self.check(self.data, schema)


def build(tmp_path, engine_name="offline", api_key=None, fake=None):
    cfg = Config(api_key=api_key, engine_name=engine_name, model="gemini-2.5-flash",
                 path=tmp_path / "config.toml")
    client = TestClient(create_app(cfg, tmp_path / "a.sqlite3"))
    if fake is not None:
        client.app.state.engine.engine = fake
    return client


def test_the_machine_page_shows_the_shape_of_the_key_and_never_the_key(tmp_path):
    secret = "AIzaS" + "x" * 30 + "QUID"
    client = build(tmp_path, engine_name="gemini", api_key=secret)
    body = client.get("/engine").text
    assert secret not in body
    assert secret[-4:] in body, "she needs to recognise which key is on file"
    assert 'type="password"' in body


def test_saving_a_key_changes_the_engine_the_other_pages_already_hold(tmp_path):
    client = build(tmp_path)
    assert client.app.state.engine.name == "offline"
    client.post("/engine/save", data={"api_key": "secret-key-123456", "model": "m-two"})
    assert client.app.state.engine.name == "gemini"


def test_the_saved_file_is_the_one_the_app_was_started_with(tmp_path):
    """Not the repo's config.toml: a test that wrote there would change the real app,
    and the real app reads that file before she ever opens a page."""
    repo = Path("config.toml")
    before = repo.read_text(encoding="utf-8") if repo.exists() else None
    client = build(tmp_path)
    client.post("/engine/save", data={"api_key": "abcdef123456", "model": "m"})
    assert (tmp_path / "config.toml").is_file()
    if before is None:
        assert not repo.exists(), "the save went to the repository instead of the tmp path"
    else:
        assert repo.read_text(encoding="utf-8") == before


def test_an_empty_key_box_keeps_the_key_already_saved(tmp_path):
    client = build(tmp_path, api_key="abcdef123456")
    client.post("/engine/save", data={"api_key": "", "model": "other-model"})
    text = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert 'api_key = "abcdef123456"' in text, "changing the model is not signing herself out"
    assert 'model = "other-model"' in text


def test_saving_no_key_at_all_says_offline_rather_than_pretending(tmp_path):
    client = build(tmp_path)
    body = client.post("/engine/save", data={"api_key": "", "model": ""}).text
    assert "offline" in body.lower()
    assert client.app.state.engine.name == "offline"


def test_the_key_never_travels_in_a_url(tmp_path):
    client = build(tmp_path, api_key="abcdef123456")
    for got in (client.get("/engine"), client.get("/"), client.get("/trends")):
        url = str(got.url)
        assert "abcdef" not in url
        assert "api_key=" not in url, "a key in a query string lands in browser history"


def test_testing_without_a_key_reports_that_there_is_nothing_to_test(tmp_path, monkeypatch):
    """No key means no call at all - not a call that fails, and not a made-up success."""
    from src.engines import gemini

    monkeypatch.setattr(gemini.GeminiEngine, "complete_json",
                        lambda *a, **k: pytest.fail("a network call was made with no key"))
    client = build(tmp_path)
    assert "no key to test" in client.post("/engine/test", data={"api_key": ""}).text.lower()


def test_the_trends_page_tells_her_nothing_was_asked(tmp_path):
    body = build(tmp_path).get("/trends").text
    assert "Fresh, unverified" in body
    assert "No lead has been asked for" in body


def test_asking_while_offline_invents_nothing(tmp_path):
    client = build(tmp_path)
    assert "nothing to ask" in client.post("/trends/leads").text.lower()
    assert "no source" not in client.get("/trends").text.lower()


def test_saving_a_key_cannot_take_the_whole_app_down(tmp_path, monkeypatch):
    """A malformed proxy variable in the shell used to be parsed while building the http
    client, inside `create_app`, so the app never came back up after a key was saved. The
    client is built on the first call now, and reads nothing out of the environment."""
    import httpx

    def explode(*a, **k):
        raise ValueError("invalid literal for int(): ':1]'")

    monkeypatch.setattr(httpx, "Client", explode)
    client = build(tmp_path)
    assert "Saved" in client.post("/engine/save", data={"api_key": "abcdef123456",
                                                        "model": "m"}).text
    tested = client.post("/engine/test", data={"api_key": "abcdef123456"}).text
    assert "did not come back" not in tested  # that wording belongs to the lead ask
    assert "ValueError" in tested, "the environment's broken variable is reported, not hidden"
    assert client.get("/").status_code == 200, "a dead model must not mean dead pages"


def test_a_live_ask_lands_under_fresh_unverified_with_the_model_named(tmp_path):
    fake = Fake()
    client = build(tmp_path, fake=fake)
    body = client.post("/trends/leads").text
    assert fake.calls == 1
    assert "Say the outcome in the first second" in body
    assert "said by fake-model" in body
    assert "What could make this wrong" in body
    assert "no source" in body.lower()


def test_a_lead_is_not_written_as_a_finding(tmp_path):
    """Findings carry an as-of date and an address. This carries neither, so it must not
    read as one: the playbook files stay empty and the note table holds the lead."""
    client = build(tmp_path, fake=Fake())
    client.post("/trends/leads")
    store = client.app.state.db
    assert {r["kind"] for r in store.recall(limit=500)} == {
        "lead", "lead_why", "lead_test", "lead_wrong", "lead_run"}


def test_an_ask_that_fails_leaves_the_page_honest(tmp_path):
    class Broken(Engine):
        name = "broken-model"

        def complete_json(self, system, user, schema, images=None):
            raise RuntimeError("quota exceeded")

    client = build(tmp_path, fake=Broken())
    body = client.post("/trends/leads").text
    assert "did not come back" in body and "RuntimeError" in body
    assert not live.ran(client.app.state.db)


def test_leads_can_be_cleared_without_touching_the_findings(tmp_path):
    client = build(tmp_path, fake=Fake())
    client.post("/trends/leads")
    assert "Say the outcome in the first second" in client.get("/trends").text
    body = client.post("/trends/leads", data={"forget": "1"}).text
    assert "Every lead cleared" in body
    assert "Say the outcome in the first second" not in client.get("/trends").text
