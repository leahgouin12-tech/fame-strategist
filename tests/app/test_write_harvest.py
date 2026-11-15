"""The export route into her voice, proved through the pages rather than the parser.

What is at stake is one sentence in the design spec: a line becomes her voice only because she
said so. So every test here asks the same question twice - what the app found, and what it was
allowed to remember before she ticked a box. It also checks the two ways a harvest can quietly
go wrong: another person's reply sliding into her profile, and a stale claim about a file she
overwrote by pasting.
"""

import io
import json
import re
import zipfile
from html import unescape
from urllib.parse import unquote_plus

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Config

MINE = ["wore the tank again lol", "nobody asked for this but ok #thrifted",
        "wait why is the lighting like this"]
THEIRS = "you look great!! omg the lighting though"


def payload():
    return {"mediaList": [{"caption": MINE[0], "comments": [{"text": THEIRS}]},
                          {"caption": MINE[1]}, {"description": MINE[2]},
                          {"caption": "#only #tags"}]}


def export_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("captions.json", json.dumps(payload()))
        zf.writestr("media/photo-1.jpg", b"\xff\xd8not really a jpeg")
    return buf.getvalue()


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text))


@pytest.fixture
def world(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "harvest.sqlite3"))
    return client, tmp_path


def send(world, name="captions.zip", data=None, ctype="application/zip"):
    client = world[0]
    return client.post("/write/harvest", follow_redirects=False,
                       files={"file": (name, data if data is not None else export_zip(), ctype)})


def page(world):
    return flat(world[0].get("/write").text)


def kept(world):
    return world[0].app.state.db.get_voice()


def test_the_writer_offers_the_export_as_well_as_the_paste_box(world):
    body = page(world)
    assert 'action="/write/harvest"' in body and 'enctype="multipart/form-data"' in body
    assert 'name="file"' in body
    assert "until you tick it" in body
    assert "No model call, no upload, no account touched" in body


def test_the_lines_are_shown_before_any_of_them_are_hers(world):
    back = send(world)
    assert back.status_code == 303
    assert "read out of captions.zip" in unquote_plus(back.headers["location"])
    assert kept(world) == [], "the profile changed without her saying so"
    body = page(world)
    for line in MINE:
        assert line in body, line
    assert "mediaList[0].caption" in body, "the page has to name where each line was read from"


def test_nobody_elses_words_get_near_the_list(world):
    send(world)
    body = page(world)
    assert THEIRS not in body
    assert "mediaList[0].comments" in body, "it should say what it refused to read"


def test_a_hashtag_wall_is_shown_as_refused_with_the_reason(world):
    send(world)
    body = page(world)
    assert "#only #tags" in body and "hashtags only" in body


def test_ticking_the_lines_is_what_makes_them_her_voice(world):
    send(world)
    back = world[0].post("/write/harvest/keep", data={"keep": ["0", "2"]},
                         follow_redirects=False)
    assert back.status_code == 303
    assert kept(world) == [MINE[0], MINE[2]], "the unticked line slipped in, or the order moved"
    rows = world[0].app.state.db.recall("voice-source")
    assert len(rows) == 1 and "captions.zip" in rows[0]["body"]
    assert "2 lines now" in unquote_plus(back.headers["location"])
    assert "read out of captions.zip" in unquote_plus(back.headers["location"])


def test_the_staged_list_goes_when_she_has_kept_it(world):
    send(world)
    world[0].post("/write/harvest/keep", data={"keep": ["1"]}, follow_redirects=False)
    body = page(world)
    assert 'name="keep"' not in body
    assert (world[0].app.state.db.recall("voice-source") or [{}])[0]["body"]
    assert "found in captions.zip" not in body


def test_keeping_nothing_changes_nothing_and_says_so(world):
    send(world)
    back = world[0].post("/write/harvest/keep", data={}, follow_redirects=False)
    assert back.status_code == 303
    assert "Not one line kept" in unquote_plus(back.headers["location"])
    assert kept(world) == []
    assert 'name="keep"' in page(world), "the list should still be there to decide about"


def test_throwing_the_batch_away_leaves_no_list_and_no_claim(world):
    send(world)
    back = world[0].post("/write/harvest/drop", data={}, follow_redirects=False)
    assert back.status_code == 303
    assert "Left those lines alone" in unquote_plus(back.headers["location"])
    assert 'name="keep"' not in page(world)
    assert not (world[1] / "harvest.json").exists()
    assert world[0].app.state.db.recall("voice-source") == []


def test_an_export_with_no_captions_of_hers_leaves_the_profile_alone(world):
    data = json.dumps({"followers": [{"name": "kyle"}, {"name": "dre"}]}).encode()
    back = send(world, name="followers.json", data=data, ctype="application/json")
    assert back.status_code == 303
    note = unquote_plus(back.headers["location"])
    assert "caption-shaped key" in note
    assert kept(world) == []
    assert 'name="keep"' not in page(world)


def test_a_plain_text_file_of_old_captions_works_too(world):
    data = "\n\n".join(MINE).encode()
    back = send(world, name="old-captions.txt", data=data, ctype="text/plain")
    assert back.status_code == 303, back.headers["location"]
    body = page(world)
    assert MINE[1] in body and "old-captions.txt" in body


def test_a_submit_with_no_file_chosen_says_so_rather_than_reading_nothing(world):
    back = world[0].post("/write/harvest", data={"note": ""}, follow_redirects=False)
    assert back.status_code == 303
    assert "No file came through" in unquote_plus(back.headers["location"])
    assert kept(world) == []
    assert not (world[1] / "harvest.json").exists()


def test_the_caption_page_stops_claiming_it_learned_nothing(world):
    send(world)
    world[0].post("/write/harvest/keep", data={"keep": ["0", "1"]}, follow_redirects=False)
    body = flat(world[0].get("/captions", params={"subject": "mirror selfie in the black ribbed "
                                                          "tank"}).text)
    assert "Your voice is unlearned" not in body
    assert "read from captions.zip" in body, "the card should name the file it measured from"


def test_pasting_afterwards_retires_the_claim_about_the_file(world):
    send(world)
    world[0].post("/write/harvest/keep", data={"keep": ["0"]}, follow_redirects=False)
    assert world[0].app.state.db.recall("voice-source")
    world[0].post("/write/samples", data={"samples": "just me and the tank again"},
                  follow_redirects=False)
    assert world[0].app.state.db.recall("voice-source") == [], "the page still credits a file she " \
                                                               "rewrote by hand"
    body = flat(world[0].get("/captions", params={"subject": "the tank"}).text)
    assert "captions.zip" not in body


def test_the_keep_page_survives_a_half_broken_form(world):
    """A ticked box whose index is junk must not take her whole profile with it, and a batch she
    never uploaded cannot be kept from a stale page."""
    send(world)
    back = world[0].post("/write/harvest/keep", data={"keep": ["99", "not-a-number", "1"]},
                         follow_redirects=False)
    assert back.status_code == 303
    assert kept(world) == [MINE[1]]
    gone = world[0].post("/write/harvest/keep", data={"keep": ["0"]}, follow_redirects=False)
    assert "That batch is gone" in unquote_plus(gone.headers["location"])
