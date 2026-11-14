"""The lens rail: what each optic promises, proved on the pixels.

One test per op, in the house style: the frame changes where the op says it changes, and
comes back byte for byte everywhere it says it does not.
"""

import time

import pytest
from PIL import Image, ImageChops, ImageDraw

from src.media import optics

SIZE = (600, 800)
W, H = SIZE
BASE = (120, 125, 130)

# The loudest setting each op will take, for the "it did something" half of the proof.
LOUD = {
    "tiltshift": [0.5, 0.22, 1.0, 15.0],
    "motion_blur": [35.0, 0.12],
    "radial_blur": [0.5, 0.5, 0.9, 0.3],
    "prism": [1.0, 0.45, 0.5],
    "bokeh": [0.5, 1.0, 0.12, 30.0],
    "orton": [1.0, 0.7],
    "lightleak": [210.0, 0.98, 0.47, 0.16, 1.0],
    "glitch": [0.8, 0.7, 0.6, 0.4],
    "fisheye": [0.6, 0.5, 0.5],
}


def run(name, im, args):
    return optics.APPLIERS[name](im, args)


def diff(im, out):
    return ImageChops.difference(im.convert("RGB"), out.convert("RGB")).convert("L")


def ink_box(im, out):
    return diff(im, out).getbbox()


def ink_fraction(im, out):
    hist = diff(im, out).histogram()
    return sum(hist[2:]) / (W * H)


def near(pixel, colour, slack=8):
    return sum(abs(a - b) for a, b in zip(pixel, colour)) <= slack


def row_exact(d, y):
    """A row of the difference map that is zero all the way across."""
    return d.crop((0, y, W, y + 1)).getextrema() == (0, 0)


def swing(im, x, y0, y1):
    """Brightest minus darkest down one column: how much detail is still standing there."""
    g = im.convert("L")
    vals = [g.getpixel((x, y)) for y in range(y0, y1)]
    return max(vals) - min(vals)


