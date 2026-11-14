"""The appearance judge: measured, described, never scored.

These tests are written against synthetic frames rather than her photos so the
contract holds whatever the camera did: a face-shaped region is found, a wall is
not, and no path through this module can produce a number that reads as a verdict
on a person.
"""

import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from src.media.appearance import (
    CONTRACT, FaceRead, _blobs, _merge, _plausible, _skin_mask, face_box, light_box,
    read_file, tap_box,
)


def face_frame(size=(300, 400), bg=(120, 118, 116)):
    """A stand-in frame: a skin-coloured oval with two dark bands across it."""
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    cx, cy = size[0] // 2, int(size[1] * 0.28)
    w, h = int(size[0] * 0.26), int(size[1] * 0.20)
    d.ellipse([cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2], fill=(206, 168, 142))
    for dy in (-int(h * 0.18), int(h * 0.30)):
        d.rectangle([cx - w // 3, cy + dy, cx + w // 3, cy + dy + max(3, h // 12)],
                    fill=(60, 45, 40))
    return im


def wall_frame(size=(300, 400)):
    """The failure this module has to survive: a brick wall the colour of a face."""
    im = Image.new("RGB", size, (150, 122, 108))
    d = ImageDraw.Draw(im)
    for y in range(0, size[1], 24):
        d.line([(0, y), (size[0], y)], fill=(120, 96, 84), width=2)
    return im


def cool_frame(size=(300, 400)):
    """The frame the colour rule cannot read: a graded, underexposed street photo where the
    face is neutral grey-blue and only the light tells you where it is."""
    im = Image.new("RGB", size, (40, 42, 46))
    d = ImageDraw.Draw(im)
    cx, cy = int(size[0] * 0.52), int(size[1] * 0.19)
    w, h = int(size[0] * 0.15), int(size[1] * 0.13)
    d.ellipse([cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2], fill=(150, 150, 152))
    return im


def write(tmp_path, im, name="f.jpg"):
    p = Path(tmp_path) / name
    im.save(p, format="JPEG", quality=92)
    return p


def test_a_face_shaped_region_is_found():
    im = face_frame()
    box = face_box(im)
    assert box is not None
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    assert abs(cx - im.size[0] / 2) < im.size[0] * 0.18
    assert abs(cy - im.size[1] * 0.28) < im.size[1] * 0.18


def test_a_whole_frame_of_colour_is_not_called_a_face():
    # A wall the colour of skin fills the frame; a face never does, and that is the gate.
    assert face_box(wall_frame()) is None


def test_a_cool_dark_frame_is_placed_by_light_when_colour_fails():
    im = cool_frame()
    assert face_box(im) is None, "the colour rule was supposed to find nothing here"
    box = light_box(im)
    assert box is not None
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    assert abs(cx - im.size[0] * 0.52) < im.size[0] * 0.12
    assert abs(cy - im.size[1] * 0.19) < im.size[1] * 0.12


def test_a_light_guess_says_it_is_a_guess(tmp_path):
    read = read_file(write(tmp_path, cool_frame()))
    assert read.found and read.placed == "guessed from the light"
    assert "found by colour" not in " ".join(read.words)
    assert any("tap the face" in w.lower() for w in read.words)


def test_a_flat_frame_offers_no_box_at_all(tmp_path):
    """No light, no colour, no face: the page has to refuse rather than box the middle."""
    im = Image.new("RGB", (300, 400), (90, 92, 96))
    read = read_file(write(tmp_path, im))
    assert not read.found
    assert "tap the face" in " ".join(read.words).lower()


def test_plausible_rejects_a_box_that_is_the_picture():
    im = face_frame()
    assert not _plausible(im, (0, 0, 300, 400))
    assert _plausible(im, (120, 80, 190, 180))


def test_merge_joins_parts_of_one_face_and_leaves_a_distant_wall_alone():
    mask = Image.new("L", (100, 100), 0)
    px = mask.load()
    for x in range(20, 30):
        for y in range(20, 40):
            px[x, y] = 255
    for x in range(31, 40):
        for y in range(22, 38):
            px[x, y] = 255
    for x in range(80, 95):
        for y in range(70, 95):
            px[x, y] = 255
    groups = _merge(_blobs(mask))
    assert len(groups) == 2


def test_tap_places_the_box_where_she_said():
    im = face_frame()
    box = tap_box(im, 0.5, 0.28, size=0.22)
    assert box[0] <= im.size[0] * 0.5 <= box[2]
    assert box[1] <= im.size[1] * 0.28 <= box[3]


def test_a_tap_on_a_wall_measures_the_wall_and_says_so(tmp_path):
    p = write(tmp_path, wall_frame())
    read = read_file(p, tap=(0.5, 0.5), size=0.22)
    assert read.found and read.placed == "you placed it"
    assert any("box you placed" in w for w in read.words)


def test_no_path_through_this_module_produces_a_score(tmp_path):
    p = write(tmp_path, face_frame())
    read = read_file(p)
    assert not hasattr(read, "score")
    text = " ".join(read.words + read.fixes) + CONTRACT
    for banned in ("rating", "attractive", "ugly", "out of 10", "/10", "stars"):
        assert banned not in text.lower()
    # The one place the word "score" may appear is the sentence that refuses to give one.
    assert text.lower().count("score") == 1
    assert "does not score your face" in text


def test_the_contract_is_on_the_page_not_buried():
    assert "does not score your face" in CONTRACT


def test_a_face_is_described_in_numbers_a_photographer_can_change(tmp_path):
    p = write(tmp_path, face_frame())
    read = read_file(p)
    assert read.light_fall is not None
    assert read.clarity is not None
    assert read.backdrop is not None
    assert read.share > 0


def test_an_unmeasurable_frame_says_why_without_blaming_her(tmp_path):
    im = Image.new("RGB", (200, 200), (30, 30, 30))
    p = write(tmp_path, im)
    read = read_file(p)
    assert not read.found
    assert "not an error" in " ".join(read.words)


def test_skin_mask_prefers_the_oval_to_the_backdrop():
    im = face_frame()
    small = im.resize((75, 100))
    mask = _skin_mask(small)
    inside = sum(1 for p in mask.crop((30, 22, 45, 40)).getdata() if p)
    outside = sum(1 for p in mask.crop((0, 80, 15, 99)).getdata() if p)
    assert inside > outside


def test_offline_engine_is_not_quietly_asked_about_the_picture(tmp_path):
    from src.engines.offline import OfflineEngine

    p = write(tmp_path, face_frame())
    read = read_file(p, engine=OfflineEngine())
    assert read.model_says == ""
    assert read.model_source == "not asked"


class Describing:
    name = "test-model"

    def __init__(self, answer):
        self.answer = answer
        self.images = None

    def complete_json(self, system, user, schema, images=None):
        self.images = images
        return self.answer


def test_a_live_model_is_shown_the_crop_and_labelled_as_describing(tmp_path):
    p = write(tmp_path, face_frame())
    engine = Describing({"lighting": "flat", "framing": "tight",
                         "what_changed_it": ["move the light"], "refuses": "nothing"})
    read = read_file(p, engine=engine)
    assert engine.images and engine.images[0][0] == "image/jpeg"
    assert read.model_source.startswith("test-model")
    assert "flat" in read.model_says


def test_a_model_that_answers_nothing_is_reported_as_answering_nothing(tmp_path):
    p = write(tmp_path, face_frame())
    read = read_file(p, engine=Describing({}))
    assert read.model_says == ""
    assert "empty" in read.model_source


def test_a_model_that_raises_does_not_take_the_page_down(tmp_path):
    class Explodes(Describing):
        def complete_json(self, *a, **k):
            raise RuntimeError("network gone")

    p = write(tmp_path, face_frame())
    read = read_file(p, engine=Explodes({}))
    assert "got nothing usable" in read.model_source
    assert read.words


def test_face_read_dict_is_json_shaped():
    import json

    assert json.dumps(FaceRead(found=False).as_dict())
