"""The reshape brush: swirl and inflate, proved by where the pixels ended up.

Both promises are the same shape - inside the brush the geometry really moves, and outside
it every pixel comes back exactly as it went in.
"""

import time

import pytest
from PIL import Image, ImageChops, ImageDraw

from src.media import mesh

SIZE = (600, 800)
W, H = SIZE
BASE = (120, 125, 130)
BRUSH = 0.40
R = 0.5 * BRUSH * min(SIZE)                       # 120 px of radius at this size
BOX = (int(W / 2 - R), int(H / 2 - R), int(W / 2 + R), int(H / 2 + R))

GOOD = {"swirl": [0.5, 0.5, BRUSH, 90.0, 0.45], "inflate": [0.5, 0.5, BRUSH, 0.8, 0.45]}


def run(name, im, args):
    return mesh.APPLIERS[name](im, args)


def diff(im, out):
    return ImageChops.difference(im.convert("RGB"), out.convert("RGB")).convert("L")


def ink_box(im, out):
    return diff(im, out).getbbox()


def ink_fraction(im, out):
    hist = diff(im, out).histogram()
    return sum(hist[2:]) / (W * H)


def marks():
    """A bar straight down the middle of the frame, a second bar off to the side for a
    second brush to find, and a mark nowhere near either."""
    im = Image.new("RGB", SIZE, BASE)
    d = ImageDraw.Draw(im)
    d.rectangle([292, 0, 308, H], fill=(240, 240, 240))
    d.rectangle([140, 160, 160, 320], fill=(240, 240, 240))
    d.rectangle([80, 380, 100, 420], fill=(200, 200, 200))
    return im


def offset_bar():
    """A bar 40 px right of the frame's middle - the thing an inflate moves and a pinch
    pulls back."""
    im = Image.new("RGB", SIZE, BASE)
    d = ImageDraw.Draw(im)
    d.rectangle([330, 0, 350, H], fill=(240, 240, 240))
    d.rectangle([60, 60, 90, 90], fill=(200, 200, 200))
    return im


def centroid(im, row, x0=250, x1=360, mid=200):
    """Which column the bar is standing in on this row."""
    g = im.convert("L")
    xs = [x for x in range(x0, x1) if g.getpixel((x, row)) >= mid]
    return sum(xs) / len(xs) if xs else None


def edges(im, row, x0=310, x1=460, mid=200):
    g = im.convert("L")
    xs = [x for x in range(x0, x1) if g.getpixel((x, row)) >= mid]
    return (xs[0], xs[-1]) if xs else None


def outside_the_brush(im, out, box=BOX):
    """Every part of the frame past the square the brush lives in."""
    d = diff(im, out)
    for crop in [(0, 0, W, box[1] - 2), (0, box[3] + 2, W, H),
                 (0, box[1] - 2, box[0] - 2, box[3] + 2),
                 (box[2] + 2, box[1] - 2, W, box[3] + 2)]:
        assert d.crop(crop).getbbox() is None, f"the brush reached {crop}"
    for pt in [(1, 1), (W - 2, 1), (1, H - 2), (W - 2, H - 2)]:
        assert out.getpixel(pt) == im.getpixel(pt)


def ink_stays_inside_the_brush(im, out, box=BOX):
    found = ink_box(im, out)
    assert found is not None, "the brush did nothing"
    assert found[0] >= box[0] - 2 and found[2] <= box[2] + 2
    assert found[1] >= box[1] - 2 and found[3] <= box[3] + 2


# ------------------------------------------------------------------------------ swirl


def test_swirl_twists_inside_the_brush_and_leaves_the_rest_of_the_picture_alone():
    im = marks()
    out = run("swirl", im, [0.5, 0.5, BRUSH, 60.0, 0.45])
    assert out.mode == "RGB" and out.size == SIZE
    assert centroid(im, 320) == 300.0                        # the bar stands on the axis
    # the twist leans it: above the middle it goes right, below it goes left, and on the
    # axis itself the rotation is a shear, not a shift
    assert centroid(out, 320) > 325
    assert abs(centroid(out, 400) - 300.0) < 6
    assert centroid(out, 480) < 275
    ink_stays_inside_the_brush(im, out)
    assert 0 < ink_fraction(im, out) < 0.05
    outside_the_brush(im, out)
    assert out.getpixel((90, 400)) == im.getpixel((90, 400))   # the mark down the side
    assert out.getpixel((BOX[0], 400)) == im.getpixel((BOX[0], 400))


