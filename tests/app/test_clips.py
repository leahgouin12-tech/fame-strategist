"""The clip pages are opened through the real app, against a real encoded file.

Nothing here is mocked: a three-second clip is encoded once with the ffmpeg that ships
with the app, and every assertion is about what comes back from that file.
"""

import io
import json
import os
import re
import subprocess
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.app import create_app
from src.config import Config
from src.media import clip as clipmod

pytestmark = pytest.mark.skipif(not clipmod.available(), reason="the bundled ffmpeg is missing")

TAKE = ["-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32", "-c:a", "aac"]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("clipapp")
    clips = root / "clips"
    clips.mkdir(exist_ok=True)
    dst = clips / "take.mp4"
    subprocess.run([clipmod.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *TAKE,
                    str(dst)], check=True, capture_output=True, text=True, timeout=600)
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   root / "a.sqlite3"))
    return client, root, dst


def test_the_clips_page_names_the_folder_it_reads(world):
    client, root, _ = world
    body = client.get("/clips").text
    assert str(root / "clips") in body
    assert "take.mp4" in body
    assert 'href="/clips"' in body, "the nav has to reach this page"


def test_the_list_reads_headers_only(world):
    client, root, _ = world
    client.get("/clips")
    assert not list((root / "frames").rglob("*.png")), "listing must not decode a single frame"


def test_opening_a_clip_judges_it_in_numbers(world):
    client, _, _ = world
    body = client.get("/clip", params={"name": "take.mp4"}).text
    assert "score" in body and "/ 10" in body
    assert "540×960" in body
    assert "photo-editor job" in body, "the page says where a reshape is actually done"


def test_the_strip_shows_the_frames_the_judge_already_decoded(world):
    """Opening a clip used to ask ffmpeg for those five frames a second time."""
    client, _, _ = world
    urls = re.findall(r'src="(/frames/[^"]+)"', client.get("/clip", params={"name": "take.mp4"}).text)
    assert len(urls) == 5
    got = client.get(urls[0])
    assert got.status_code == 200 and got.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(got.content)) as im:
        assert im.height > im.width, "the strip shows the frame as the file holds it"


def test_the_preview_holds_the_geometry_the_recipe_asked_for(world):
    client, _, _ = world
    ops = '[["ratio",0.8],["brightness",0.2],["rotate",4]]'
    got = client.get("/clip/preview", params={"name": "take.mp4", "ops": ops, "t": 1.0})
    assert got.status_code == 200
    with Image.open(io.BytesIO(got.content)) as im:
        assert abs(im.width / im.height - 0.8) < 0.02


def test_saving_a_cut_writes_a_copy_and_leaves_the_original_alone(world):
    client, root, src = world
    before = src.stat().st_size
    saved = client.post("/clip/save", data={"name": "take.mp4", "recipe": '[["trim",0,1.5]]'},
                        follow_redirects=False)
    assert saved.status_code == 303
    assert "edited%2F" in saved.headers["location"] or "edited/" in saved.headers["location"]
    copies = list((root / "clips" / "edited").glob("*.mp4"))
    assert copies, "the copy lands in clips/edited"
    after = clipmod.probe(copies[0])
    assert after.duration == pytest.approx(1.5, abs=0.3)
    assert (root / "clips" / "edited" / f"{copies[0].stem}.json").is_file()
    assert src.stat().st_size == before, "the original is never rewritten"


def test_the_cover_button_hands_the_frame_to_the_photo_editor(world):
    client, root, _ = world
    got = client.post("/clip/cover", data={"name": "take.mp4", "t": 1.0}, follow_redirects=False)
    assert got.status_code == 303 and got.headers["location"].startswith("/edit?name=")
    stills = list((root / "inbox").glob("take-cover*.jpg"))
    assert stills, "the frame is saved as a photo"
    with Image.open(stills[0]) as im:
        assert (im.width, im.height) == (540, 960)


