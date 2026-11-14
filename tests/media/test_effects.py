import json
import math

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

from src.media.effects import APPLIERS, CLAMP, DEFAULTS, LIMITS, MAX_EDGE, SHAPE, apply

SIZE = (600, 900)

# One argument list per op that must leave the picture exactly as it found it, and one
# that sits at the far end of the op's own range and must visibly do something.
OFF = {
    "auto": [0.0],
    "perspective": [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0],
    "stretch": [0.5, 0.0, 0.2],
    "cutout": [0.0, 0.2, 0.0, 0.0],
    "splash": [0.0, 0.0, 1.0, 0.0],
    "duotone": [0.08, 0.12, 0.16, 0.94, 0.86, 0.75, 0.0],
    "pixelate": [0.5, 0.5, 0.0, 0.0],
    "rays": [0.5, 0.0, 0.6, 0.0],
    "upscale": [1.0],
    "softfocus": [0.0, 0.0],
    "mirror": [0.0, 1.0, 0.0],
}

ON = {
    "auto": [1.0],
    "perspective": [0.18, 0.06, 0.86, 0.02, 1.0, 0.94, 0.0, 1.0],
    "stretch": [0.42, 0.55, 0.1],
    "cutout": [0.35, 0.2, 0.0, 0.0],
    "splash": [120.0, 25.0, 1.0, 1.0],
    "duotone": [0.086, 0.133, 0.235, 0.98, 0.886, 0.667, 1.0],
    "pixelate": [0.5, 0.36, 0.25, 0.1],
    "rays": [0.78, 0.12, 0.7, 0.9],
    "upscale": [2.0],
    "softfocus": [0.8, 0.55],
    "mirror": [0.0, 4.0, 0.2],
}


def frame():
    """Three hues and two tones, so a colour op has something to disagree about."""
    im = Image.new("RGB", SIZE, (150, 150, 150))
    d = ImageDraw.Draw(im)
    d.rectangle([80, 90, 300, 330], fill=(226, 28, 40))
    d.ellipse([330, 520, 560, 760], fill=(28, 196, 96))
    d.rectangle([0, 800, SIZE[0], SIZE[1]], fill=(40, 60, 150))
    return im


def flat():
    """A frame whose luminance only ever covers 100..150."""
    tile = bytes(100 + i % 50 for i in range(256))
    im = Image.frombytes("L", (256, 8), tile * 8)
    return im.resize(SIZE, Image.NEAREST).convert("RGB")


def full_range():
    ramp = Image.linear_gradient("L")
    return ramp.resize(SIZE, Image.NEAREST).convert("RGB")


def backdrop():
    """An even-lit studio wall with something unmistakably not the wall in front of it."""
    im = Image.new("RGB", SIZE, (70, 120, 160))
    d = ImageDraw.Draw(im)
    d.rectangle([220, 330, 380, 590], fill=(238, 232, 220))
    d.ellipse([250, 250, 350, 350], fill=(36, 30, 28))
    return im


def band():
    """A light-on-dark gradient, for a bloom that must not lift the blacks."""
    im = Image.new("L", SIZE)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, SIZE[0], 300], fill=250)
    d.ellipse([220, 180, 380, 340], fill=255)
    return im.convert("RGB")


def changed(im, out):
    """The fraction of the frame that moved - and an alpha channel counts as movement,
    since a cutout leaves the pixels under it alone on purpose."""
    if im.size != out.size:
        return 1.0
    diff = ImageChops.difference(im.convert("RGB"), out.convert("RGB")).convert("L")
    if "A" in im.getbands() or "A" in out.getbands():
        diff = ImageChops.lighter(diff, ImageChops.difference(im.convert("RGBA").getchannel("A"),
                                                              out.convert("RGBA").getchannel("A")))
    return sum(diff.histogram()[3:]) / (im.width * im.height)


def untouched(im, out):
    assert out.size == im.size
    return im.convert("RGB").tobytes() == out.convert("RGB").tobytes()


NAMES = sorted(APPLIERS)


