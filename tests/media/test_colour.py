"""Behaviour tests for the colour engine: one test per op, and each proves the same two
things - that the pixels the op claims to move did move, and that the pixels it does not
claim are byte-for-byte where they were.

The frame is a grid of swatches with known hue, saturation and value, plus a neutral toe,
a neutral highlight and a wide flat field, because a colour op can only be pinned against
numbers you wrote down first. Nothing here is written into data/.
"""

import colorsys
import random
import time

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageStat

from src.media import colour

SIZE = (600, 900)

# Regions are (left, upper, right, lower) boxes that sit wholly inside a swatch.
REGIONS = {
    "red": (60, 60, 240, 240),
    "green": (330, 60, 510, 240),
    "blue": (60, 320, 240, 500),
    "skin": (330, 320, 510, 500),
    "vivid": (60, 560, 240, 700),
    "toe": (330, 560, 510, 700),
    "top": (60, 770, 540, 850),
    "field": (540, 40, 590, 90),
}
# (hue in degrees, saturation, value). green and skin start at the same saturation on
# purpose, and vivid sits on blue's hue with more of its own, so the two things vibrance
# promises - damp the vivid, spare the skin - are each measured against one control.
SWATCHES = {
    "red": (0.0, 0.74, 0.75),
    "green": (135.0, 0.42, 0.80),
    "blue": (225.0, 0.62, 0.85),
    "skin": (24.0, 0.42, 0.90),
    "vivid": (225.0, 0.70, 0.85),
}
NEUTRALS = {"toe": (30, 30, 32), "top": (238, 238, 238)}

# One argument list per op that must leave the picture exactly as it found it - the
# engine's own defaults - and one at the far end of its range that must do something.
OFF = {name: list(args) for name, args in colour.DEFAULTS.items()}
ON = {
    "curves": [0.0, 0.7, 0.3, -0.5],
    "levels": [0.28, 0.78, 0.5],
    "vibrance": [0.9],
    "hue_rotate": [90.0, 4.0],
    "hsl": [3.0, 0.6, 0.8, 0.5, 0.9],
    "split_tone": [0.2, 0.34, 0.95, 0.98, 0.62, 0.28, 0.2, 0.9],
    "clarity": [0.9, 0.03],
    "dehaze": [0.9, 0.3],
    "invert": [0.8],
    "posterize": [4.0],
}


def swatch(hue_deg: float, sat: float, val: float):
    r, g, b = colorsys.hsv_to_rgb(hue_deg / 360.0, sat, val)
    return tuple(round(c * 255) for c in (r, g, b))


def photo():
    im = Image.new("RGB", SIZE, (128, 128, 128))
    d = ImageDraw.Draw(im)
    for key, box in REGIONS.items():
        if key in SWATCHES:
            d.rectangle(box, fill=swatch(*SWATCHES[key]))
        elif key in NEUTRALS:
            d.rectangle(box, fill=NEUTRALS[key])
    return im


def hazy():
    """The same frame with a flat neutral grey laid over it: classical haze, known thickness."""
    clean = photo()
    return clean, Image.blend(clean, Image.new("RGB", SIZE, (205, 205, 205)), 0.4)


def ramp_row():
    """One row holding every value a channel can take, so a LUT can be read back directly."""
    row = Image.new("L", (256, 1))
    row.putdata(list(range(256)))
    return row.convert("RGB")


def textured():
    """A hard-edged subject on a wide flat field, so a local-contrast op has one of each."""
    im = Image.new("RGB", (600, 600), (120, 120, 120))
    d = ImageDraw.Draw(im)
    d.ellipse([190, 190, 410, 410], fill=(190, 190, 190))
    return im


def ramp_photo(lo_deg=60.0, hi_deg=190.0, box=(40, 700, 560, 760)):
    """A hue sweep across the one free band of the frame, for the HSL range slot."""
    im = photo()
    strip = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (128, 128, 128))
    pen = ImageDraw.Draw(strip)
    for x in range(strip.width):
        deg = lo_deg + (hi_deg - lo_deg) * x / max(1, strip.width - 1)
        pen.line([(x, 0), (x, strip.height)], fill=swatch(deg, 0.5, 0.8))
    im.paste(strip, box[:2])
    return im, box


def run(name, im, args):
    return colour.APPLIERS[name](im, args)


def diff(im, out):
    return ImageChops.difference(im.convert("RGB"), out.convert("RGB")).convert("L")