def stripes(period=12):
    """High detail running across the frame, so a blur has something to destroy."""
    band = Image.new("L", (1, H))
    px = band.load()
    for y in range(H):
        px[0, y] = 240 if (y // period) % 2 == 0 else 30
    return band.convert("RGB").resize(SIZE, Image.NEAREST)


def step_edge(at=0.5, dark=60, bright=200):
    """One hard vertical edge, uniform from top to bottom."""
    strip = Image.new("RGB", (W, 1), (dark, dark, dark))
    ImageDraw.Draw(strip).rectangle([int(at * W), 0, W - 1, 0], fill=(bright, bright, bright))
    return strip.resize(SIZE, Image.NEAREST)


def transition_width(im, y=None, lo=70, hi=190):
    """How many columns sit inside the ramp of the edge - a streak's signature."""
    y = H // 2 if y is None else y
    g = im.convert("L")
    return len([x for x in range(W) if lo <= g.getpixel((x, y)) <= hi])


def block_field():
    """A bright rectangle on a flat field: four edges to fringe, flat anywhere else."""
    im = Image.new("RGB", SIZE, (90, 90, 90))
    ImageDraw.Draw(im).rectangle([200, 350, 380, 450], fill=(200, 200, 200))
    return im


def dot_left():
    """A bright mark well left of the frame's middle, on flat ground."""
    im = Image.new("RGB", SIZE, BASE)
    ImageDraw.Draw(im).rectangle([80, 380, 100, 420], fill=(240, 240, 240))
    return im


def lights():
    """One hot point, one field under the threshold, one true black."""
    im = Image.new("RGB", SIZE, (110, 110, 110))
    d = ImageDraw.Draw(im)
    d.ellipse([120, 380, 150, 410], fill=(250, 250, 250))
    d.rectangle([430, 600, 520, 700], fill=(0, 0, 0))
    return im


def black_hole():
    """Flat density with a true black core big enough that a soft plate cannot reach it."""
    im = Image.new("RGB", SIZE, (100, 100, 100))
    ImageDraw.Draw(im).rectangle([240, 340, 360, 460], fill=(0, 0, 0))
    return im


def grey():
    return Image.new("RGB", SIZE, (100, 100, 100))


def line_field(at=200):
    """A straight bright line across the frame, well off the middle."""
    im = Image.new("RGB", SIZE, BASE)
    ImageDraw.Draw(im).line([0, at, W - 1, at], fill=(245, 245, 245), width=3)
    return im


def line_row(im, x, lo=60, hi=380):
    """Where the bright line has ended up in one column."""
    g = im.convert("L")
    best, row = -1, None
    for y in range(lo, hi):
        v = max(g.getpixel((x, y)), g.getpixel((x, min(H - 1, y + 1))))
        if v > best:
            best, row = v, y
    return row


def crossing(ch, x0, x1, row, mid=145):
    for x in range(x0, x1):
        if ch.getpixel((x, row)) >= mid:
            return x
    return None


def last_bright(ch, x0, x1, row, mid=145):
    xs = [x for x in range(x0, x1) if ch.getpixel((x, row)) >= mid]
    return xs[-1] if xs else None


# --------------------------------------------------------------------------- the ops


def test_tiltshift_holds_its_band_sharp_and_drops_everything_else():
    im = stripes()
    out = run("tiltshift", im, [0.5, 0.22, 1.0, 0.0])
    assert out.mode == "RGB" and out.size == SIZE
    d = diff(im, out)
    # half the band is 0.11 * 800 = 88 px either side of row 400: that strip is untouched
    assert all(row_exact(d, y) for y in range(316, 484))
    # above it and below it the same detail is gone: 210 of swing left with 5
    assert swing(im, 300, 40, 160) == 210
    assert swing(out, 300, 40, 160) < 12
    assert swing(out, 300, 640, 760) < 12
    assert d.crop((0, 0, W, 220)).getbbox() is not None
    assert d.crop((0, 580, W, H)).getbbox() is not None
    assert run("tiltshift", im, [0.5, 0.22, 0.0, 0.0]).tobytes() == im.tobytes()


def test_tiltshift_band_turns_with_its_angle():
    im = stripes()
    flat = run("tiltshift", im, [0.5, 0.22, 1.0, 0.0])
    tilt = run("tiltshift", im, [0.5, 0.22, 1.0, 45.0])
    # on the level, (60,400) is inside the band and (420,520) is outside it
    assert flat.getpixel((60, 400)) == im.getpixel((60, 400))
    assert flat.getpixel((420, 520)) != im.getpixel((420, 520))
    # at 45 degrees the band runs corner to corner, so both flip
    assert tilt.getpixel((60, 400)) != im.getpixel((60, 400))
    assert tilt.getpixel((420, 520)) == im.getpixel((420, 520))


def test_motion_blur_streaks_across_a_feature_and_not_along_it():
    im = step_edge()
    across = run("motion_blur", im, [0.0, 0.06])
    along = run("motion_blur", im, [90.0, 0.06])
    assert transition_width(im) == 0
    # 0.06 of a 600 px short edge is 36 px of travel, and the ramp shows it
    assert transition_width(across) > 40
    # a streak along the edge's own axis is the identity: the copies are the frame itself
    assert along.tobytes() == im.tobytes()
    box = ink_box(im, across)
    assert box is not None and 250 < box[0] < box[2] < 350 and box[3] == H
    assert across.getpixel((5, 5)) == im.getpixel((5, 5))
    assert across.getpixel((W - 6, 5)) == im.getpixel((W - 6, 5))
    assert run("motion_blur", im, [35.0, 0.0]).tobytes() == im.tobytes()


def test_motion_blur_length_is_a_fraction_of_the_short_edge():
    im = step_edge()
    short = run("motion_blur", im, [0.0, 0.03])
    long = run("motion_blur", im, [0.0, 0.2])
    assert transition_width(short) < transition_width(long)
    assert ink_box(im, long)[2] - ink_box(im, long)[0] > 150


def test_radial_blur_drags_outward_from_its_anchor_and_leaves_the_core_alone():
    im = dot_left()
    out = run("radial_blur", im, [0.5, 0.5, 0.8, 0.4])
    d = diff(im, out)
    assert out.getpixel((300, 400)) == im.getpixel((300, 400))
    # falloff 0.4 protects 120 px around the anchor, and the drag is a flat field there
    assert d.crop((180, 280, 420, 520)).getbbox() is None
    box = d.getbbox()
    assert box is not None
    # the mark sits 200 px left of the anchor: the zoom copies sit between it and the
    # anchor, so the smear reaches outward past x = 80 and never comes back inside x = 100
    assert box[0] < 40 and box[2] <= 105
    assert 360 <= box[1] <= 380 and 420 <= box[3] <= 440
    # move the anchor outside the mark and the same rule drags it the other way
    flip = diff(im, run("radial_blur", im, [0.05, 0.5, 0.6, 0.1])).getbbox()
    assert flip is not None and flip[0] >= 78 and flip[2] > 110
    assert diff(im, run("radial_blur", im, [0.5, 0.5, 0.8, 1.0])).crop(
        (100, 200, 500, 600)).getbbox() is None
    assert run("radial_blur", im, [0.5, 0.5, 0.0, 0.4]).tobytes() == im.tobytes()


def test_prism_frings_each_edge_and_the_order_flips_across_the_anchor():
    im = block_field()
    out = run("prism", im, [1.0, 0.5, 0.5])
    r, g, b = out.split()
    left = [crossing(ch, 170, 230, 400) for ch in (r, g, b)]
    right = [last_bright(ch, 355, 425, 400) for ch in (r, g, b)]
    # blue keeps the geometry it came in with; red is stretched hardest, and which side of
    # the edge it lands on depends on which side of the anchor that edge is
    assert left == [190, 195, 200] and right == [388, 384, 380]
    assert left[0] < left[1] < left[2] and right[0] > right[1] > right[2]
    box = ink_box(im, out)
    assert box is not None and 185 <= box[0] and box[2] <= 395
    assert out.getpixel((290, 400)) == im.getpixel((290, 400))
    assert out.getpixel((20, 20)) == im.getpixel((20, 20))
    flat = Image.new("RGB", SIZE, (90, 90, 90))
    assert run("prism", flat, [1.0, 0.5, 0.5]).tobytes() == flat.tobytes()
    assert run("prism", im, [0.0, 0.5, 0.5]).tobytes() == im.tobytes()


def test_bokeh_lifts_only_the_points_over_threshold_and_stretches_the_ball():
    im = lights()
    out = run("bokeh", im, [0.7, 0.9, 0.06, 0.0])
    d = diff(im, out)
    box = d.getbbox()
    assert box is not None
    # the bloom is around the point, not on it: the point itself was already nearly white
    assert sum(out.getpixel((135, 350))) > sum(im.getpixel((135, 350)))
    # under the threshold the frame keeps the pixels it had
    assert out.getpixel((560, 60)) == im.getpixel((560, 60))
    assert out.getpixel((300, 100)) == im.getpixel((300, 100))
    assert out.getpixel((475, 650)) == (0, 0, 0)
    assert ink_fraction(im, out) < 0.05
    # anamorphic: the long axis of the ball follows the angle
    assert (box[2] - box[0]) > (box[3] - box[1])
    turn = diff(im, run("bokeh", im, [0.7, 0.9, 0.06, 90.0])).getbbox()
    assert turn is not None and (turn[3] - turn[0]) > (turn[2] - turn[0])
    assert run("bokeh", im, [1.0, 0.9, 0.06, 0.0]).tobytes() == im.tobytes()
    assert run("bokeh", im, [0.7, 0.0, 0.06, 0.0]).tobytes() == im.tobytes()


def test_orton_lifts_density_and_leaves_a_true_black_black():
    im = black_hole()
    out = run("orton", im, [1.0, 0.0])
    assert out.getpixel((60, 60)) == (161, 161, 161)          # 100 screened against itself
    assert run("orton", im, [0.5, 0.0]).getpixel((60, 60)) == (130, 130, 130)
    assert out.getpixel((300, 400)) == (0, 0, 0)              # nothing there to screen with
    assert sum(out.getpixel((245, 400))) > 0                  # the rim of the shadow does bloom
    soft = run("orton", im, [1.0, 1.0])
    assert sum(soft.getpixel((300, 400))) > sum(out.getpixel((300, 400)))
    assert run("orton", im, [0.0, 0.4]).tobytes() == im.tobytes()


def test_lightleak_comes_in_from_one_edge_and_is_exactly_nothing_at_the_other():
    im = grey()
    out = run("lightleak", im, [0.0, 1.0, 0.58, 0.322, 1.0])
    d = diff(im, out)
    assert d.crop((0, 0, 200, H)).getbbox() is None
    assert out.getpixel((0, 400)) == (100, 100, 100)
    assert out.getpixel((W - 1, 400)) == (255, 190, 150)
    box = d.getbbox()
    assert box is not None and box[0] > 200 and box[2] == W
    # a red leak lifts red and nothing else, screen mode never takes density away
    warm = run("lightleak", im, [0.0, 1.0, 0.0, 0.0, 1.0])
    assert warm.getpixel((W - 1, 400)) == (255, 100, 100)
    turn = diff(im, run("lightleak", im, [180.0, 1.0, 0.58, 0.322, 1.0])).getbbox()
    assert turn is not None and turn[0] == 0 and turn[2] < 400
    assert run("lightleak", im, [0.0, 1.0, 0.58, 0.322, 0.0]).tobytes() == im.tobytes()


def test_glitch_moves_the_slices_it_was_given_and_none_it_was_not():
    im = step_edge()
    a = run("glitch", im, [0.45, 0.11, 0.0, 0.3])
    b = run("glitch", im, [0.45, 0.11, 0.0, 0.3])
    assert a.tobytes() == b.tobytes()                          # the same seed, the same damage
    assert a.tobytes() != run("glitch", im, [0.45, 0.11, 0.0, 0.8]).tobytes()
    d = diff(im, a)
    touched = [y for y in range(H) if not row_exact(d, y)]
    assert 0 < len(touched) < H // 2                           # two bands out of 800 rows
    assert all(row_exact(d, y) for y in range(0, min(touched)))
    assert all(row_exact(d, y) for y in range(max(touched) + 1, H))
    assert ink_fraction(im, a) < 0.05
    assert a.getpixel((100, 400)) == im.getpixel((100, 400))    # flat ground, flat output


def test_glitch_channel_shift_pushes_red_and_blue_opposite_ways():
    im = step_edge()
    out = run("glitch", im, [0.0, 0.4, 1.0, 0.0])
    r, g, b = out.split()
    shifts = [crossing(ch, 240, 360, 200) for ch in (r, g, b)]
    assert shifts == [318, 300, 282]                           # +-18 px about the same edge
    assert out.getpixel((100, 200)) == im.getpixel((100, 200))
    assert 0 < ink_fraction(im, out) < 0.25
    assert run("glitch", im, [0.0, 0.4, 0.0, 0.0]).tobytes() == im.tobytes()


def test_glitch_scanlines_arrive_only_past_half_amount_and_on_every_third_row():
    im = Image.new("RGB", SIZE, BASE)
    out = run("glitch", im, [0.8, 0.0, 0.0, 0.0])
    d = diff(im, out)
    assert all(row_exact(d, y) for y in range(0, 60) if y % 3 != 2)
    assert all(not row_exact(d, y) for y in range(2, 60, 3))
    assert near(out.getpixel((100, 62)), (104, 108, 112), slack=6)
    quiet = run("glitch", im, [0.5, 0.0, 0.0, 0.0])
    assert quiet.tobytes() == im.tobytes()


def test_fisheye_bows_a_straight_line_and_pins_the_frame_it_was_given():
    im = line_field()
    home = line_row(im, 300)
    assert home == line_row(im, 40)                            # the line starts out straight
    bulge = run("fisheye", im, [0.35, 0.5, 0.5])
    pinch = run("fisheye", im, [-0.35, 0.5, 0.5])
    # a positive amount throws the line away from the anchor, a negative one back over it
    assert line_row(bulge, 300) < home < line_row(pinch, 300)
    # and it bows: the middle of the line travels further than its ends, each sign its own way
    assert line_row(bulge, 300) < line_row(bulge, 40) <= home
    assert line_row(pinch, 300) > line_row(pinch, 40) >= home
    for pt in [(1, 1), (W - 2, 1), (1, H - 2), (W - 2, H - 2)]:
        assert bulge.getpixel(pt) == im.getpixel(pt)            # the rim is held
        assert pinch.getpixel(pt) == im.getpixel(pt)
    assert bulge.getpixel((300, 400)) == im.getpixel((300, 400))
    box = ink_box(im, bulge)
    assert box is not None and box[3] < 260                     # the bottom half never moves
    assert run("fisheye", im, [0.0, 0.5, 0.5]).tobytes() == im.tobytes()


# ------------------------------------------------------------------ the shared contract


@pytest.mark.parametrize("name", sorted(optics.APPLIERS))
def test_each_default_is_the_no_op_it_claims(name):
    im = step_edge()
    out = run(name, im, optics.DEFAULTS[name])
    assert out.mode == "RGB" and out.size == SIZE
    assert out.tobytes() == im.tobytes(), f"{name} at its defaults moved a pixel"


@pytest.mark.parametrize("name", sorted(optics.APPLIERS))
def test_a_loud_setting_actually_ink_the_frame(name):
    im = stripes() if name == "tiltshift" else lights()
    assert ink_box(im, run(name, im, LOUD[name])) is not None, f"{name} did nothing"


@pytest.mark.parametrize("name", sorted(optics.APPLIERS))
def test_every_op_returns_the_mode_it_was_given_and_keeps_the_alpha(name):
    im = Image.new("RGBA", SIZE, (200, 100, 50, 128))
    ImageDraw.Draw(im).ellipse([120, 380, 150, 410], fill=(250, 250, 250, 255))
    out = run(name, im, LOUD[name])
    assert out.mode == "RGBA" and out.size == SIZE
    assert out.getchannel("A").tobytes() == im.getchannel("A").tobytes()
    plain = Image.new("P", (64, 64))
    plain = plain.convert("RGB")
    assert run(name, plain, optics.DEFAULTS[name]).mode == "RGB"


@pytest.mark.parametrize("name", sorted(optics.APPLIERS))
def test_junk_and_short_argument_lists_land_on_the_no_op(name):
    im = step_edge()
    k = len(optics.DEFAULTS[name])
    for args in ([], None, ["a", "b", "c"], [None] * k, [float("nan")] * k,
                 [0.5, float("inf"), "x", 99, -99]):
        out = run(name, im, args)
        assert out.mode == "RGB" and out.size == SIZE
    for cut in range(1, k):
        assert run(name, im, optics.DEFAULTS[name][:cut]).tobytes() == im.tobytes()


@pytest.mark.parametrize("name", sorted(optics.APPLIERS))
def test_clamps_hold_at_both_ends(name):
    im = lights()
    for args in ([0.0] * len(optics.DEFAULTS[name]),
                 [hi for lo, hi in optics.CLAMP[name]],
                 [lo - 500.0 for lo, _ in optics.CLAMP[name]],
                 [hi + 500.0 for _, hi in optics.CLAMP[name]]):
        out = run(name, im, args)
        assert out.mode == "RGB" and out.size == SIZE


@pytest.mark.parametrize("name", sorted(optics.APPLIERS))
def test_a_small_frame_is_not_special_cased_into_a_crash(name):
    im = Image.new("RGB", (40, 30), BASE)
    out = run(name, im, LOUD[name])
    assert out.size == (40, 30) and out.mode == "RGB"


def test_no_operation_touches_the_picture_it_was_given():
    im = lights()
    before = im.tobytes()
    for name, args in LOUD.items():
        run(name, im, args)
        assert im.tobytes() == before, f"{name} mutated its input"


def test_a_recipe_runs_in_the_order_it_arrives(tmp_path):
    im = Image.new("RGB", SIZE, BASE)
    ImageDraw.Draw(im).ellipse([120, 380, 150, 410], fill=(250, 250, 250))
    im.save(tmp_path / "in.png")
    recipe = [
        ["orton", 0.6, 0.5],
        ["lightleak", 300.0, 1.0, 0.47, 0.157, 0.7],
        ["glitch", 0.4, 0.3, 0.5, 0.25],
        ["tiltshift", 0.45, 0.3, 0.8, 10.0],
        ["not_an_optic", 1, 2, 3],
        [],
        "junk",
    ]
    out = optics.apply(Image.open(tmp_path / "in.png"), recipe)
    assert out.mode == "RGB"
    out.save(tmp_path / "out.png")
    assert Image.open(tmp_path / "out.png").tobytes() == out.tobytes()
    assert diff(Image.open(tmp_path / "in.png"), out).getbbox() is not None
    assert optics.apply(im, []) is im


def test_a_recipes_op_runs_once_and_no_further(tmp_path):
    im = lights()
    once = optics.apply(im, [["orton", 1.0, 0.6]])
    twice = optics.apply(im, [["orton", 1.0, 0.6], ["orton", 1.0, 0.6]])
    assert once.tobytes() == twice.tobytes()
    assert optics.LIMITS["orton"] == 1


def test_no_operation_falls_back_to_walking_pixels():
    """The budget is a multiple of one whole-frame Pillow pass, measured on this machine in
    this moment: a busy laptop shifts both together, and a Python pixel loop costs 100x."""
    preview = step_edge().resize((900, 1200), Image.NEAREST)
    started = time.time()
    ImageChops.add(preview, preview)
    pass_cost = max(time.time() - started, 0.01)
    loud = {
        "tiltshift": [0.5, 0.22, 1.0, 20.0],
        "motion_blur": [35.0, 0.2],
        "radial_blur": [0.5, 0.5, 1.0, 0.4],
        "prism": [1.0, 0.4, 0.6],
        "bokeh": [0.5, 1.0, 0.15, 20.0],
        "orton": [1.0, 1.0],
        "lightleak": [300.0, 1.0, 0.47, 0.235, 1.0],
        "glitch": [1.0, 1.0, 1.0, 0.5],
        "fisheye": [0.9, 0.5, 0.5],
    }
    for name, args in loud.items():
        started = time.time()
        out = run(name, preview, args)
        took = time.time() - started
        assert out.size == preview.size
        assert took < 60 * pass_cost, f"{name} cost {took:.2f} s against a {pass_cost:.2f} s pass"