@pytest.mark.parametrize("name", NAMES)
def test_the_contract_tables_all_agree_about_the_same_ops(name):
    assert name in SHAPE and name in CLAMP and name in LIMITS
    shape = SHAPE[name]
    assert shape[0] in ("list", "group")
    assert LIMITS[name] >= 1
    arity = len(shape[1]) if shape[0] == "list" else shape[1]
    assert len(CLAMP[name]) == arity
    assert len(DEFAULTS[name]) == arity
    for kind, span, default in zip(shape[1] if shape[0] == "list" else ["f"] * arity,
                                   CLAMP[name], DEFAULTS[name]):
        assert kind in ("f", "s")
        assert len(span) == 2 and span[0] <= span[1]
        assert span[0] <= default <= span[1]


def test_the_tables_do_not_carry_an_op_the_engine_has_not_got():
    assert set(APPLIERS) == set(SHAPE) == set(CLAMP) == set(LIMITS) == set(DEFAULTS)


@pytest.mark.parametrize("name", NAMES)
def test_a_missing_or_neutral_argument_leaves_every_pixel_alone(name):
    im = frame()
    for args in ([], OFF[name]):
        out = APPLIERS[name](im, args)
        assert untouched(im, out), f"{name} with {args} moved pixels it should not touch"
        assert changed(im, APPLIERS[name](frame(), ON[name])) > 0, f"{name} at its limit does nothing"


@pytest.mark.parametrize("name", NAMES)
def test_an_effect_never_writes_on_the_file_it_was_handed(name):
    im = frame()
    before = im.tobytes()
    apply(im, [[name] + ON[name]])
    assert im.tobytes() == before


@pytest.mark.parametrize("name", NAMES)
def test_an_effect_keeps_the_frame_up_to_its_own_documented_size(name):
    out = APPLIERS["upscale"](frame(), ON["upscale"]) if name == "upscale" else APPLIERS[name](frame(), ON[name])
    assert out.mode == ("RGBA" if name == "cutout" else "RGB")
    assert max(out.size) <= MAX_EDGE
    if name not in ("upscale",):
        assert out.size == SIZE


def test_auto_widens_a_frame_that_uses_a_fifth_of_the_ramp():
    im = flat()
    out = apply(im, [["auto", 1.0]])
    lo, hi = im.convert("L").getextrema()
    widened = out.convert("L").getextrema()
    assert widened[1] - widened[0] > hi - lo
    assert ImageStat.Stat(out.convert("L")).stddev > ImageStat.Stat(im.convert("L")).stddev
    assert changed(im, out) > 0.5


def test_auto_does_nothing_at_all_to_a_frame_that_already_spans_the_ramp():
    im = full_range()
    assert untouched(im, apply(im, [["auto", 1.0]]))
    assert untouched(im, apply(im, [["auto", 0.4]]))


def test_a_strong_auto_cannot_be_pushed_further_than_the_recipe_says():
    im = flat()
    assert apply(im, [["auto", 9.0]]).tobytes() == apply(im, [["auto", 1.0]]).tobytes()


def test_the_default_quad_is_the_identity_and_a_sheared_one_is_not():
    im = frame()
    assert untouched(im, APPLIERS["perspective"](im, [0, 0, 1, 0, 1, 1, 0, 1]))
    sheared = APPLIERS["perspective"](im, [0.1, 0.05, 0.95, 0.0, 1.0, 1.0, 0.0, 0.95])
    assert sheared.size == SIZE
    assert changed(im, sheared) > 0.05
    assert untouched(im, APPLIERS["perspective"](im, [0, 0, 1, 0, 1, 1, 0, 1, 0.5]))


def test_a_keystone_pulls_a_vertical_edge_straight_without_growing_the_frame():
    im = frame()
    out = APPLIERS["perspective"](im, [0.06, 0.0, 0.94, 0.0, 1.0, 1.0, 0.0, 1.0])
    assert out.size == SIZE
    assert changed(im, out) > 0