def test_preview_states_are_keyed_by_their_controls(world):
    """Both used to land on one file named after the clip alone, so a drag could be served a
    half-written picture of a different state."""
    client, root, _ = world
    one = client.get("/clip/preview", params={"name": "take.mp4", "ops": '[["ratio",0.8]]',
                                              "t": 1.0}).content
    two = client.get("/clip/preview", params={"name": "take.mp4", "ops": "[]", "t": 1.0}).content
    assert one != two, "different controls, different picture"
    with Image.open(io.BytesIO(one)) as im:
        assert abs(im.width / im.height - 0.8) < 0.02
    assert client.get("/clip/preview", params={"name": "take.mp4", "ops": '[["ratio",0.8]]',
                                              "t": 1.0}).content == one, \
        "a state she has already looked at is read back from disk"
    names = {p.name for p in (root / "frames" / "preview").glob("clips-take-*.png")}
    assert len(names) >= 2


def test_a_long_session_does_not_fill_the_disk_with_frames(world):
    client, root, _ = world
    folder = root / "frames" / "preview"
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(40):
        stale = folder / f"clips-take-old{i:02d}.png"
        stale.write_bytes(b"x")
        os.utime(stale, (1_600_000_000 + i, 1_600_000_000 + i))
    client.get("/clip", params={"name": "take.mp4"})
    left = list(folder.glob("clips-take-*.png"))
    assert len(left) <= 24, f"the newest states are what she compares; {len(left)} were kept"
    assert any(p.name.startswith("clips-take-old3") for p in left), "newest wins, not first"


def test_a_saved_cut_is_painted_with_its_edit_already_applied(world):
    """Opening a saved cut asked for the raw frame and then for the edited one - two full
    decodes of a clip whose controls are already known when the page is built."""
    client, _, _ = world
    saved = client.post("/clip/save", data={"name": "take.mp4",
                                           "recipe": '[["ratio",0.8],["rotate",3]]'},
                        follow_redirects=False)
    name = parse_qs(urlparse(saved.headers["location"]).query)["name"][0]
    src = re.search(r'id="clipshot" src="([^"]+)"',
                    client.get("/clip", params={"name": name}).text).group(1)
    ops = json.loads(parse_qs(urlparse(src).query)["ops"][0])
    assert [e[0] for e in ops] == ["rotate", "ratio"], "the first paint is the edit, not the raw file"


def test_a_saved_cut_shows_its_own_frames_not_the_originals(world):
    """`edited/take.mp4` keeps the stem of the file it came from, so frames cached under the
    stem alone would hand her the wrong picture."""
    client, _, _ = world
    before = set(re.findall(r'src="(/frames/[^"]+)"',
                            client.get("/clip", params={"name": "take.mp4"}).text))
    saved = client.post("/clip/save", data={"name": "take.mp4", "recipe": '[["ratio",1.0]]'},
                        follow_redirects=False)
    name = parse_qs(urlparse(saved.headers["location"]).query)["name"][0]
    after = set(re.findall(r'src="(/frames/[^"]+)"', client.get("/clip", params={"name": name}).text))
    assert before and after and not (before & after), "the two files keep separate frames"
    with Image.open(io.BytesIO(client.get(sorted(after)[0]).content)) as im:
        assert im.width == im.height, "the copy is the square the recipe asked for"


def test_a_name_that_reaches_outside_the_clips_folder_is_refused(world):
    client, _, _ = world
    assert "Pick a clip first" in client.get("/clip", params={"name": "../a.sqlite3"}).text
    body = client.post("/clip/save", data={"name": "../../windows/win.ini",
                                           "recipe": "[]"}).text
    assert "not in the clips folder" in body


def test_a_file_that_is_not_a_video_is_refused_before_it_is_stored(world):
    client, root, _ = world
    body = client.post("/clips/upload", files={"file": ("notes.txt", b"not a video", "text/plain")}).text
    assert "is not a video this app can read" in body
    assert list((root / "clips").glob("*.txt")) == []