def ink_box(im, out):
    return diff(im, out).getbbox()


def ink_fraction(im, out):
    hist = diff(im, out).histogram()
    return sum(hist[2:]) / (im.width * im.height)


def gap(im, out):
    """How far, on average, the edited frame sits from the original. ink_fraction only
    says a pixel moved at all, so a gentle setting and a brutal one can tie on a frame
    of flat swatches; this cannot."""
    return round(ImageStat.Stat(diff(im, out)).mean[0], 2)


def exact(im, out, key):
    """That region is byte for byte the same picture."""
    return im.crop(REGIONS[key]).tobytes() == out.crop(REGIONS[key]).tobytes()


def mean(im, key):
    return tuple(round(v) for v in ImageStat.Stat(im.crop(REGIONS[key])).mean)


def band_mean(im, key, which):
    """The mean of one HSV channel over a region: 0 hue in degrees, 1 saturation,
    2 value."""
    band = im.convert("HSV").split()[which]
    v = ImageStat.Stat(band.crop(REGIONS[key])).mean[0]
    return round(v * 360.0 / 256.0, 1) if which == 0 else round(v, 1)


def hue_turn(im, out, key):
    """Signed degrees the hue actually travelled, shortest way round the wheel."""
    a, b = band_mean(im, key, 0), band_mean(out, key, 0)
    return round((b - a + 180.0) % 360.0 - 180.0, 1)


def stddev(im, box=None):
    crop = im if box is None else im.crop(box)
    return round(ImageStat.Stat(crop.convert("L")).stddev[0], 2)


def spread(pixel):
    return max(pixel) - min(pixel)


def test_curves_bends_one_channel_and_three_regions_of_it():
    im = photo()
    green = run("curves", im, [2.0, 0.0, 0.8, 0.0])        # slot 0 names the band
    assert green.mode == "RGB" and green.size == SIZE
    assert green.split()[0].tobytes() == im.split()[0].tobytes(), "a green curve moved red"
    assert green.split()[2].tobytes() == im.split()[2].tobytes(), "a green curve moved blue"
    assert band_mean(green, "field", 2) > band_mean(im, "field", 2)
    rgb = run("curves", im, [0.0, 0.0, 0.8, 0.0])          # slot 0 = all three bands
    assert ink_fraction(green, rgb) > 0.2, "channel 0 did not reach the other two"
    # each offset holds its own third of the ramp
    shadows = run("curves", im, [0.0, 0.9, 0.0, 0.0])
    mids = run("curves", im, [0.0, 0.0, 0.9, 0.0])
    highs = run("curves", im, [0.0, 0.0, 0.0, 0.9])
    assert mean(shadows, "toe")[0] - mean(im, "toe")[0] > 50
    assert abs(mean(shadows, "top")[0] - mean(im, "top")[0]) <= 2, "the shadows slider lit whites"
    assert band_mean(mids, "field", 2) - band_mean(im, "field", 2) > 30
    assert abs(mean(mids, "toe")[0] - mean(im, "toe")[0]) < 25, "the mids slider took the toe"
    assert mean(highs, "top")[0] - mean(im, "top")[0] > 10
    assert abs(mean(highs, "toe")[0] - mean(im, "toe")[0]) <= 3, "the highs slider lifted blacks"
    assert run("curves", im, OFF["curves"]).tobytes() == im.tobytes()


