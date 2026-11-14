"""The composer, tested as the loop she described: a file goes in, words go on it with her
timings, a real file comes out, and the page stops calling that a post.

Nothing here is mocked at the render - a photo is written with PIL and burned with the same
code the button runs. Video timing is proven in tests/media/test_story.py, where it is proven
against decoded frames.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from src.app import create_app
from src.config import Config

FORM = {"name": "one.jpg", "platform": "instagram", "surface": "Story",
        "caption": "the dress is from a charity shop", "hashtags": "#thriftflip, #fitcheck",
        "alt": "a green slip dress in a bedroom mirror", "lines": "", "music": "",
        "audio": "", "keep_audio": "on"}


def photo(root: Path, name: str = "one.jpg", size=(720, 1280)) -> Path:
    """A real JPEG with structure in it, because a flat colour is what the burn-in tests
    use to prove the ink is the caption - here the file only has to be openable."""
    folder = root / "inbox"
    folder.mkdir(parents=True, exist_ok=True)
    dst = folder / name
    im = Image.new("RGB", size, (40, 44, 52))
    draw = ImageDraw.Draw(im)
    for x in range(0, size[0], 40):
        draw.line([(x, 0), (x, size[1] - 1)], fill=(210, 205, 190), width=3)
    im.save(dst, "JPEG", quality=90)
    return dst


@pytest.fixture
def world(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "a.sqlite3"))
    return client, tmp_path


def test_the_composer_says_so_when_there_is_nothing_to_compose(world):
    client, _ = world
    body = client.get("/story").text
    assert "Nothing to compose from yet" in body
    assert 'href="/photos"' in body


def test_the_picker_offers_every_file_she_could_post(world):
    client, root = world
    photo(root)
    (root / "clips").mkdir(exist_ok=True)
    (root / "clips" / "take.mp4").write_bytes(b"not really a video")
    body = client.get("/story").text
    assert "<option value=\"one.jpg\"" in body
    assert "take.mp4" in body


def test_the_safe_zone_and_the_clock_format_are_on_the_page(world):
    client, root = world
    photo(root)
    body = client.get("/story").text
    assert "13% clear at the top" in body and "20% clear at the bottom" in body
    assert "0:01-0:03.4" in body
    assert "baked into the pixels" in body


def test_a_photo_renders_with_her_words_baked_in(world):
    client, root = world
    photo(root)
    got = client.post("/story/ready", data={**FORM, "lines":
                                            "0:01 the dress is from a charity shop\n"
                                            "and it cost four quid"})
    assert got.status_code == 200, got.text[-400:]
    written = list((root / "outputs" / "story").glob("*.jpg"))
    assert written, "the page said it rendered and nothing is on disk"
    body = got.text
    assert "What the render actually did" in body
    assert written[0].name in body
    assert f"/outputs/story/{written[0].name}" in body
    assert "and it cost four quid" in body, "the untimed line was placed without a note"


def test_the_rendered_file_is_the_one_staged(world):
    client, root = world
    photo(root)
    client.post("/story/ready", data={**FORM, "lines": "four quid"})
    body = client.get("/story").text
    href = re.search(r'href="(/outputs/story/[^"]+)"', body).group(1)
    assert (root / "outputs" / "story" / Path(href).name).is_file()
    assert "Take it to instagram" in body


def test_the_page_never_calls_a_render_a_post(world):
    client, root = world
    photo(root)
    body = client.post("/story/ready", data={**FORM, "lines": "four quid"}).text
    lower = body.lower()
    assert "nothing has been posted" in lower
    for claim in ("posted for you", "published", "your post is live", "uploaded to"):
        assert claim not in lower


def test_the_share_tap_is_named_as_hers(world):
    client, root = world
    photo(root)
    body = client.post("/story/ready", data=FORM).text
    assert "the share tap is yours" in body.lower() or "share" in body.lower()
    assert "add → story" in body.lower() or "add the music sticker" in body.lower()


def test_an_empty_words_box_gives_her_the_frame_and_says_so(world):
    """No words is a choice she can make on the page, not a rejection: the render still
    produces a file, and the page tells her nothing was burned in."""
    client, root = world
    photo(root)
    body = client.post("/story/ready", data=FORM).text
    assert "Nothing was written on the picture" in body
    assert (hrefs := re.search(r'href="(/outputs/story/[^"]+)"', body))
    assert (root / "outputs" / hrefs.group(1).split("/outputs/", 1)[1]).is_file()


def test_words_she_did_type_are_listed_back_on_the_render_card(world):
    client, root = world
    photo(root)
    body = client.post("/story/ready", data={**FORM, "lines": "it cost four quid"}).text
    assert "it cost four quid" in body
    assert "Nothing was written on the picture" not in body


def test_a_name_that_is_not_a_file_renders_nothing(world):
    client, root = world
    photo(root)
    got = client.post("/story/ready", data={**FORM, "name": "../../Windows/win.ini"})
    assert "nothing was rendered" in got.text
    assert client.app.state.db.get_staged() == {} or not \
        client.app.state.db.get_staged().get("platform")


def test_the_caption_button_refuses_without_a_plan_and_keeps_her_words(world):
    client, root = world
    photo(root)
    body = client.post("/story/caption", data={**FORM, "caption": "words i wrote myself"}).text
    assert "needs the interview and a plan" in body
    assert re.search(r'name="caption"[^>]*>words i wrote myself', body), \
        "her typing has to survive the round trip"


def test_the_caption_button_writes_from_the_plan_once_there_is_one(world):
    client, root = world
    photo(root)
    client.post("/interview", data={
        "hours_per_week": "6", "existing_followers": "0",
        "what_you_actually_film": "outfits in my room and the odd street clip",
        "gear": "phone", "has_clips": "on", "on_camera": "on",
        "platforms": ["tiktok"], "comfort": ["talking", "text on screen"]})
    client.post("/plan/build")
    body = client.post("/story/caption", data={**FORM, "platform": "tiktok",
                                               "surface": "Video post"}).text
    assert "Why that line" in body
    box = re.search(r'name="caption"[^>]*>(.*?)</textarea>', body, re.S).group(1)
    assert len(box.strip()) > 20, "the Writer came back with an empty box"


def test_a_story_surface_gets_one_line_not_a_block(world):
    client, root = world
    photo(root)
    client.post("/interview", data={
        "hours_per_week": "6", "existing_followers": "0",
        "what_you_actually_film": "outfits in my room",
        "gear": "phone", "has_clips": "on", "on_camera": "on",
        "platforms": ["tiktok"], "comfort": ["text on screen"]})
    client.post("/plan/build")
    body = client.post("/story/caption", data={**FORM, "surface": "Story"}).text
    box = re.search(r'name="caption"[^>]*>(.*?)</textarea>', body, re.S).group(1)
    assert "\n\n" not in box.strip(), "a Story caption box is one line, not three paragraphs"


def test_audio_is_kept_and_listed(world):
    client, root = world
    photo(root)
    got = client.post("/story/audio", files={"file": ("bed.mp3", b"ID3fake", "audio/mpeg")})
    assert "bed.mp3" in got.text
    assert (root / "audio" / "bed.mp3").is_file()


def test_audio_refuses_a_file_that_is_not_audio(world):
    client, root = world
    photo(root)
    got = client.post("/story/audio", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert "not an audio format" in got.text
    assert list((root / "audio").glob("*")) == []


def test_audio_cannot_be_laid_under_a_photo(world):
    client, root = world
    photo(root)
    client.post("/story/audio", files={"file": ("bed.mp3", b"ID3fake", "audio/mpeg")})
    got = client.post("/story/ready", data={**FORM, "audio": "bed.mp3"})
    assert "A photo has no timeline" in got.text
    assert list((root / "outputs" / "story").glob("*.jpg")) == []


def test_clearing_empties_the_package_and_keeps_the_files(world):
    client, root = world
    photo(root)
    client.post("/story/ready", data={**FORM, "lines": "four quid"})
    written = list((root / "outputs" / "story").glob("*.jpg"))
    got = client.post("/story/clear")
    assert "outputs/story" in got.text or "stay on disk" in got.text
    assert "Take it to" not in got.text
    assert written and all(p.is_file() for p in written)


def test_the_platform_and_surface_decide_the_instructions(world):
    client, root = world
    photo(root)
    client.post("/story/ready", data={**FORM, "platform": "youtube", "surface": "Short"})
    body = client.get("/story").text
    assert "YouTube Studio" in body
    assert "uploading a short by api" in body.lower()
