"""The phone is a second machine, so every page has to decide twice: what it shows, and
whether the thing asking is allowed to see it. These tests are that second decision."""

import pytest
from fastapi.testclient import TestClient

from src import net
from src.app import create_app
from src.config import Config

LAPTOP = ("127.0.0.1", 53211)
PHONE = ("192.168.1.50", 53212)
PIN = "sunflower"


@pytest.fixture
def pair(tmp_path):
    """One app, two visitors - the laptop and a phone on the same wifi."""
    app = create_app(Config(api_key=None, engine_name="offline", model=""),
                     tmp_path / "a.sqlite3")
    return {"laptop": TestClient(app, client=LAPTOP),
            "phone": TestClient(app, client=PHONE),
            "gate": tmp_path / "phone.json"}


def open_the_door(pair):
    return pair["laptop"].post("/phone/pin", data={"pin": PIN})


# ---- who is let in ----------------------------------------------------------


def test_the_laptop_never_has_to_answer_for_itself(pair):
    assert pair["laptop"].get("/photos").status_code == 200


def test_a_phone_is_not_let_in_before_she_opens_the_door(pair):
    got = pair["phone"].get("/photos")
    assert got.status_code == 401
    assert "not open to the network" in got.text.lower()
    assert "/inbox/" not in got.text, "a refused page must not name a single file"


def test_the_door_stays_shut_even_on_the_pages_that_look_harmless(pair):
    for path in ["/today", "/numbers", "/sources", "/edit?name=x.jpg", "/photos/upload"]:
        assert pair["phone"].get(path).status_code == 401, path


def test_the_pin_box_can_still_load_its_own_look(pair):
    """A plain browser error page is what a phishing box looks like, so the stylesheet that
    makes this one look like the app has to be reachable without a PIN."""
    assert pair["phone"].get("/static/app.css").status_code == 200
    assert "/static/app.css" in pair["phone"].get("/photos").text


# ---- setting the PIN --------------------------------------------------------


def test_the_pin_is_written_as_a_hash_and_never_as_itself(pair):
    assert open_the_door(pair).status_code == 200
    stored = pair["gate"].read_text(encoding="utf-8")
    assert PIN not in stored, "a PIN that can be read off the disk is not a PIN"
    assert "salt" in stored and "hash" in stored


def test_a_phone_cannot_open_its_own_door(pair):
    """Two layers, because both matter: the door never answers an unauthenticated phone at
    all, and once a phone is inside, the PIN setter still refuses it - a stolen unlocked
    phone must not be able to change the lock and lock her out of her own laptop."""
    got = pair["phone"].post("/phone/pin", data={"pin": PIN})
    assert got.status_code == 401, "an unanswered phone gets the PIN box, not a settings page"
    assert not pair["gate"].exists()

    open_the_door(pair)
    pair["phone"].post("/phone/unlock", data={"pin": PIN})
    inside = pair["phone"].post("/phone/pin", data={"pin": "hijacked"})
    assert "on the laptop" in inside.text.lower()
    assert pair["phone"].post("/phone/unlock", data={"pin": "hijacked"},
                              follow_redirects=False).status_code == 401
    assert pair["phone"].post("/phone/unlock", data={"pin": PIN},
                              follow_redirects=False).status_code == 303
    assert pair["phone"].get("/photos").status_code == 200, "the refusal changed nothing"


def open_the_door_type(pair, pin):
    return pair["laptop"].post("/phone/pin", data={"pin": pin})


@pytest.mark.parametrize("bad", ["123", "", "  ", "twelve thirty four", "a" * 13])
def test_an_unusable_pin_is_named_not_stored(pair, bad):
    got = open_the_door_type(pair, bad)
    assert "characters" in got.text.lower()
    assert not pair["gate"].exists()


# ---- answering with it ------------------------------------------------------