def test_swirl_reverses_with_the_sign_of_its_angle():
    im = marks()
    right = run("swirl", im, [0.5, 0.5, BRUSH, 60.0, 0.45])
    left = run("swirl", im, [0.5, 0.5, BRUSH, -60.0, 0.45])
    assert centroid(right, 320) > 325 and centroid(right, 480) < 275
    assert centroid(left, 320) < 275 and centroid(left, 480) > 325
    assert abs(centroid(right, 400) - centroid(left, 400)) < 8
    assert right.tobytes() != left.tobytes()
    outside_the_brush(im, left)


def test_swirl_strength_is_the_angle_and_the_brush_is_the_size():
    im = marks()
    small = run("swirl", im, [0.5, 0.5, 0.12, 120.0, 0.45])
    big = run("swirl", im, [0.5, 0.5, 0.5, 120.0, 0.45])
    assert ink_fraction(im, small) < ink_fraction(im, big)
    sb, bb = ink_box(im, small), ink_box(im, big)
    assert sb and bb and (sb[2] - sb[0]) < (bb[2] - bb[0])
    assert ink_fraction(im, run("swirl", im, [0.5, 0.5, BRUSH, 360.0, 0.45])) > 0.0
    # a brush narrower than two pixels is nothing to warp, and nothing breaks
    assert run("swirl", im, [0.5, 0.5, 0.001, 120.0, 0.45]).tobytes() == im.tobytes()


# ----------------------------------------------------------------------------- inflate


def test_inflate_magnifies_inside_the_brush_and_stops_at_its_rim():
    im = offset_bar()
    out = run("inflate", im, [0.5, 0.5, BRUSH, 0.8, 0.45])
    src, moved = edges(im, 400), edges(out, 400)
    # a full inflate reads the plate at 1 - 0.8 * 0.55 of its distance from the middle, so
    # the bar lands further out and wider than it went in
    assert src == (330, 350)
    assert moved[0] > src[0] + 15 and moved[1] > src[1] + 15
    assert (moved[1] - moved[0]) > (src[1] - src[0])
    assert centroid(out, 400, 310, 460) > 360
    ink_stays_inside_the_brush(im, out)
    assert 0 < ink_fraction(im, out) < 0.05
    outside_the_brush(im, out)
    assert out.getpixel((75, 75)) == im.getpixel((75, 75))


def test_inflate_negative_pinches_instead_of_swelling():
    im = offset_bar()
    src = edges(im, 400)
    out = run("inflate", im, [0.5, 0.5, BRUSH, -0.8, 0.45])
    moved = edges(out, 400)
    assert moved[0] < src[0] and moved[1] < src[1] - 10       # pulled toward the middle
    assert (moved[1] - moved[0]) < (src[1] - src[0])          # and squeezed narrower
    assert centroid(out, 400, 310, 460) < 335
    ink_stays_inside_the_brush(im, out)
    outside_the_brush(im, out)
    assert ink_box(im, out) != ink_box(im, run("inflate", im, [0.5, 0.5, BRUSH, 0.8, 0.45]))


# --------------------------------------------------------------------- the shared contract


@pytest.mark.parametrize("name", sorted(mesh.APPLIERS))
def test_zero_is_the_no_op_it_claims(name):
    im = marks()
    args = list(GOOD[name])
    args[3] = 0.0
    assert run(name, im, args).tobytes() == im.tobytes()


@pytest.mark.parametrize("name", sorted(mesh.APPLIERS))
def test_a_loud_stroke_actually_moves_the_picture(name):
    im = marks()
    assert ink_box(im, run(name, im, GOOD[name])) is not None, f"{name} did nothing"


@pytest.mark.parametrize("name", sorted(mesh.APPLIERS))
def test_junk_short_and_partial_arguments_are_dropped(name):
    im = marks()
    k = len(mesh.CLAMP[name])
    for args in ([], None, ["a", "b", "c", "d", "e"], [None] * k, [float("nan")] * k,
                 GOOD[name][:k - 1], [0.5, float("inf"), 0.4, 90.0, 0.45]):
        out = run(name, im, args)
        assert out.mode == "RGB" and out.size == SIZE
        assert out.tobytes() == im.tobytes(), f"{name} took {args}"


@pytest.mark.parametrize("name", sorted(mesh.APPLIERS))
def test_extra_arguments_start_another_stroke_and_a_whole_group_runs(name):
    im = marks()
    plain = run(name, im, GOOD[name])
    assert run(name, im, GOOD[name] + [0.3] * 3).tobytes() == plain.tobytes()
    assert run(name, im, GOOD[name] + GOOD[name]).tobytes() != plain.tobytes()


@pytest.mark.parametrize("name", sorted(mesh.APPLIERS))
def test_clamps_hold_at_both_ends(name):
    im = marks()
    for args in ([hi for lo, hi in mesh.CLAMP[name]],
                 [lo - 500.0 for lo, _ in mesh.CLAMP[name]],
                 [hi + 500.0 for _, hi in mesh.CLAMP[name]]):
        out = run(name, im, args)
        assert out.mode == "RGB" and out.size == SIZE
        outside_the_brush(im, out, BOX)