def test_levels_sets_a_floor_and_a_ceiling_and_only_those_ends():
    ramp = ramp_row()
    def at(im, x):
        return im.getpixel((x, 0))

    floor = run("levels", ramp, [0.35, 1.0, 0.0])
    # The black point is a floor: everything under it lands on zero and the top of the
    # ramp is nailed at 255, so all the compression happens between the two.
    assert at(floor, 0) == (0, 0, 0)
    assert at(floor, 89) == (0, 0, 0), "values under the black point survived"
    assert at(floor, 255) == (255, 255, 255), "the black point took the white"
    assert at(floor, 128)[0] < 100, "the black point lifted the midtones instead of crushing them"
    assert at(floor, 254)[0] > 250, "the black point flattened the top of the ramp"
    ceiling = run("levels", ramp, [0.0, 0.62, 0.0])
    assert at(ceiling, 0) == (0, 0, 0)
    assert at(ceiling, 160) == (255, 255, 255), "values over the white point survived"
    assert at(ceiling, 20)[0] > 20, "the white point darkened the toe"
    lifted = run("levels", ramp, [0.0, 1.0, 0.8])
    sunk = run("levels", ramp, [0.0, 1.0, -0.8])
    assert at(lifted, 128)[0] > 150 and at(sunk, 128)[0] < 45, "gamma did not bend the middle"
    for variant in (lifted, sunk):
        assert at(variant, 0) == (0, 0, 0) and at(variant, 255) == (255, 255, 255), \
            "gamma moved an endpoint"

    mid_lift = at(lifted, 128)[0] - 128
    top_lift = at(lifted, 238)[0] - 238
    assert mid_lift > 3 * top_lift >= 0, "gamma hit the highlights as hard as the midtones"

    im = photo()
    black = run("levels", im, [0.35, 1.0, 0.0])
    assert mean(black, "toe") == (0, 0, 0), "the black point did not crush the toe"
    assert mean(black, "field")[0] < mean(im, "field")[0]
    assert mean(black, "top")[0] >= mean(im, "top")[0] - 12, "the black point collapsed the highlights"
    assert run("levels", im, OFF["levels"]).tobytes() == im.tobytes()


def test_vibrance_adds_colour_where_there_is_room_and_not_where_there_is_not():
    im = photo()
    out = run("vibrance", im, [1.0])
    def gain(key):
        return band_mean(out, key, 1) - band_mean(im, key, 1)
    assert gain("green") > 60, (gain("green"), "a roomy mid-saturation pixel barely moved")
    assert gain("green") > gain("vivid") + 25, "the already-vivid pixel was pushed as hard"
    assert gain("green") > gain("skin") + 25, "skin took the full dose, which is how faces go orange"
    assert band_mean(out, "vivid", 1) <= 255 and band_mean(out, "skin", 1) <= 255
    assert exact(im, out, "field") and exact(im, out, "top"), "grey invented its own colour"
    back = run("vibrance", im, [-0.9])
    assert band_mean(back, "blue", 1) < band_mean(im, "blue", 1) - 40
    assert exact(im, back, "field")
    assert run("vibrance", im, [0.0]).tobytes() == im.tobytes()


def test_hue_rotate_turns_one_band_and_leaves_the_rest_of_the_wheel_alone():
    im = photo()
    out = run("hue_rotate", im, [90.0, 4.0])               # 4 is the green band
    assert hue_turn(im, out, "green") == pytest.approx(90.0, abs=6)
    for key in ("red", "blue", "skin", "vivid", "toe", "field"):
        assert exact(im, out, key), f"the green band reached the {key}"
    every = run("hue_rotate", im, [90.0, 0.0])
    for key in ("red", "green", "blue"):
        assert hue_turn(im, every, key) == pytest.approx(90.0, abs=6), key
    assert exact(im, every, "field") and exact(im, every, "top"), "a grey pixel was turned"
    assert ink_fraction(im, run("hue_rotate", im, [-180.0, 0.0])) > 0.2
    assert run("hue_rotate", im, [0.0, 4.0]).tobytes() == im.tobytes()
    assert run("hue_rotate", im, [30.0, 7.0]).tobytes() == im.tobytes(), "nothing here is purple"


def test_hsl_edits_one_hue_band_and_the_grey_pixels_next_to_it():
    im = photo()
    out = run("hsl", im, [3.0, 0.0, 1.0, 1.0, 1.0])        # green: saturation and lightness up
    assert band_mean(out, "green", 1) > band_mean(im, "green", 1) + 40
    assert band_mean(out, "green", 2) > band_mean(im, "green", 2)
    for key in ("red", "blue", "skin", "vivid", "toe", "top", "field"):
        assert exact(im, out, key), f"the green band reached the {key}"
    hue_only = run("hsl", im, [3.0, 1.0, 0.0, 0.0, 1.0])
    assert hue_turn(im, hue_only, "green") == pytest.approx(40.0, abs=8), \
        "the hue slot swings a band by HUE_SWING degrees at 1"
    skin = run("hsl", im, [7.0, 0.0, -1.0, 0.0, 1.0])      # band 7 is skin, drained here
    assert band_mean(skin, "skin", 1) < band_mean(im, "skin", 1) - 40
    assert exact(im, skin, "blue") and exact(im, skin, "field")
    swept, box = ramp_photo()
    def strip_ink(edited):
        return ink_fraction(swept.crop(box), edited.crop(box))
    wide = run("hsl", swept, [3.0, 0.0, 1.0, 0.0, 1.0])
    narrow = run("hsl", swept, [3.0, 0.0, 1.0, 0.0, 0.25])
    assert strip_ink(wide) > 0.3, "range 1 did not cover its own band"
    assert strip_ink(narrow) < 0.2, "a 0.25 range still ate the whole sweep"
    assert strip_ink(wide) > 2 * strip_ink(narrow), "the range slot does nothing"
    assert run("hsl", im, OFF["hsl"]).tobytes() == im.tobytes()