def test_the_phone_gets_in_once_it_answers_with_the_pin(pair):
    open_the_door(pair)
    got = pair["phone"].post("/phone/unlock", data={"pin": PIN}, follow_redirects=False)
    assert got.status_code == 303
    assert got.headers["location"] == "/today"
    assert net.COOKIE in got.cookies, "the PIN is typed once, not once per page"
    assert pair["phone"].get("/photos").status_code == 200


def test_a_wrong_pin_opens_nothing_and_says_so_plainly(pair):
    open_the_door(pair)
    got = pair["phone"].post("/phone/unlock", data={"pin": "daisy"}, follow_redirects=False)
    assert got.status_code == 401
    assert "wrong pin" in got.text.lower()
    assert net.COOKIE not in got.cookies


def test_five_wrong_guesses_bring_a_wait_instead_of_a_sixth_chance(pair):
    open_the_door(pair)
    for _ in range(net.MAX_WRONG):
        pair["phone"].post("/phone/unlock", data={"pin": "wrong"})
    got = pair["phone"].post("/phone/unlock", data={"pin": PIN}, follow_redirects=False)
    assert got.status_code == 401, "the right PIN cannot buy its way out of a cooldown"
    assert "minute" in got.text.lower()


def test_the_unlock_answer_cannot_be_used_to_leave_the_app(pair):
    open_the_door(pair)
    got = pair["phone"].post("/phone/unlock", data={"pin": PIN, "back": "//somewhere.else/x"},
                             follow_redirects=False)
    assert got.headers["location"] == "/today"


def test_the_phone_lands_where_it_was_reaching_for(pair):
    open_the_door(pair)
    got = pair["phone"].post("/phone/unlock", data={"pin": PIN, "back": "/numbers"},
                             follow_redirects=False)
    assert got.headers["location"] == "/numbers"


def test_locking_every_phone_sends_them_back_to_the_pin_box(pair):
    open_the_door(pair)
    pair["phone"].post("/phone/unlock", data={"pin": PIN})
    assert pair["phone"].get("/photos").status_code == 200
    pair["laptop"].post("/phone/lock")
    assert pair["phone"].get("/photos").status_code == 401


def test_a_new_pin_locks_the_phone_that_already_walked_in(pair):
    open_the_door(pair)
    pair["phone"].post("/phone/unlock", data={"pin": PIN})
    pair["laptop"].post("/phone/pin", data={"pin": "marigold"})
    assert pair["phone"].get("/photos").status_code == 401


# ---- taking the finished file back ----------------------------------------


def test_an_edit_saved_on_the_laptop_can_be_taken_back_to_the_phone(pair, tmp_path):
    """Shooting on the phone only pays off if the finished frame comes back to it, so every
    saved copy is offered as a file, not just as something to reopen on the laptop."""
    from PIL import Image
    edited = tmp_path / "inbox" / "edited"
    edited.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 60), (200, 120, 40)).save(edited / "Look-1.jpg")
    body = pair["laptop"].get("/photos").text
    assert 'href="/inbox/edited/Look-1.jpg"' in body and "download" in body
    assert pair["laptop"].get("/inbox/edited/Look-1.jpg").status_code == 200
    assert pair["phone"].get("/inbox/edited/Look-1.jpg").status_code == 401, \
        "the file is for her phone, not for anyone holding the address"


# ---- the pairing page -------------------------------------------------------


def test_the_phone_page_gives_an_address_to_type(pair, monkeypatch):
    monkeypatch.setattr(net, "lan_addresses", lambda: ["172.20.10.2", "192.168.1.44"])
    body = pair["laptop"].get("/phone").text
    assert "http://172.20.10.2" in body and "http://192.168.1.44" in body
    assert "Add to Home Screen" in body, "the iPhone installs it from Share, not from a prompt"


def test_the_phone_page_says_so_when_there_is_no_network(pair, monkeypatch):
    monkeypatch.setattr(net, "lan_addresses", lambda: [])
    assert "not joined to a network" in pair["laptop"].get("/phone").text.lower()