@pytest.mark.parametrize("name", sorted(mesh.APPLIERS))
def test_every_op_returns_the_mode_it_was_given_and_keeps_the_alpha(name):
    im = Image.new("RGBA", SIZE, (200, 100, 50, 90))
    ImageDraw.Draw(im).rectangle([292, 0, 308, H], fill=(240, 240, 240, 255))
    out = run(name, im, GOOD[name])
    assert out.mode == "RGBA" and out.size == SIZE
    assert out.getchannel("A").tobytes() == im.getchannel("A").tobytes()
    assert run(name, im.convert("RGB"), GOOD[name]).mode == "RGB"


@pytest.mark.parametrize("name", sorted(mesh.APPLIERS))
def test_a_small_frame_is_not_special_cased_into_a_crash(name):
    im = Image.new("RGB", (40, 30), BASE)
    ImageDraw.Draw(im).rectangle([18, 0, 22, 30], fill=(240, 240, 240))
    out = run(name, im, GOOD[name])
    assert out.size == (40, 30) and out.mode == "RGB"


def test_several_strokes_in_one_group_run_in_order():
    im = marks()
    first, second = [0.5, 0.5, 0.3, 90.0, 0.45], [0.25, 0.3, 0.2, -120.0, 0.45]
    out = run("swirl", im, first + second)
    d = diff(im, out)
    assert d.crop((240, 320, 360, 480)).getbbox() is not None      # the middle brush
    assert d.crop((100, 190, 200, 290)).getbbox() is not None      # the one up left
    assert d.crop((0, 560, W, H)).getbbox() is None                # and nothing below them
    assert out.tobytes() != run("swirl", im, first).tobytes()


def test_no_operation_touches_the_picture_it_was_given():
    im = marks()
    before = im.tobytes()
    for name, args in GOOD.items():
        run(name, im, args)
        assert im.tobytes() == before, f"{name} mutated its input"


def test_a_recipe_runs_in_the_order_it_arrives(tmp_path):
    im = marks()
    source = tmp_path / "in.png"
    im.save(source)
    recipe = [
        ["swirl", 0.5, 0.5, 0.3, 80.0, 0.45],
        ["inflate", 0.5, 0.5, 0.3, 0.6, 0.45],
        ["not_a_brush", 1, 2, 3],
        [],
        "junk",
    ]
    out = mesh.apply(Image.open(source), recipe)
    assert out.mode == "RGB" and out.size == SIZE
    target = tmp_path / "out.png"
    out.save(target)
    assert Image.open(target).tobytes() == out.tobytes()
    assert ImageChops.difference(Image.open(source), out).getbbox() is not None
    assert mesh.apply(im.convert("RGBA"), []).mode == "RGB"
    outside_the_brush(im.convert("RGB"), out)


def test_a_recipes_brush_caps_at_its_limit():
    im = marks()
    entry = ["swirl", 0.5, 0.5, 0.1, 90.0, 0.45]          # a small brush on the middle bar
    assert mesh.LIMITS["swirl"] == 40
    assert len(mesh._strokes(GOOD["swirl"] * 80, "swirl")) == 40
    assert mesh.apply(im, [entry] * 40).tobytes() == mesh.apply(im, [entry] * 80).tobytes()
    assert mesh.apply(im, [entry]).tobytes() != mesh.apply(im, [entry] * 4).tobytes()
    assert ink_box(im, mesh.apply(im, [entry] * 40)) is not None


def test_no_operation_falls_back_to_walking_pixels():
    """The budget is a multiple of one whole-frame Pillow pass, measured on this machine in
    this moment: a busy laptop shifts both together, and a Python pixel loop costs 100x."""
    preview = marks().resize((900, 1200), Image.NEAREST)
    started = time.time()
    ImageChops.add(preview, preview)
    pass_cost = max(time.time() - started, 0.01)
    every = [
        ("swirl", [0.5, 0.5, 0.4, 120.0, 0.45]),
        ("swirl", [0.3, 0.4, 0.3, -90.0, 0.45, 0.7, 0.6, 0.3, 90.0, 0.45]),
        ("inflate", [0.5, 0.5, 0.4, 0.9, 0.45]),
        ("inflate", [0.35, 0.45, 0.3, -0.9, 0.45, 0.65, 0.55, 0.3, 0.9, 0.45]),
    ]
    for name, args in every:
        started = time.time()
        out = run(name, preview, args)
        took = time.time() - started
        assert out.size == preview.size
        assert took < 12 * pass_cost, f"{name} cost {took:.2f} s against a {pass_cost:.2f} s pass"
