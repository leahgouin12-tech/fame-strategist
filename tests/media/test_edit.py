import json
import random

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


def mean_error(im, out):
    """How far the pixels moved, not how many. A hard edge only needs a few levels left
    behind to still count as changed, so a count alone cannot tell an undo that worked
    from an undo that only softened the bend."""
    hist = ImageChops.difference(im, out).convert("L").histogram()
    return sum(i * hist[i] for i in range(1, 256)) / (im.width * im.height)


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


def test_a_one_lever_control_reaches_the_picture_it_was_switched_on_for():
    """The no-op test used to start reading from the second argument, which threw away
    every control whose only lever is its first one - auto, enlarge, vibrance, clarity -
    with the page still showing the number she set."""
    for name, value in (("auto", 0.75), ("upscale", 3.0), ("vibrance", 0.5), ("clarity", 0.4),
                        ("invert", 1.0), ("posterize", 4.0)):
        got = normalize([[name, value]])
        assert got and got[0][0] == name, f"{name} was dropped before it ran"
        assert got[0][1] == pytest.approx(value)


def test_a_one_lever_control_left_at_zero_is_still_no_work():
    assert normalize([["vibrance", 0.0], ["auto", 0.0], ["invert", 0.0]]) == []


def test_a_heal_cannot_cover_more_than_a_blemish():
    im = frame()
    out = apply(im, [["heal", 0.5, 0.5, 0.9]])  # she asks for a huge patch
    assert changed_fraction(im, out) < 0.12, MAX_SPOT
    assert out.getpixel((8, 8)) == im.getpixel((8, 8))


def speckled():
    """A frame with real high-frequency detail, because a smoothing brush run over a flat
    colour changes nothing and would let an undo brush pass every test by doing nothing."""
    random.seed(11)
    return Image.effect_noise(SIZE, 46).convert("RGB")


def test_the_undo_brush_uncovers_the_skin_the_smudge_covered():
    im = speckled()
    grade = [["exposure", 0.2]]
    flat = apply(im, grade)
    smoothed = apply(im, grade + [["smooth", 0.5, 0.5, 0.24, 1.0]])
    undone = apply(im, grade + [["smooth", 0.5, 0.5, 0.24, 1.0], ["restore", 0.5, 0.5, 0.24]])
    centre = (300, 450)
    took = changed_fraction(flat, smoothed)          # what the smudge changed
    gave = changed_fraction(smoothed, undone)        # what the undo gave back
    assert took > 0.01, "the smudge did nothing for the undo to do"
    assert sum(undone.getpixel(centre)) != sum(smoothed.getpixel(centre)), "the undo did nothing"
    assert undone.getpixel(centre) == flat.getpixel(centre), "it uncovered the pre-brush frame"
    assert gave > 0.8 * took, f"the undo only reached {gave:.3f} of the {took:.3f} she smudged"
    assert changed_fraction(im, undone) > 0.5, "and the grade is still on the picture"


def test_the_undo_brush_leaves_everything_outside_its_stroke_alone():
    im = speckled()
    smoothed = apply(im, [["smooth", 0.5, 0.5, 0.24, 1.0]])
    undone = apply(im, [["smooth", 0.5, 0.5, 0.24, 1.0], ["restore", 0.5, 0.5, 0.16]])
    for spot in ((10, 10), (580, 10), (300, 880), (20, 450), (580, 450)):
        assert undone.getpixel(spot) == smoothed.getpixel(spot), spot


def test_the_undo_brush_runs_after_the_brushes_whatever_order_she_painted_them():
    """The page hands the strokes over in the order they were painted, but an undo laid
    down first still has to undo the smoothing painted after it."""
    retouch_ = [["smooth", 0.5, 0.5, 0.24, 1.0]]
    undo = [["restore", 0.5, 0.5, 0.16]]
    assert [e[0] for e in normalize(retouch_ + undo)] == ["smooth", "restore"]
    assert [e[0] for e in normalize(undo + retouch_)] == ["smooth", "restore"]
    im = speckled()
    assert list(apply(im, undo + retouch_).getdata()) == \
           list(apply(im, retouch_ + undo).getdata())


def test_an_undo_brush_with_nothing_to_undo_does_not_repaint_the_picture():
    im = speckled()
    graded = apply(im, [["exposure", 0.3], ["contrast", 0.4]])
    assert list(apply(im, [["exposure", 0.3], ["contrast", 0.4],
                           ["restore", 0.5, 0.5, 0.2]]).getdata()) == list(graded.getdata())


def test_the_undo_brush_gives_a_warp_back_its_original_shape():
    """The undo brush is an eraser for warps as much as for smoothing, and a bend left
    half-standing is the defect nobody notices until print."""
    im = frame()
    x, y, size = 0.6, 0.7, 0.5
    push = ["warp", x, y, size, 1.0, 0, 0.5, 0.0]
    warped = apply(im, [push])
    undone = apply(im, [push, ["restore", x, y, size]])
    bent = mean_error(im, warped)
    assert bent > 0.2, "the warp did not move anything to undo"
    assert mean_error(warped, undone) > 0.8 * bent, "the undo barely touched the warp"
    assert mean_error(im, undone) < 0.05 * bent, f"{mean_error(im, undone) / bent:.0%} still bent"


def test_the_undo_brush_is_never_narrower_than_the_brush_it_has_to_erase():
    """Capping the undo below the widest retouch brush leaves a ring of retouch standing
    around the stroke, which reads as the tool working "mostly" and is invisible in a
    preview at phone size."""
    widest = max(cell[2][1] for cell in edit.retouch.CLAMP.values())
    assert edit.retouch.MAX_UNDO >= widest


def test_the_undo_brush_is_clamped_to_a_brush_and_a_position():
    entry = normalize([["restore", 4.0, -2.0, 40.0]])[0]
    assert entry[1:3] == [1.0, 0.0], "her tap stays inside the frame"
    assert entry[3] == edit.retouch.MAX_UNDO, "the stroke cannot erase the whole picture"
    assert normalize([["restore"], ["restore", "a", "b", "c"]]) == []


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
