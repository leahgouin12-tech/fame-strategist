import json

import pytest
from PIL import Image, ImageChops, ImageDraw

from src.media import edit
from src.media.edit import MAX_ROTATE, MAX_SPOT, PRESETS, SLIDERS, apply, normalize

SIZE = (600, 900)


def frame():
    im = Image.new("RGB", SIZE, (120, 130, 140))
    d = ImageDraw.Draw(im)
    d.rectangle([60, 60, 300, 400], fill=(240, 20, 30))
    d.ellipse([320, 500, 520, 760], fill=(20, 200, 120))
    return im


def changed_fraction(im, out):
    hist = ImageChops.difference(im, out).convert("L").histogram()
    return sum(hist[3:]) / (im.width * im.height)


@pytest.mark.parametrize("op", SLIDERS, ids=[op.name for op in SLIDERS])
def test_every_control_runs_and_leaves_a_whole_picture(op):
    im = frame()
    args = [op.hi]
    if op.name == "lens_blur":
        args += [0.5, 0.5, 0.4]
    out = apply(im, [[op.name] + args])
    assert out.mode == "RGB"
    if op.name == "rotate":
        assert out.width < im.width and out.height < im.height, "straightening crops in"
    else:
        assert out.size == im.size
    assert changed_fraction(im, out) > 0, f"{op.name} at its limit must actually do something"


def test_a_hand_edited_recipe_cannot_push_a_control_past_its_range():
    got = {e[0]: e[1] for e in normalize([["exposure", 99], ["saturation", -99], ["rotate", -400]])}
    assert got["exposure"] == 1 and got["saturation"] == -1
    assert abs(got["rotate"]) == MAX_ROTATE


def test_geometry_runs_before_tone_whatever_order_it_arrives_in():
    names = [e[0] for e in normalize([["exposure", 0.4], ["rotate", 4], ["heal", 0.5, 0.5, 0.05]])]
    assert names == ["rotate", "exposure", "heal"]


def test_an_unknown_control_is_dropped_rather_than_run():
    assert normalize([["face_slim", 0.9], ["skin_smooth", 1], ["nonsense"]]) == []


FORBIDDEN = ("slim", "reshape", "warp", "liquify", "smooth", "skin", "face", "body",
             "plump", "enlarge", "teeth", "eye", "waist", "leg", "generative", "inpaint")


def test_no_operation_can_reshape_or_resmooth_a_person():
    """The app's own rule, as a test: an edit that changes how she looks is not offered."""
    names = " ".join(edit.APPLIERS)
    for word in FORBIDDEN:
        assert word not in names, f"{word} would change how a person looks"
    assert {edit.OPS[n].group for n in edit.APPLIERS} <= {"frame", "tone", "lens", "heal"}


def test_a_heal_cannot_cover_more_than_a_blemish():
    im = frame()
    out = apply(im, [["heal", 0.5, 0.5, 0.9]])  # she asks for a huge patch
    assert changed_fraction(im, out) < 0.12, MAX_SPOT
    assert out.getpixel((8, 8)) == im.getpixel((8, 8))


def test_a_crop_never_leaves_an_empty_corner():
    im = apply(frame(), [["crop", 0.2, 0.1, 0.9, 0.8]])
    assert im.size == (420, 630)
    assert apply(frame(), [["crop", 0, 0, 0.01, 0.01]]).size == SIZE, "a silly crop is refused"


def ratio_size(recipe):
    out = apply(frame(), recipe)
    return out.width / out.height


def test_a_ratio_chip_lands_on_exactly_that_ratio():
    assert ratio_size([["crop", 4 / 5]]) == pytest.approx(0.8, abs=0.01)
    # The straighten runs first, so the box has to fit what is left, not the original.
    assert ratio_size([["rotate", 6.0], ["crop", 4 / 5]]) == pytest.approx(0.8, abs=0.01)
    assert ratio_size([["crop", 16 / 9]]) == pytest.approx(16 / 9, abs=0.01)


def test_a_saved_heal_stays_where_she_tapped_it():
    recipe = edit.normalize([["heal", 0.82, 0.31, 0.9]])
    assert recipe[0][1:4] == [0.82, 0.31, edit.MAX_SPOT], "position kept, brush clamped"


def test_every_preset_is_a_recipe_the_engine_accepts():
    im = frame()
    for name, recipe in PRESETS.items():
        out = apply(im, recipe)
        assert out.size == im.size, name
        assert changed_fraction(im, out) > 0.01, f"{name} does nothing"


def test_a_recipe_survives_json_and_applies_identically():
    recipe = [["rotate", 3.0], ["exposure", 0.2], ["temperature", -0.4],
              ["heal", 0.3, 0.4, 0.05], ["lens_blur", 0.5, 0.5, 0.4, 0.3]]
    back = json.loads(json.dumps(recipe))
    assert apply(frame(), recipe).tobytes() == apply(frame(), back).tobytes()


def test_the_engine_reads_the_formats_a_phoneactually_gives_her():
    from src.media.judge import IMAGE_SUFFIXES

    for suffix in (".jpg", ".png", ".webp", ".heic", ".avif", ".tif"):
        assert suffix in IMAGE_SUFFIXES
