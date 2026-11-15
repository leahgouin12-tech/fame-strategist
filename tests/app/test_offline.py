"""The phone has to work where the laptop cannot be reached, so these tests ask one question of
every page: is it on the list a phone downloads, and does that list tell the truth about it?

The danger in this feature is a list that lies. If `pages()` hand-picked a few screens, "everything
offline" would drift into "most of it" the day somebody added a room, and she would find out on a
train. So the tests read the list the way the service worker does - every entry has to answer, no
entry may name a file that is not really there, and the two halves have to speak the same protocol.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import offline
from src.app import create_app
from src.config import Config

ROOT = Path(__file__).resolve().parents[2]
LAPTOP = ("127.0.0.1", 53211)
PHONE = ("192.168.1.50", 53212)


@pytest.fixture
def world(tmp_path):
    """One app on a fresh machine, seen by the laptop that owns it."""
    app = create_app(Config(api_key=None, engine_name="offline", model=""),
                     tmp_path / "a.sqlite3")
    return TestClient(app, client=LAPTOP), tmp_path


def manifest(client):
    return client.get("/offline/manifest").json()


def her_photo(root, name, size=1024):
    (root / "inbox").mkdir(exist_ok=True)
    (root / "inbox" / name).write_bytes(b"\xff\xd8" + b"x" * (size - 2))
    return size


# ---- the list ---------------------------------------------------------------


def test_the_list_is_every_page_the_app_renders(world):
    client, _ = world
    got = manifest(client)
    assert got["pages"], "an empty list would pack nothing and call it everything"
    for path in ["/today", "/write", "/plan", "/captions", "/photos", "/numbers", "/agent"]:
        assert path in got["pages"], path
    assert "/offline/manifest" not in got["pages"], "the list cannot contain itself"


def test_every_page_on_the_list_really_answers(world):
    """A packed 500 page is worse than a missing one: it looks like the app is broken offline."""
    client, _ = world
    for path in manifest(client)["pages"]:
        assert "{" not in path, path
        got = client.get(path)
        assert got.status_code == 200, f"{path} answered {got.status_code}"
        assert "text/html" in got.headers["content-type"], path


def test_the_generated_ones_are_named_instead_of_pretending_to_travel(world):
    client, _ = world
    got = manifest(client)
    assert got["generated"] == ["/edit/preview", "/clip/preview"]
    assert not [p for p in got["pages"] if p.startswith("/edit/preview")]


def test_the_registry_knows_the_list_answers_json_rather_than_being_a_page(world):
    """`pages()` keeps the routes that render a template, and the audit is where that reading comes
    from - so the manifest itself has to be recorded as JSON, not as a page and not as nothing."""
    from src.registry import audit
    row = [e for e in audit.routes() if e.key == "route:GET /offline/manifest"][0]
    assert row.outputs == ["answers JSON"]


def test_the_counts_match_the_lists_they_come_from(world):
    client, root = world
    her_photo(root, "one.jpg")
    got = manifest(client)
    assert got["counts"]["pages"] == len(got["pages"])
    assert got["counts"]["files"] == len(got["media"])
    assert got["bytes"] == sum(m["bytes"] for m in got["media"])


# ---- her files, as URLs ----------------------------------------------------


def test_a_photo_on_the_laptop_travels_as_a_url_not_a_path(world):
    client, root = world
    her_photo(root, "tank.jpg")
    got = manifest(client)
    assert [m["url"] for m in got["media"]] == ["/inbox/tank.jpg"]
    assert got["media"][0]["bytes"] == 1024
    assert got["media"][0]["mtime"].endswith("Z")
    body = client.get("/offline/manifest").text
    assert str(root) not in body and "\\inbox" not in body
    assert got["counts"]["too_big"] == 0 and got["too_big"] == []


def test_a_subfolder_travels_under_its_own_name(world):
    client, root = world
    (root / "outputs" / "story").mkdir(parents=True, exist_ok=True)
    (root / "outputs" / "story" / "vo.mp3").write_bytes(b"audio")
    her_photo(root, "inbox.jpg", 10)
    assert [m["url"] for m in manifest(client)["media"]] == ["/inbox/inbox.jpg",
                                                             "/outputs/story/vo.mp3"]


def test_something_too_heavy_for_a_phone_stays_behind_and_says_why(world, monkeypatch):
    client, root = world
    her_photo(root, "tiny.jpg", 10)
    her_photo(root, "huge.mov", 5000)
    monkeypatch.setattr(offline, "MAX_FILE_BYTES", 1000)
    got = manifest(client)
    assert [m["url"] for m in got["media"]] == ["/inbox/tiny.jpg"]
    assert got["counts"]["too_big"] == 1
    assert got["too_big"][0]["url"] == "/inbox/huge.mov"
    assert got["too_big"][0]["bytes"] == 5000 and "bigger than" in got["too_big"][0]["why"]


def test_a_folder_that_was_never_made_is_not_an_error(world):
    client, _ = world
    assert manifest(client)["media"] == []


# ---- the door --------------------------------------------------------------


def test_a_phone_cannot_read_the_list_before_answering_with_the_pin(tmp_path):
    app = create_app(Config(api_key=None, engine_name="offline", model=""),
                     tmp_path / "a.sqlite3")
    got = TestClient(app, client=PHONE).get("/offline/manifest")
    assert got.status_code == 401
    assert "/inbox/" not in got.text, "a refused page must not name a single file of hers"


# ---- what she sees and presses --------------------------------------------


def test_the_phone_page_lets_her_copy_the_whole_app_and_erase_it(world):
    client, _ = world
    body = client.get("/phone").text
    assert "Carry it with you" in body
    assert 'id="pack"' in body and "Copy everything to this phone" in body
    assert 'id="packerase"' in body and "Erase the copy on this phone" in body
    assert "What still needs the laptop" in body


def test_the_size_of_the_promise_is_shown_before_she_taps(world):
    client, root = world
    her_photo(root, "one.jpg")
    got = manifest(client)
    body = client.get("/phone").text
    assert f"{got['counts']['pages']} pages" in body
    assert "1 file" in body and "1 files" not in body, "one photo is not 1 files"
    assert "about 1 KB" in body


def test_the_promise_switches_to_MB_once_it_is_worth_MB(world):
    client, root = world
    her_photo(root, "clip.mp4", 3 * 1024 * 1024)
    assert "about 3.0 MB" in client.get("/phone").text


def test_the_page_that_promises_the_copy_is_the_one_that_installs_the_worker(world):
    """None of this exists on a phone that never registered the worker, so the shell has to keep
    doing it - and ask for the whole site, because a worker that lives under /static and stays
    scoped to /static can store every page and still serve none of them offline."""
    client, _ = world
    shell = (ROOT / "src" / "templates" / "base.html").read_text(encoding="utf-8")
    assert '.register("/static/sw.js", { scope: "/" })' in shell
    assert "no wifi at all" in client.get("/phone").text


def test_the_worker_is_allowed_to_tell_it_what_it_may_control(world):
    """The browser only accepts a scope wider than the script's own folder when the response says
    so; without the header the registration is refused and the app looks online-only forever."""
    client, root = world
    app = create_app(Config(api_key=None, engine_name="offline", model=""),
                     root / "b.sqlite3")
    for visitor in (TestClient(app, client=LAPTOP), TestClient(app, client=PHONE)):
        got = visitor.get("/static/sw.js")
        assert got.status_code == 200
        assert got.headers.get("service-worker-allowed") == "/"
        assert visitor.get("/static/app.css").headers.get("service-worker-allowed") is None


def test_the_shell_labels_a_page_that_came_off_the_phone(world):
    """A screen of last Tuesday's numbers looks exactly like today's, so the worker writes the
    moment of storage into the document and the shell reads it back out loud."""
    client, _ = world
    body = client.get("/today").text
    assert 'id="copystate"' in body and "Offline copy." in body
    assert 'meta[name="fame:stored"]' in body
    assert "fame:ask" not in body, "the worker cannot be asked which copy arrived; it has no client id"


def test_the_worker_writes_the_label_with_an_api_every_phone_has(world):
    """`FetchEvent.resultClientId` is what this looked like before it was tested on a phone: the
    record went in under `undefined` and no page was ever labelled, with nothing to show for it.
    The word may appear in a comment warning about it; the expression may not run."""
    assert "event.resultClientId" not in worker()
    assert '"fame:stored"' in worker()


# ---- the two halves agree --------------------------------------------------


def worker():
    return (ROOT / "src" / "static" / "sw.js").read_text(encoding="utf-8")


def test_the_page_and_the_worker_speak_the_same_protocol(world):
    """The two halves only meet at runtime, so a renamed message would surface as a button that
    appears to do nothing - which this project forbids more than it forbids a missing feature."""
    client, _ = world
    page = client.get("/phone").text
    for verb in ["fame:pack", "fame:status", "fame:erase"]:
        assert f'"{verb}"' in worker(), verb + " is sent but never answered"
        assert verb in page, verb + " is answered but never sent"
    for reply in ["fame:pack:done", "fame:pack:progress", "fame:status", "fame:erased"]:
        assert reply in worker(), reply + " is read by a page but never posted back"


def test_the_worker_packs_from_the_laptop_s_list_not_its_own_guesses(world):
    client, _ = world
    assert '"/offline/manifest"' in worker()
    assert "x-fame-stored" in worker(), "an unlabelled copy cannot be timed when it is served"
    assert "caches.open" in worker() and "navigator.storage.persist" in worker()


def test_the_worker_only_uses_what_a_worker_actually_has():
    """DOMParser is a window API. The pack used it to find the pictures on a page, so every page
    threw, and because the throw sat in the same try as the fetch the Phone page reported a
    laptop that was perfectly reachable as `nothing to reach`."""
    for absent in ["new DOMParser", "document.", "window.", "localStorage", "alert("]:
        assert absent not in worker(), absent + " does not exist in a service worker"


def test_a_pack_failure_says_what_broke(world):
    """The two ways a page fails to pack are the two she can act on: the laptop is asleep, or
    this code is wrong. A message that blames the wifi sends her to the wrong machine."""
    assert "e.message" in worker()


def test_the_cache_has_a_name_that_can_be_changed_when_the_rules_change(world):
    """iOS keeps answering out of an old cache until the name changes, so a versioned name is the
    only way a fixed worker reaches a phone that already packed the broken one."""
    assert 'const KEEP = "fame-strategist-v4"' in worker()
    assert worker().count("caches.delete") >= 2, "the old caches have to be dropped on activate"