def test_the_phone_page_shows_the_lock_state_it_actually_has(pair):
    open_the_door(pair)
    body = pair["laptop"].get("/phone").text
    assert "Change the PIN" in body and "Lock every phone" not in body
    pair["phone"].post("/phone/unlock", data={"pin": PIN})
    assert "1 phone in" in pair["laptop"].get("/phone").text
    assert "Lock every phone" in pair["laptop"].get("/phone").text


def test_the_app_offers_the_phone_page_rather_than_making_her_find_it(pair):
    assert 'href="/phone"' in pair["laptop"].get("/today").text


# ---- the iPhone side of it --------------------------------------------------


def test_the_iphone_is_told_to_open_it_like_an_app(pair):
    body = pair["laptop"].get("/today").text
    assert 'name="apple-mobile-web-app-capable" content="yes"' in body
    assert 'name="apple-mobile-web-app-title"' in body
    assert "viewport-fit=cover" in body, "the notch is part of the screen she has to fit"


def test_the_stylesheet_reaches_a_thumb(pair):
    css = pair["laptop"].get("/static/app.css").text
    assert "env(safe-area-inset-top)" in css
    assert "touch-action: manipulation" in css, "double-tap zoom turns a tap into a jump"
    assert "min-height: 44px" in css
    assert "font-size: 16px" in css, "Safari zooms the whole page under 16px"


# ---- the address list and the launcher --------------------------------------


def test_the_laptop_is_never_counted_as_a_phone():
    for host in ["127.0.0.1", "::1", "testclient", "", "169.254.8.8"]:
        assert not net.is_foreign(host), host
    for host in ["192.168.1.50", "172.20.10.2", "10.0.0.5"]:
        assert net.is_foreign(host), host


def test_the_address_list_holds_no_loopback_and_no_duplicates():
    found = net.lan_addresses()
    assert len(found) == len(set(found))
    assert all(not a.startswith("127.") for a in found)


def test_the_pin_is_checked_against_a_constant_time_comparison_of_a_hash(tmp_path):
    """The gate is a file and a hash, so its own rules can be read without a browser: no
    PIN set means no way in, an unknown token means no way in, and a device list that grows
    forever is a door nobody can shut."""
    gate = net.PhoneGate(tmp_path / "never-unlocked" / "phone.json")
    assert gate.unlock(PIN) == "", "nothing is right when no PIN was ever set"
    assert gate.accepts("anything") is False
    assert gate.accepts("") is False
    assert gate.has_pin() is False
    assert gate.set_pin("12") != "", "too short to be a PIN"
    assert gate.set_pin(PIN) == ""
    assert gate.has_pin()
    tokens = [gate.unlock(PIN) for _ in range(net.SESSION_LIMIT + 3)]
    assert all(tokens), "every phone she unlocks gets its own answer"
    assert gate.accepts(tokens[0]) is False, "the oldest device falls off, so the list stays shut-able"
    assert gate.accepts(tokens[-1])


def test_the_engine_listens_for_the_wifi_adapter():
    import run as launcher
    assert launcher.HOST == "0.0.0.0"
    assert "0.0.0.0" not in launcher.URL, "the laptop still opens the address it always knew"


def test_the_launcher_reads_out_the_phone_address(monkeypatch, capsys):
    import run as launcher
    monkeypatch.setattr(launcher.net, "lan_addresses", lambda: ["172.20.10.2"])
    monkeypatch.setattr(launcher, "live_instance", lambda: "")
    monkeypatch.setattr(launcher, "serve", lambda: None)
    monkeypatch.setattr(launcher, "open_in_browser", lambda url: None)
    launcher.main()
    out = capsys.readouterr().out
    assert f"http://172.20.10.2:{launcher.PORT}" in out
    assert "/phone" in out