def test_the_stretch_does_not_move_a_single_row_above_its_line():
    im = frame()
    line = int(round(0.62 * (SIZE[1] - 1)))
    out = apply(im, [["stretch", 0.62, 0.5, 0.18]])
    above = (0, 0, SIZE[0], line)
    assert out.crop(above).tobytes() == im.crop(above).tobytes()
    below = (0, line + 60, SIZE[0], SIZE[1])
    assert out.crop(below).tobytes() != im.crop(below).tobytes()
    assert changed(im, out) > 0.1


def test_a_shortening_and_a_lengthening_stretch_are_not_the_same_picture():
    im = frame()
    long = apply(im, [["stretch", 0.5, 0.5, 0.12]])
    short = apply(im, [["stretch", 0.5, -0.5, 0.12]])
    assert long.tobytes() != short.tobytes()
    assert changed(im, long) > 0 and changed(im, short) > 0


@pytest.mark.parametrize("amount", [-0.9, -0.4, 0.0, 0.4, 0.9])
def test_a_mad_stretch_amount_is_clamped_instead_of_tearing_the_frame(amount):
    im = frame()
    out = apply(im, [["stretch", 0.5, amount, 0.3]])
    assert out.size == SIZE
    assert out.tobytes() != b""


def test_the_cutout_opens_the_backdrop_and_leaves_the_subject_alone():
    im = backdrop()
    out = apply(im, [["cutout", 0.25, 0.15, 0.0, 0.0]])
    assert out.mode == "RGBA"
    alpha = out.getchannel("A")
    assert alpha.getpixel((2, 2)) == 0
    assert alpha.getpixel((300, 460)) == 255
    assert alpha.getpixel((300, 300)) == 255
    assert out.getpixel((300, 460))[:3] == im.getpixel((300, 460)), "the subject is not recoloured"
    assert changed(im, out.convert("RGB")) < 0.75


def test_a_filled_cutout_replaces_the_background_with_the_colour_it_found_at_the_edge():
    im = backdrop()
    out = apply(im, [["cutout", 0.25, 0.1, 1.0, 0.0]])
    assert out.mode == "RGB"
    assert out.getpixel((2, 2)) == im.getpixel((2, 2))
    assert out.getpixel((300, 460)) == im.getpixel((300, 460))
    assert out.getpixel((60, 60)) != im.getpixel((300, 460))


def test_a_hue_on_a_filled_cutout_paints_the_removed_backdrop_not_the_subject():
    im = backdrop()
    plain = apply(im, [["cutout", 0.25, 0.1, 1.0, 0.0]])
    tinted = apply(im, [["cutout", 0.25, 0.1, 1.0, 210.0]])
    assert plain.getpixel((300, 460)) == tinted.getpixel((300, 460))
    assert tinted.getpixel((3, 3)) != plain.getpixel((3, 3))


def test_a_cutout_with_nothing_to_grip_just_returns_the_picture():
    im = frame()
    assert untouched(im, apply(im, [["cutout", 0.0, 0.2, 0.0, 0.0]]))


def test_colour_splash_holds_one_hue_and_drains_the_rest():
    im = frame()
    out = apply(im, [["splash", 0.0, 30.0, 1.0, 1.0]])
    hsv = out.convert("HSV")
    assert hsv.getpixel((190, 210))[1] > 180, "the red square keeps its colour"
    assert hsv.getpixel((445, 640))[1] < 8, "the green blob is grey"
    assert hsv.getpixel((300, 850))[1] < 8, "the blue band is grey"
    assert changed(im, apply(im, [["splash", 120.0, 30.0, 1.0, 1.0]])) > 0


def test_a_splash_that_keeps_everything_at_full_colour_is_a_no_op():
    im = frame()
    assert untouched(im, apply(im, [["splash", 200.0, 60.0, 1.0, 0.0]]))


