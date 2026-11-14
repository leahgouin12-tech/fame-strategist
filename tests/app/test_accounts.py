"""The accounts page is the answer to "can it log in for me", so the tests are that the
answer cannot be misread: every link it shows is a real address, no box takes a password, and
a saved note says out loud that nothing was contacted and no session was taken."""

import re
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from src import accounts
from src.app import create_app
from src.config import Config


def note_of(got) -> str:
    """The sentence the redirect is carrying, decoded - because asserting on the escaped form
    is how a test passes while the copy reads wrong."""
    return parse_qs(urlparse(got.headers["location"]).query)["note"][0]


@pytest.fixture
def world(tmp_path):
    return TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                 tmp_path / "a.sqlite3")), tmp_path


@pytest.fixture
def client(world):
    return world[0]


def test_every_platform_is_described_in_three_parts(client):
    body = client.get("/accounts").text
    for label in ("Instagram", "TikTok", "YouTube", "Pinterest", "X"):
        assert label in body
    assert "WHAT IT CAN READ" in body and "WHAT IT CAN POST" in body
    assert "MUSIC AND SOUNDS" in body


def test_no_box_on_the_page_accepts_a_password(client):
    body = client.get("/accounts").text
    assert 'type="password"' not in body
    assert not re.search(r"sessionid|ddg5|appstate|cookies\.sqlite", body.lower())


def test_the_handoff_buttons_point_at_real_addresses(client):
    """A button that goes nowhere is the failure this app keeps being tested for, and the
    addresses are data rather than code so the guardrail still refuses a hardcoded URL."""
    body = client.get("/accounts").text
    hrefs = set(re.findall(r'href="([^"]+)"\s+target="_blank"', body))
    assert hrefs == set(accounts.default_links().values())
    assert all(accounts.valid_link(h) for h in hrefs)


def test_a_saved_note_is_recorded_as_a_note_and_says_so(client):
    client.post("/accounts/save", data={"platform": "tiktok", "handle": "@her",
                                         "method": "export", "connected": "on",
                                         "last_export": date.today().isoformat()})
    body = client.get("/accounts").text
    assert "@her" in body
    assert "signed in on your browser" in body
    assert "export read in" in body
    again = client.post("/accounts/save", data={"platform": "tiktok", "handle": "@her",
                                                "method": "token"},
                        follow_redirects=False)
    note = note_of(again)
    assert "Nothing was contacted" in note and "no login was taken" in note
    assert "A token you mint yourself" in note


def test_a_garbage_date_does_not_take_the_page_down(client):
    got = client.post("/accounts/save", data={"platform": "instagram", "handle": "",
                                              "method": "handoff", "last_export": "tuesday"},
                      follow_redirects=False)
    assert got.status_code == 303
    assert "Tuesday" not in client.get("/accounts").text


def test_an_unknown_method_falls_back_to_the_one_that_is_true(client):
    client.post("/accounts/save", data={"platform": "x", "handle": "h", "method": "magic"})
    assert accounts.state_rows(client.app.state.db.get_accounts())[4]["method"] == "handoff"


def test_an_address_without_a_scheme_is_refused_and_named(world):
    client, root = world
    got = client.post("/accounts/links", data={"link_instagram": "instagram.com",
                                               "link_tiktok": "https://tiktok.com/@me"},
                      follow_redirects=False)
    assert "Refused Instagram" in note_of(got)
    saved = accounts.load_links(root / "accounts.json")
    assert saved["tiktok"] == "https://tiktok.com/@me"
    assert saved["instagram"] == accounts.default_links()["instagram"]


def test_the_links_live_in_a_file_she_owns(world):
    client, root = world
    client.post("/accounts/links", data={"link_pinterest": "https://pinterest.com/business/"})
    path = root / "accounts.json"
    assert path.is_file()
    assert "pinterest.com/business" in path.read_text(encoding="utf-8")


def test_forgetting_clears_the_note_and_says_the_account_is_untouched(client):
    client.post("/accounts/save", data={"platform": "youtube", "handle": "@chan",
                                        "method": "token", "connected": "on"})
    got = client.post("/accounts/forget", data={"platform": "youtube"},
                      follow_redirects=False)
    assert "never held anything" in note_of(got)
    assert client.app.state.db.get_accounts()["youtube"]["handle"] == ""
    assert "@chan" not in client.get("/accounts").text


def test_the_numbers_line_tells_the_truth_before_any_import(client):
    body = client.get("/accounts").text
    assert "Nothing has been read in yet" in body
    assert "metrics-last.csv" in body


def test_the_platform_facts_refuse_the_things_this_app_will_not_do():
    """The copy on the page is the guardrail with sentences in it: if the module ever stops
    saying that a licensed sound cannot be attached, the composer starts implying it can."""
    for p in accounts.PLATFORMS:
        assert any(word in p["music"].lower() for word in
                   ("cannot", "in-app", "licence", "no music layer"))
        assert p["steps"], p["id"]
        # The word is allowed only inside a refusal: "we ask for your password" and "we will
        # never ask for your password" differ by three characters and mean opposite things.
        for hit in re.finditer("password", p["reads"].lower()):
            before = p["reads"].lower()[max(0, hit.start() - 40):hit.start()]
            assert re.search(r"\bno\b|\bnot\b|never", before), (p["id"], before)
    assert "no password" in " ".join(m[2] for m in accounts.METHODS).lower()
