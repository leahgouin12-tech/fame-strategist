"""The repurposing page, driven the way she would drive it after a week in the lab: open it,
see which ranked posts this app can actually touch, press the button, and find crops on disk.

What these tests hold is that the page never sells a pass that did not happen. The button is
only drawn when something is ranked; a press writes files or writes nothing and says which;
every cut it shows is a file the app then serves back and opens in the editor; and a second
press works from her original, not from the crop the first press made.
"""

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.app import create_app
from src.config import Config

COMPLETE = {
    "hours_per_week": "6",
    "existing_followers": "0",
    "what_you_actually_film": "outfits in my room and the odd street clip",
    "gear": "phone",
    "has_clips": "on",
    "on_camera": "on",
    "platforms": ["tiktok", "reels"],
    "comfort": ["talking", "text on screen"],
}

HEADERS = "post_ref,views,avg_watch_pct,follows_gained,hypothesis,posted_at"


@pytest.fixture
def world(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "repurpose.sqlite3"))
    client.folder = tmp_path
    client.inbox = tmp_path / "inbox"
    client.edited = tmp_path / "inbox" / "edited"
    return client


def flat(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(html))


def plan_built(client):
    client.post("/interview", data=COMPLETE)
    client.post("/plan/build")
    plan = client.app.state.kit.plan()
    return plan.weeks[0].experiment, plan.weeks[1].experiment


def store(client, rows):
    """The ledger's own CSV, so the page reads the numbers exactly as the lab left them."""
    (client.folder / "metrics-last.csv").write_text(
        HEADERS + "\n" + "\n".join(f"{ref},{views},{watch},{gained},{arm},"
                                   for ref, views, watch, gained, arm in rows) + "\n",
        encoding="utf-8")


def put(client, name, size=(1200, 1600)):
    """A real picture in the inbox folder - the only thing that can become a cut."""
    client.inbox.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (180, 120, 90)).save(client.inbox / name, "JPEG")


def ranked(world, with_file=True):
    arm, other = plan_built(world)
    if with_file:
        put(world, "a0.jpg")
    store(world, [("a0.jpg", 1000, 30.0, 14, arm), ("a1.jpg", 1000, 30.0, 9, arm),
                  ("b0.jpg", 1000, 30.0, 4, other)])
    return arm, other


def test_the_page_lists_the_posts_the_ledger_ranks_and_which_files_it_can_see(world):
    arm, other = ranked(world)
    body = flat(world.get("/repurpose").text)
    assert "Repurposing" in body
    assert arm in body and other in body, "each candidate carries the hypothesis it ran under"
    assert "photo · a0.jpg" in body, "the row that has a file says which file it would cut"
    assert body.count("not in this app") == 2, "the rows without one say so in the same table"
    assert "3 labelled posts across 2 arms" in body


def test_running_the_pass_writes_the_crops_it_claims(world):
    ranked(world)
    body = flat(world.post("/repurpose/run").text)
    written = sorted(p.name for p in world.edited.iterdir())
    assert written == ["a0-1x1.jpg", "a0-9x16.jpg"], \
        "two shapes, not three files: tiktok and reels want the same frame"
    assert Image.open(world.edited / "a0-9x16.jpg").size == (900, 1600)
    assert Image.open(world.edited / "a0-1x1.jpg").size == (1200, 1200)
    assert "3 cuts from 1 post the ledger already ranked." in body
    for name in written:
        assert name in body, "every file the pass wrote is named on the page that wrote it"


def test_the_page_shows_the_shape_each_copy_was_written_for(world):
    ranked(world)
    raw = world.post("/repurpose/run").text
    body = flat(raw)
    for platform in ("tiktok", "reels", "x"):
        assert f'<span class="chip post">{platform}</span>' in raw, \
            f"no card was drawn for {platform}"
    assert "9:16" in body and "1:1" in body
    assert "from a0.jpg" in body and "ran under" in body, \
        "a cut with no original named on it cannot be checked"


def test_a_cut_is_a_file_the_app_serves_and_the_editor_opens(world):
    """The page links each crop to its own image and to the editor. A link that 404s would be
    a button that does nothing, one file short of a deliverable."""
    ranked(world)
    world.post("/repurpose/run")
    for name in ("a0-9x16.jpg", "a0-1x1.jpg"):
        got = world.get(f"/inbox/edited/{name}")
        assert got.status_code == 200 and got.content[:2] == b"\xff\xd8", f"{name} is not a jpeg"
        page = world.get(f"/edit?name=edited/{name}").text
        assert 'id="stage"' in page, "the editor link did not land in the editor"
        assert name in page


def test_a_second_pass_cuts_the_original_not_the_crop_it_made(world):
    ranked(world)
    world.post("/repurpose/run")
    body = flat(world.post("/repurpose/run").text)
    assert "a0-9x16-2.jpg" in body, "the second pass adds, it never overwrites the first"
    assert "from a0.jpg" in body
    assert not [p for p in world.edited.iterdir() if "9x16-9x16" in p.name], \
        "a cut fed back as a source would shrink her best post every time she pressed the button"


def test_the_posts_it_had_to_leave_out_are_named_on_the_page(world):
    ranked(world)
    body = flat(world.post("/repurpose/run").text)
    assert "Left out, and why" in body
    for ref in ("a1.jpg", "b0.jpg"):
        assert f"{ref} ran under" in body, f"{ref} was skipped silently"
    assert "Put it in the inbox folder" in body, "the refusal has to carry the fix"


def test_a_pass_with_nothing_on_the_shelf_writes_no_file_and_says_so(world):
    ranked(world, with_file=False)
    body = flat(world.post("/repurpose/run").text)
    assert "Nothing was written." in body
    assert "holds none of the files" in body
    assert body.count("does not hold the file") == 3, "all three ranked posts are accounted for"
    assert not world.edited.exists() or list(world.edited.iterdir()) == []


def test_nothing_is_offered_to_rebuild_before_the_lab_has_ranked_anything(world):
    body = flat(world.get("/repurpose").text)
    assert 'action="/repurpose/run"' not in body
    assert "Nothing to rebuild yet" in body
    assert 'href="/numbers"' in body and 'href="/lab"' in body, "the way out is on the page"


def test_the_original_is_left_alone_and_only_the_copy_is_cut(world):
    ranked(world)
    before = (world.inbox / "a0.jpg").read_bytes()
    world.post("/repurpose/run")
    assert (world.inbox / "a0.jpg").read_bytes() == before
    assert sorted(p.name for p in world.inbox.iterdir() if p.is_file()) == ["a0.jpg"], \
        "the pass writes beside her files, never into the folder she uploaded to"


def test_the_rail_reaches_it_like_every_other_room(world):
    assert 'href="/repurpose"' in world.get("/today").text