def test_splash_wraps_around_the_hue_wheel_rather_than_stopping_at_zero():
    im = frame()
    at_zero = apply(im, [["splash", 0.0, 30.0, 1.0, 1.0]])
    at_360 = apply(im, [["splash", 360.0, 30.0, 1.0, 1.0]])
    assert at_zero.convert("HSV").getpixel((190, 210))[1] == \
        at_360.convert("HSV").getpixel((190, 210))[1]


def test_duotone_paints_the_whole_frame_between_its_two_colours():
    im = full_range()
    dark, light = (20, 30, 60), (250, 226, 170)
    endpoints = [c / 255 for c in dark + light]      # the picker sends 0..1, not bytes
    out = apply(im, [["duotone", *endpoints, 1.0]])
    grey = im.convert("L")
    assert out.getpixel((0, 0)) == dark
    assert out.getpixel((0, SIZE[1] - 1)) == light
    mid = out.getpixel((0, SIZE[1] // 2))
    assert dark[0] < mid[0] < light[0]
    assert changed(im, out) > 0.5
    half = apply(im, [["duotone", *endpoints, 0.5]])
    assert changed(im, half) < changed(im, out)


def test_a_kaleidoscope_fold_repeats_a_strip_of_the_photo_itself():
    im = frame()
    out = apply(im, [["mirror", 0.0, 4.0, 0.0]])
    assert out.size == im.size
    strip = im.width // 4
    left = im.crop((0, 0, strip, im.height))
    assert out.crop((0, 0, strip, im.height)).tobytes() == left.tobytes(), \
        "the first panel is the original strip, not a copy of something else"
    assert out.crop((strip, 0, 2 * strip, im.height)).tobytes() == \
        left.transpose(Image.FLIP_LEFT_RIGHT).tobytes(), "the second panel reads backwards"


def test_the_fold_axis_turns_the_repeat_the_way_it_says():
    im = frame()
    across = apply(im.transpose(Image.ROTATE_90), [["mirror", 0.0, 4.0, 0.0]]) \
        .transpose(Image.ROTATE_270)
    assert apply(im, [["mirror", 1.0, 4.0, 0.0]]).tobytes() == across.tobytes()


def test_a_fold_cannot_run_past_eight_panels_and_one_panel_is_no_work():
    im = frame()
    assert apply(im, [["mirror", 0.0, 400.0, 0.0]]).tobytes() == \
        apply(im, [["mirror", 0.0, 8.0, 0.0]]).tobytes()
    assert apply(im, [["mirror", 2.0, 1.0, 0.0]]).tobytes() == im.tobytes()


def test_softening_a_seam_blurs_the_join_and_leaves_the_panel_centres_alone():
    """A mirrored fold is continuous at its joins, so softening one only shows where real
    detail sits against the seam - which is exactly where it is worth seeing."""
    im = Image.new("RGB", SIZE, (150, 150, 150))
    ImageDraw.Draw(im).rectangle([0, 300, 12, 600], fill=(240, 240, 20))
    hard = apply(im, [["mirror", 0.0, 4.0, 0.0]])
    soft = apply(im, [["mirror", 0.0, 4.0, 0.45]])
    strip = im.width // 4
    assert hard.tobytes() != soft.tobytes(), "the seam control does work"
    # a mirrored fold is continuous at its joins, so the second join is where the bar lands
    assert hard.getpixel((2 * strip, 450)) != soft.getpixel((2 * strip, 450)), "join softened"
    assert soft.getpixel((8, 450)) == hard.getpixel((8, 450)), "the panel body is not touched"


def test_mosaic_only_covers_its_disc_and_the_feather_eats_its_edge():
    im = frame()
    out = apply(im, [["pixelate", 0.5, 0.36, 0.25, 0.1]])
    for corner in ((0, 0, 60, 60), (520, 0, 600, 90), (0, 700, 90, 790)):
        assert out.crop(corner).tobytes() == im.crop(corner).tobytes(), "no hard circle somewhere else"
    assert changed(im, out) > 0
    inner = (240, 264, 360, 384)
    blocks = len(out.crop(inner).getcolors(1 << 20) or [])
    blurred = len(im.filter(ImageFilter.GaussianBlur(12)).crop(inner).getcolors(1 << 20) or [])
    assert 2 < blocks < blurred / 3, "a mosaic, not a blur"
    assert changed(im, apply(im, [["pixelate", 0.5, 0.36, 0.25, 0.0]])) == 0.0


def test_a_brush_entry_stacks_several_dabs_and_ignores_a_stray_tail():
    im = frame()
    one = apply(im, [["pixelate", 0.5, 0.36, 0.25, 0.1]])
    two = apply(im, [["pixelate", 0.5, 0.36, 0.25, 0.1, 0.62, 0.78, 0.14, 0.1]])
    assert changed(one, two) > 0.001
    tail = apply(im, [["pixelate", 0.5, 0.36, 0.25, 0.1, 0.62, 0.78, 0.14, 0.1, 0.5]])
    assert two.tobytes() == tail.tobytes()


def test_rays_warm_the_end_of_the_frame_they_come_from_and_not_the_other():
    im = frame()
    out = apply(im, [["rays", 0.9, 0.08, 0.75, 0.9]])
    near, far = out.getpixel((556, 40)), im.getpixel((556, 40))
    assert near[0] > far[0] and near[0] > near[2], "a leak is warm, not grey"
    assert out.getpixel((20, 880)) == im.getpixel((20, 880))
    assert changed(im, out) > 0.05


def test_softfocus_blooms_the_light_end_and_leaves_the_dark_end_alone():
    im = band()
    out = apply(im, [["softfocus", 0.8, 0.5]])
    assert out.getpixel((300, 60)) >= im.getpixel((300, 60))
    assert changed(im, out) > 0
    assert out.getpixel((300, 860)) == im.getpixel((300, 860)) == (0, 0, 0)
    assert changed(im, apply(im, [["softfocus", 0.15, 0.1]])) < changed(im, out)


def test_upscale_enlarges_and_refuses_to_pass_the_honest_limit():
    im = frame()
    out = apply(im, [["upscale", 2.0]])
    assert out.size == (1200, 1800)
    assert ImageStat.Stat(out.convert("L")).stddev[0] > 0
    huge = apply(Image.new("RGB", (2600, 3400), (128, 120, 130)), [["upscale", 4.0]])
    assert max(huge.size) == 4000 and min(huge.size) > 3000
    parked = Image.new("RGB", (4000, 4000), (10, 10, 10))
    assert apply(parked, [["upscale", 4.0]]).size == (4000, 4000)
    assert apply(im, [["upscale", 99]]).tobytes() == apply(im, [["upscale", 4.0]]).tobytes()


def test_an_upscale_of_one_is_not_a_resize_at_all():
    im = frame()
    assert apply(im, [["upscale", 1.0]]).size == SIZE


JUNK = [
    [], ["auto"], ["auto", "warm"], ["auto", None], ["auto", 0.4, 0.9, 0.2, 0.1],
    ["perspective"], ["perspective", 0.2], ["perspective", "a", "b", "c"],
    ["perspective", 0, 0, 1, 0, 1, 1, 0, 1, 0.5, 0.5, 0.5],
    ["stretch"], ["stretch", 0.5], ["stretch", 0.5, "longer"], ["stretch", -3, 40, -1],
    ["cutout"], ["cutout", 0.3], ["cutout", "blur", "yes"], ["cutout", 0.3, 0.2, 7.0, -50.0],
    ["splash"], ["splash", 400, -20, 3, 9], ["splash", None, None],
    ["duotone"], ["duotone", 300, -40, 12], ["duotone", "red", "blue"],
    ["mirror"], ["mirror", 9, -3, 40], ["mirror", "fold", "many"],
    ["pixelate"], ["pixelate", 0.5], ["pixelate", 0.5, 0.5], ["pixelate", "x", "y", 0.2, 0.1],
    ["pixelate", *([0.4, 0.4, 0.2, 0.1] * 40)],
    ["rays"], ["rays", 0.5, 0.5], ["rays", 2.0, -1.0, 0.0, 99.0], ["rays", float("nan"), 0.2, 0.5, 0.5],
    ["upscale"], ["upscale", 0.2], ["upscale", "big"], ["upscale", float("inf")],
    ["softfocus"], ["softfocus", 0.5, "lots"], ["softfocus", -2, 2],
    ["face_slim", 0.9], [None, 0.5], ["auto", [1, 2]], ["stretch", {"amount": 0.4}],
]


@pytest.mark.parametrize("entry", JUNK, ids=[str(j)[:38] for j in JUNK])
def test_a_malformed_entry_degrades_instead_of_raising(entry):
    im = frame()
    out = apply(im, [entry])
    assert out.size[0] > 0 and out.mode in ("RGB", "RGBA")
    assert max(out.size) <= MAX_EDGE


@pytest.mark.parametrize("name", NAMES)
def test_every_op_survives_an_entry_with_no_arguments_at_all(name):
    assert untouched(frame(), apply(frame(), [[name]]))


def test_a_recipe_that_is_not_a_recipe_at_all_is_refused_quietly():
    im = frame()
    for junk in (None, {}, "auto", [None], ["auto"], [["auto"]], [[7, 1]], [[["auto", 0.5]]]):
        assert apply(im, junk).size == SIZE


def test_a_recipe_survives_json_and_applies_identically():
    recipe = [["perspective", 0.08, 0.02, 0.94, 0.0, 1.0, 1.0, 0.0, 0.96],
              ["stretch", 0.55, 0.4, 0.2],
              ["auto", 0.6], ["splash", 0.0, 28.0, 1.0, 0.9],
              ["duotone", 0.094, 0.125, 0.227, 0.965, 0.878, 0.706, 0.5],
              ["pixelate", 0.3, 0.25, 0.16, 0.1, 0.7, 0.8, 0.16, 0.1],
              ["rays", 0.85, 0.1, 0.7, 0.5], ["softfocus", 0.5, 0.4],
              ["cutout", 0.3, 0.2, 1.0, 0.0]]
    back = json.loads(json.dumps(recipe))
    im = frame()
    assert apply(im, recipe).tobytes() == apply(im, back).tobytes()


def test_a_cutout_early_in_a_recipe_does_not_lose_its_transparency():
    im = backdrop()
    out = apply(im, [["cutout", 0.3, 0.2, 0.0, 0.0], ["softfocus", 0.5, 0.4], ["rays", 0.2, 0.2, 0.5, 0.4]])
    assert out.mode == "RGBA"
    assert out.getchannel("A").getpixel((2, 2)) == 0
    assert out.getchannel("A").getpixel((300, 460)) == 255


def test_an_op_asking_for_more_entries_than_the_registry_allows_is_cut_off():
    im = frame()
    entries = [["pixelate", 0.2, 0.2, 0.12, 0.1]] * (LIMITS["pixelate"] + 4)
    assert changed(apply(im, entries[:LIMITS["pixelate"]]), apply(im, entries)) == 0.0


def test_the_shape_tables_are_the_ones_the_ui_was_handed():
    assert SHAPE["pixelate"] == ["group", 4, 16]
    assert SHAPE["perspective"] == ["list", ["f"] * 8]
    assert CLAMP["splash"][0] == (0.0, 360.0)
    assert CLAMP["splash"][1] == (0.0, 180.0)
    assert CLAMP["upscale"] == [(1.0, 4.0)]
    assert all(isinstance(spec, list) and spec[0] in ("list", "group") for spec in SHAPE.values())


def test_no_argument_can_blow_the_frame_past_the_hard_edge():
    im = Image.new("RGB", (1500, 1500), (90, 90, 90))
    out = apply(im, [["upscale", 4.0], ["pixelate", 0.5, 0.5, 1.0, 0.4], ["stretch", 0.5, 0.7, 0.2]])
    assert max(out.size) <= MAX_EDGE
    assert not math.isnan(CLAMP["rays"][2][1])
