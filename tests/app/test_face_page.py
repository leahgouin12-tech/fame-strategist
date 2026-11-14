"""The face page, driven the way she drives it: pick, read, tap, resize.

Registry said this route was the last endpoint no test named. Writing the test found the
one sentence the page got wrong - with three photos in the inbox and no name typed it told
her "Nothing in the inbox yet" - which is fixed below and covered here. Everything asserted
is what the page actually printed: the numbers come from the same measurement the template
renders, so a test that passes proves the box on screen is the box that was measured.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.app import create_app
from src.config import Config
from src.media.appearance import read_file
from tests.media.test_appearance import face_frame, wall_frame

BANNED = ("/10", "out of 10", "rating", "attractive", "ugly", "stars", "hotness", "score:")


def a_client(db_path, pictures=True):
    inbox = Path(db_path).parent / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    if pictures:
        face_frame().save(inbox / "selfie.jpg", "JPEG", quality=92)
        wall_frame().save(inbox / "brick.jpg", "JPEG", quality=92)
        Image.new("RGB", (300, 400), (90, 92, 96)).save(inbox / "flat.jpg", "JPEG", quality=92)
    return TestClient(create_app(Config(api_key=None, engine_name="offline", model=""), db_path))


@pytest.fixture
def world(tmp_path):
    return a_client(tmp_path / "face.sqlite3")


def one_line(text: str) -> str:
    """Markup with the attributes broken across lines, readable as one string."""
    return re.sub(r"\s+", " ", text)


def box_of(html: str) -> dict:
    """The percentages the page drew the box with."""
    span = re.search(r'class="facebox" style="left: ([\d.]+)%; top: ([\d.]+)%;\s*'
                     r'width: ([\d.]+)%; height: ([\d.]+)%"', html)
    assert span, "no box was drawn"
    left, top, width, height = (float(x) for x in span.groups())
    return {"left": left, "top": top, "width": width, "height": height}


def test_the_page_offers_every_photo_in_the_inbox(world):
    body = world.get("/face").text
    for name in ("selfie.jpg", "brick.jpg", "flat.jpg"):
        assert f'href="/face?name={name}"' in body, name
    assert "How this page works." in body


def test_an_empty_inbox_says_so_and_a_full_one_does_not(tmp_path):
    body = a_client(tmp_path / "face.sqlite3").get("/face").text
    assert "Pick a photo first." in body
    assert "Nothing in the inbox yet" not in body
    empty = a_client(tmp_path / "empty" / "face.sqlite3", pictures=False).get("/face").text
    assert "Nothing in the inbox yet" in empty
    assert "Pick a photo first." not in empty


def test_a_name_that_is_not_a_photo_is_named_not_measured(world):
    body = world.get("/face?name=nope.jpg").text
    assert "Pick a photo first." in body
    assert "What was measured" not in body


def test_a_name_pointing_out_of_the_inbox_is_refused(world, tmp_path):
    Image.new("RGB", (300, 400), (200, 160, 130)).save(tmp_path / "outside.jpg", "JPEG")
    body = world.get("/face?name=../outside.jpg").text
    assert "Pick a photo first." in body
    assert "What was measured" not in body, "a path she typed is never opened"


def test_the_contract_sits_above_the_numbers_not_in_a_footnote(world):
    body = world.get("/face?name=selfie.jpg").text
    assert "does not score your face" in body
    assert body.index("does not score your face") < body.index("What was measured")


def test_the_face_is_read_as_numbers_a_photographer_can_change(world):
    body = world.get("/face?name=selfie.jpg").text
    for row in ("Skin in the box", "Dark band", "Light fall", "Mirror difference",
                "Colour spread", "Sharpness vs frame", "Backdrop vs face"):
        assert row in body, row
    assert "found by colour" in body


def test_the_box_drawn_is_the_box_measured(world, tmp_path):
    read = read_file(tmp_path / "inbox" / "selfie.jpg")
    got = box_of(world.get("/face?name=selfie.jpg").text)
    w, h = read.frame
    for key, want in (("left", read.box[0] / w * 100), ("top", read.box[1] / h * 100),
                      ("width", (read.box[2] - read.box[0]) / w * 100),
                      ("height", (read.box[3] - read.box[1]) / h * 100)):
        assert abs(got[key] - want) < 0.01, key


def test_a_tap_overrules_the_detector_and_the_page_says_who_chose_it(world):
    auto = world.get("/face?name=selfie.jpg").text
    tapped = world.get("/face?name=selfie.jpg&fx=0.5&fy=0.9").text
    assert "found by colour" in auto
    assert "This box is the one you placed." in tapped
    assert "Measured inside the box you placed" in tapped
    assert box_of(auto) != box_of(tapped), "her tap did not move the box"


def test_a_tap_on_a_wall_measures_the_wall_and_labels_it_as_hers(world):
    body = world.get("/face?name=brick.jpg&fx=0.5&fy=0.5").text
    assert "the box you placed" in body
    assert "Skin in the box" in body, "the numbers are still measured, just elsewhere"


def test_the_size_chip_redraws_bigger_and_keeps_her_tap(world):
    """The same tap at two box sizes: her finger stays, the window it measures grows."""
    tight = box_of(world.get("/face?name=selfie.jpg&fx=0.5&fy=0.9&size=0.12").text)
    close = one_line(world.get("/face?name=selfie.jpg&fx=0.5&fy=0.9&size=0.40").text)
    assert box_of(close)["width"] > tight["width"] * 2, f"{tight} -> {box_of(close)}"
    assert 'class="chip on" href="/face?name=selfie.jpg&size=0.4&fx=0.5&fy=0.9">close-up' in close
    assert "Measured inside the box you placed" in close


def test_a_frame_with_no_face_in_it_explains_without_blaming_her(world):
    body = world.get("/face?name=flat.jpg").text
    assert "not an error" in body
    assert "Tap the photo on her face" in body
    assert "What was measured" not in body
    assert not re.search(r'class="facebox"', body), "a frame with no face gets no box"


def test_the_picture_itself_is_the_tap_target(world):
    body = world.get("/face?name=selfie.jpg").text
    assert 'id="tapframe"' in body
    assert re.search(r'addEventListener\("click"', body)
    assert "&fx=" in body, "the tap has to reach the server that re-measures"


def test_no_page_here_rates_her(world):
    for url in ("/face", "/face?name=selfie.jpg", "/face?name=selfie.jpg&fx=0.5&fy=0.9",
                "/face?name=brick.jpg", "/face?name=flat.jpg"):
        body = world.get(url).text
        for word in BANNED:
            assert word not in body.lower(), f"{word} on {url}"


def test_the_nav_carries_it(world):
    assert "/face" in world.get("/today").text
