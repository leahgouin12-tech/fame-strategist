"""The registry page, tested against the repository it claims to describe.

The audit parses the real tree, so these tests do not seed anything: they check that what
the page prints is what the audit found, and that a filter that matches nothing says so
instead of quietly showing everything.
"""

import re

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Config
from src.registry import audit as a


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """One app, audited once. The audit reads every file in src, so it is the slowest thing
    in the suite that does not touch a picture - and a module fixture pays it one time."""
    root = tmp_path_factory.mktemp("registry")
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   root / "a.sqlite3"))
    client.post("/registry/read")
    return client


def test_the_page_opens_and_shows_the_counts_it_just_computed(world):
    body = world.get("/registry").text
    entries = a.audit()
    assert f">{len(entries)}<" in body, "the headline figure is the audit's own count"
    assert "features in the tree" in body
    assert "The count is the count" in body


def test_a_first_visit_with_nothing_stored_runs_the_audit_itself(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "a.sqlite3"))
    body = client.get("/registry").text
    assert "Read the repository:" in body
    assert "route:GET /bench" in body


def test_searching_finds_the_thing_and_names_the_test_that_proves_it(world):
    body = world.get("/registry", params={"q": "bench"}).text
    assert "route:GET /bench" in body
    assert "tests/app/test_bench_page.py" in body


def test_a_filter_that_matches_nothing_says_so_rather_than_showing_everything(world):
    body = world.get("/registry", params={"q": "zzz-not-a-thing"}).text
    assert "Nothing in the index matches that" in body
    assert "route:GET /bench" not in body


def test_the_department_filter_narrows_to_that_department_only(world):
    body = world.get("/registry", params={"dept": "Analytics"}).text
    assert "route:GET /bench" in body
    assert "route:GET /trends" not in body


def test_the_department_dropdown_offers_no_choice_that_shows_an_empty_list(world):
    """The list used to be hard-coded department names, so it offered departments the tree has
    no work in - and a filter that returns nothing is the dead control this app is told not to
    build. The options now come from the audit's own distribution, so the test reads the tree,
    compares the two sets, and then proves every offered name has rows behind it.

    It also catches the shape the page actually passes around: the registry is rows of dicts,
    not the Entry objects the audit returns, and a helper written against the wrong one raises
    on the first real read while every mock-shaped test stays green.
    """
    filled = {e.dept for e in a.audit()}
    select = re.search(r'<select name="dept">(.*?)</select>', world.get("/registry").text, re.S)
    offered = [d for d in re.findall(r'<option value="([^"]*)"', select.group(1)) if d]
    assert set(offered) == filled
    for d in offered:
        assert "Nothing in the index matches that" not in world.get(
            "/registry", params={"dept": d}).text, f"{d} was offered with nothing in it"


def test_the_gaps_index_shows_the_holes_the_audit_can_see_today(world):
    """The tab is a reading of the tree, so the test reads the same derivation: when the audit
    sees gaps every one of them is listed with its closing condition, and when it sees none the
    page says the backlog is empty instead of leaving a stale entry behind."""
    ups = a.upgrades(a.audit())
    body = world.get("/registry", params={"kind": "upgrade"}).text
    assert "open gaps" in body
    if ups:
        for u in ups:
            assert u.key in body, u.key
            assert u.acceptance[0] in body, f"{u.key} names no way to close it"
    else:
        assert "no missing test, no missing link" in body, \
            "an empty backlog has to be said, not left as a blank list"
        for stale in ("upgrade:prove-", "upgrade:reach-", "upgrade:document-"):
            assert stale not in body, stale


def test_re_reading_the_repository_reports_what_it_found(world):
    got = a.summary(a.audit(), a.upgrades(a.audit()))
    body = world.post("/registry/read").text
    assert "Re-read the tree just now:" in body
    assert f"{got['features']} features" in body
    assert ("with no test naming them" in body) == bool(got["unproven"])
    assert ("named by a test" in body) == (not got["unproven"])
    assert f"{got['upgrades']} open gaps" in body


def test_an_entry_shows_what_it_reads_and_what_it_hands_back(world):
    body = world.get("/registry", params={"q": "crop"}).text
    assert "inputs" in body and "outputs" in body
    assert "lives at" in body


def test_the_page_refuses_to_look_like_a_roadmap(world):
    body = world.get("/registry").text
    assert "not:</strong> a roadmap" in body
    assert "no registry" in body


def test_the_registry_is_reachable_from_the_nav(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "b.sqlite3"))
    body = client.get("/today").text
    assert "/registry" in body