def test_split_tone_paints_the_two_ends_and_hands_the_middle_back_unchanged():
    im = photo()
    args = [0.18, 0.32, 0.95, 0.98, 0.60, 0.24]
    out = run("split_tone", im, [*args, 0.0, 1.0])
    assert mean(out, "toe")[2] > mean(out, "toe")[0] + 20, "shadows did not go cool"
    assert mean(out, "top")[0] > mean(out, "top")[2] + 20, "highlights did not go warm"
    assert spread(mean(out, "toe")) > spread(mean(im, "toe"))
    assert exact(im, out, "field"), "the split reached into the midtones it was told to leave"
    assert ink_box(im, out) is not None
    low = run("split_tone", im, [*args, -0.8, 1.0])
    high = run("split_tone", im, [*args, 0.8, 1.0])
    assert mean(low, "field")[0] > mean(low, "field")[2], "balance -0.8 left the mids neutral"
    assert mean(high, "field")[2] > mean(high, "field")[0], "balance +0.8 left the mids neutral"
    assert mean(out, "toe") != mean(low, "toe")
    idle = run("split_tone", im, [*args, 0.4, 0.0])
    assert idle.tobytes() == im.tobytes(), "amount 0 still painted a colour cast"


def test_clarity_raises_local_contrast_and_leaves_a_flat_field_byte_exact():
    im = textured()
    ring, flat = (150, 150, 450, 450), (20, 20, 120, 120)
    up = run("clarity", im, [1.0, 0.02])
    down = run("clarity", im, [-1.0, 0.02])
    assert stddev(up, ring) > stddev(im, ring), "clarity raised nothing"
    assert stddev(down, ring) < stddev(im, ring), "negative clarity sharpened instead"
    assert up.crop(flat).tobytes() == im.crop(flat).tobytes(), "clarity moved a flat area"
    assert down.crop(flat).tobytes() == im.crop(flat).tobytes()
    assert ink_box(im, up)[0] > 0, "the wide radius reached the frame edge"
    wide = run("clarity", im, [1.0, 0.08])
    assert ink_fraction(im, wide) > ink_fraction(im, up), "the radius slot does nothing"
    assert run("clarity", im, [0.0, 0.05]).tobytes() == im.tobytes()


def test_dehaze_takes_the_veil_off_and_only_lifts_the_blacks_back():
    clean, im = hazy()
    out = run("dehaze", im, [1.0, 0.0])
    assert mean(out, "toe")[0] < mean(im, "toe")[0] - 30, "the haze floor stayed put"
    assert spread(mean(out, "toe")) < 20, "a neutral shadow turned coloured"
    assert stddev(out) > stddev(im), "taking the veil off returned no contrast"
    assert stddev(out) > stddev(clean) - 15, "the recovery undershot its own target"
    assert spread(mean(out, "field")) < 12, "the flat grey field went cast"
    lifted = run("dehaze", im, [1.0, 1.0])
    assert mean(lifted, "toe")[0] > mean(out, "toe")[0] + 10, "lift put no black back"
    assert lifted.crop(REGIONS["top"]).tobytes() == out.crop(REGIONS["top"]).tobytes(), \
        "the shadow lift reached into the highlights"
    assert run("dehaze", im, [0.0, 1.0]).tobytes() == im.tobytes()
    assert gap(im, run("dehaze", im, [0.3, 0.0])) < gap(im, out), "a third of a dehaze pulled as hard as a whole one"


def test_invert_blends_the_frame_toward_its_own_negative_by_the_amount_it_says():
    im = photo()
    full = run("invert", im, [1.0])
    assert mean(full, "red") == tuple(255 - c for c in mean(im, "red"))
    assert mean(full, "field") == (127, 127, 127)
    half = run("invert", im, [0.5])
    for a, b, c in zip(mean(half, "red"), mean(im, "red"), mean(full, "red")):
        assert abs(a - (b + c) / 2) <= 2, (a, b, c)
    assert ink_fraction(im, half) > 0.3, "half an invert left most of the frame alone"
    assert run("invert", im, [0.0]).tobytes() == im.tobytes(), "amount 0 painted the negative"
    assert ink_box(im, run("invert", im, [0.05])) == ink_box(im, full), "it stopped short"


def test_posterize_counts_down_the_levels_it_promises():
    row = Image.new("L", (256, 1))
    row.putdata(list(range(256)))
    grad = row.convert("RGB")
    def held(im):
        """Distinct values one channel still carries - posterising is per channel."""
        return len([n for n in im.split()[0].histogram() if n])
    assert held(grad) == 256
    for levels in (2, 4, 8, 16):
        assert held(run("posterize", grad, [float(levels)])) == levels, \
            (levels, "levels 2..16 are 2..16 steps per channel")
    im = photo()
    coarse = run("posterize", im, [2.0])
    assert len(coarse.crop(REGIONS["red"]).getcolors(maxcolors=8)) == 1, "a flat swatch gained bands"
    assert exact(coarse, run("posterize", coarse, [16.0]), "red"), "posterising twice undid itself"
    assert ink_fraction(im, coarse) > 0.01
    assert gap(im, run("posterize", im, [16.0])) < gap(im, coarse), \
        "16 levels cut as hard as 2"


def test_every_op_keeps_the_mode_the_size_and_the_alpha_it_was_given():
    rgba = photo().convert("RGBA")
    ImageDraw.Draw(rgba).rectangle([480, 620, 599, 899], fill=(0, 0, 0, 40))
    alpha = rgba.getchannel("A").tobytes()
    for name, args in ON.items():
        out = run(name, rgba, args)
        assert out.mode == "RGBA", name
        assert out.size == rgba.size, name
        assert out.getchannel("A").tobytes() == alpha, f"{name} touched the alpha"
        assert ink_fraction(rgba, out) > 0.0, f"{name} did nothing at all"
        assert out.convert("RGB").tobytes() == run(name, rgba.convert("RGB"), args).tobytes(), name


def test_a_default_entry_does_nothing_except_where_there_is_no_such_setting():
    im = photo()
    for name, args in OFF.items():
        if name == "posterize":
            # 16 levels is the gentlest thing this op owns, so a short or broken entry
            # posterises mildly instead of pretending it never ran.
            out = run(name, im, args)
            assert len(out.crop(REGIONS["field"]).getcolors(maxcolors=17)) <= 16, name
            assert out.size == im.size and out.mode == "RGB"
            continue
        assert run(name, im, args).tobytes() == im.tobytes(), f"{name} is not idle at its default"


def busy():
    """The swatch frame with real grain over it. Flat colour is the easy case for every
    op here - per-pixel maths across a noisy frame is what a preview actually costs."""
    grain = Image.frombytes("RGB", (SIZE[0] // 2, SIZE[1] // 2),
                            random.Random(7).randbytes(SIZE[0] * SIZE[1] // 2 * 3))
    return Image.blend(photo(), grain.resize(SIZE, Image.BILINEAR), 0.45)


@pytest.mark.parametrize("name", sorted(colour.APPLIERS))
def test_no_colour_op_costs_more_than_a_preview_should_wait(name):
    im = busy()
    start = time.perf_counter()
    out = run(name, im, ON[name])
    took = time.perf_counter() - start
    assert out.width > 0
    assert took < 1.5, f"{name} took {took:.2f}s on a 900 px frame"


def test_a_whole_colour_recipe_survives_the_file_it_is_saved_to(tmp_path):
    src = tmp_path / "inbox.jpg"
    photo().save(src, quality=95)
    recipe = [[name, *args] for name, args in ON.items()]
    with Image.open(src) as raw:
        out = colour.apply(raw.convert("RGB"), recipe)
    assert out.mode == "RGB" and out.size == SIZE
    assert out.getbbox() is not None
    saved = tmp_path / "graded.png"
    out.save(saved)
    with Image.open(saved) as again:
        reloaded = again.convert("RGB")
    assert reloaded.size == SIZE
    assert ImageStat.Stat(reloaded.convert("L")).mean[0] > 4
    # the same recipe run twice lands on the same pixels, which is the whole point of
    # keeping it as a list of numbers instead of a flattened file
    with Image.open(src) as raw:
        twice = colour.apply(raw.convert("RGB"), recipe)
    assert twice.tobytes() == out.tobytes()
