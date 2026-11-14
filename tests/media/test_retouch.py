import math
import time

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageMath

from src.media.retouch import APPLIERS, CLAMP, LIMITS, SHAPE

SIZE = (600, 900)

GOOD = {
    "smooth": [0.5, 0.55, 0.25, 0.8],
    "texture": [0.5, 0.55, 0.25, 0.8],
    "matte": [0.5, 0.55, 0.25, 0.9],
    "whiten": [0.5, 0.55, 0.25, 0.9],
    "brighten": [0.5, 0.55, 0.25, 0.8, 0.5],
    "tint": [0.5, 0.55, 0.25, 0.9, 350.0, 0.6],
    "warp": [0.5, 0.55, 0.25, 0.8, 0.0, 0.5, 0.0],
    "eyes": [0.5, 0.5, 0.12, 0.9],
}


def gritty(im, sigma=50, amt=0.5):
    """Per-pixel grey noise around the colours already there, without wrecking them."""
    n = Image.effect_noise(im.size, sigma).convert("L").convert("I")
    return Image.merge("RGB", tuple(
        ImageMath.unsafe_eval("convert(c + (n - 128) * a, 'L')", c=c.convert("I"), n=n, a=amt)
        for c in im.split()))


def skin():
    """A dark field, a noisy skin disc and a near-white shine blob at its centre."""
    im = Image.new("RGB", SIZE, (28, 30, 36))
    d = ImageDraw.Draw(im)
    d.ellipse([150, 300, 450, 700], fill=(185, 145, 120))
    d.ellipse([255, 455, 345, 545], fill=(238, 230, 220))
    return gritty(im)


def probe_outside(name, args):
    """Pixels well clear of every disc the suite aims at the middle of the frame."""
    im = skin()
    out = APPLIERS[name](im, args)
    assert out.mode == "RGB" and out.size == SIZE
    for pt in [(10, 10), (590, 10), (10, 890), (590, 890), (300, 60), (300, 850)]:
        assert out.getpixel(pt) == im.getpixel(pt), f"{name} moved {pt}"
    return im, out


@pytest.mark.parametrize("name", sorted(APPLIERS))
def test_each_op_acts_inside_and_leaves_the_rest_byte_identical(name):
    im, out = probe_outside(name, GOOD[name])
    diff = ImageChops.difference(im, out).convert("L")
    assert diff.getbbox() is not None, f"{name} did nothing inside its disc"


@pytest.mark.parametrize("name", sorted(APPLIERS))
def test_zero_amount_is_a_no_op(name):
    args = list(GOOD[name])
    args[3] = 0.0
    im = skin()
    assert APPLIERS[name](im, args).tobytes() == im.tobytes()


@pytest.mark.parametrize("name", sorted(APPLIERS))
def test_neutral_mode_and_mid_are_no_ops_at_zero_amount(name):
    args = list(GOOD[name])
    args[3] = 0.0
    if name == "warp":
        args[4] = 2.0
        args[6] = 137.0
    if name == "brighten":
        args[4] = 0.0
    im = skin()
    assert APPLIERS[name](im, args).tobytes() == im.tobytes()


@pytest.mark.parametrize("name", sorted(APPLIERS))
def test_extra_and_truncated_args_are_ignored(name):
    k = len(CLAMP[name])
    im = skin()
    plain = APPLIERS[name](im, GOOD[name])
    assert APPLIERS[name](im, GOOD[name] + [0.7] * (k - 1)).tobytes() == plain.tobytes()
    assert APPLIERS[name](im, GOOD[name][: k - 1]).tobytes() == im.tobytes()


@pytest.mark.parametrize("name", sorted(APPLIERS))
def test_junk_never_raises(name):
    im = skin()
    junk = [
        [],
        ["a", "b", "c", "d", "e", "f", "g"],
        [0.5, float("nan"), 0.2, 0.5, 0.0, 0.0, 0.0],
        [5.0, -9.0, 50.0, 9.0, 7.0, 3.0, 999.0],
        [None, None, None, None, None, None, None],
    ]
    for args in junk:
        out = APPLIERS[name](im, args)
        assert out.mode == "RGB" and out.size == SIZE


def test_input_is_never_mutated():
    im = skin()
    before = im.tobytes()
    for name, args in GOOD.items():
        APPLIERS[name](im, args)
    assert im.tobytes() == before


def test_several_strokes_in_one_group_run_in_order():
    im = skin()
    a = GOOD["smooth"]
    b = [0.25, 0.35, 0.12, 0.9]
    out = APPLIERS["smooth"](im, a + b)
    diff = ImageChops.difference(im, out).convert("L")
    assert diff.crop((114, 263, 186, 367)).getbbox() is not None
    assert diff.crop((225, 420, 375, 570)).getbbox() is not None


def test_smooth_rolls_out_noise_but_keeps_the_shading():
    im = skin()
    out = APPLIERS["smooth"](im, [0.5, 0.55, 0.25, 1.0])
    box = (265, 460, 335, 530)   # inside the fully feathered core of the disc

    def spread(x):
        px = list(x.convert("L").getdata())
        mu = sum(px) / len(px)
        return math.sqrt(sum((v - mu) ** 2 for v in px) / len(px))

    assert spread(out.crop(box)) < spread(im.crop(box)) * 0.75


def test_texture_adds_detail_back_inside_the_disc():
    im = skin()
    smoothed = APPLIERS["smooth"](im, [0.5, 0.55, 0.25, 1.0])
    back = APPLIERS["texture"](smoothed, [0.5, 0.55, 0.25, 1.0])
    box = (225, 425, 375, 575)
    assert ImageChops.difference(back.crop(box), smoothed.crop(box)).getbbox() is not None


def test_matte_kills_a_bright_weakly_coloured_shine():
    im = Image.new("RGB", (400, 400), (170, 120, 95))
    d = ImageDraw.Draw(im)
    d.ellipse([150, 150, 250, 250], fill=(250, 246, 242))   # shine: bright, near neutral
    d.ellipse([120, 200, 190, 260], fill=(210, 40, 30))     # saturated colour: keep
    out = APPLIERS["matte"](im, [0.5, 0.5, 0.6, 1.0])
    assert out.getpixel((200, 200)) != im.getpixel((200, 200))
    assert sum(out.getpixel((200, 200))) < sum(im.getpixel((200, 200)))
    assert out.getpixel((150, 235)) == im.getpixel((150, 235))
    assert out.getpixel((6, 6)) == im.getpixel((6, 6))


def test_whiten_lifts_only_the_white_end_and_cools_it():
    im = Image.new("RGB", (400, 400), (60, 50, 45))
    d = ImageDraw.Draw(im)
    d.rectangle([140, 140, 260, 260], fill=(232, 222, 200))  # yellowed teeth
    out = APPLIERS["whiten"](im, [0.5, 0.5, 0.5, 1.0])
    r, g, b = out.getpixel((200, 200))
    assert (r, g, b) != im.getpixel((200, 200))
    assert b > 200 and r < 232                               # yellow neutralised
    assert out.getpixel((20, 20)) == im.getpixel((20, 20))   # dark field untouched


def test_brighten_moves_only_luma_near_mid():
    im = Image.new("RGB", (400, 400), (128, 128, 128))
    d = ImageDraw.Draw(im)
    d.rectangle([100, 100, 180, 180], fill=(250, 250, 250))  # far above any mid gate
    d.rectangle([220, 220, 300, 300], fill=(130, 130, 130))  # right at mid 0.5
    out = APPLIERS["brighten"](im, [0.5, 0.5, 0.7, 0.8, 0.5])
    assert out.getpixel((260, 260)) != im.getpixel((260, 260))
    assert out.getpixel((140, 140)) == im.getpixel((140, 140))
    assert out.getpixel((8, 8)) == im.getpixel((8, 8))


def test_tint_rotates_colour_without_painting_grey_or_dark():
    im = Image.new("RGB", (400, 400), (150, 120, 100))
    d = ImageDraw.Draw(im)
    d.rectangle([120, 120, 200, 200], fill=(200, 90, 80))    # lip colour
    d.rectangle([240, 240, 320, 320], fill=(235, 235, 235))  # tooth white: no hue
    out = APPLIERS["tint"](im, [0.5, 0.5, 0.8, 1.0, 300.0, 0.8])
    assert out.getpixel((160, 160)) != im.getpixel((160, 160))
    assert out.getpixel((280, 280)) == im.getpixel((280, 280))
    assert out.getpixel((4, 4)) == im.getpixel((4, 4))


def step_frame():
    im = Image.new("RGB", (400, 400), (40, 40, 40))
    ImageDraw.Draw(im).rectangle([250, 120, 400, 340], fill=(220, 220, 220))
    return im


def edge_column(im):
    row = 200
    for x in range(150, 300):
        if sum(im.getpixel((x, row))) > 3 * 120:
            return x
    return 300


def test_warp_pinches_in_and_pushes_out_in_opposite_directions():
    im = step_frame()
    plain = edge_column(im)
    slim = APPLIERS["warp"](im, [0.5, 0.5, 0.8, -1.0, 0.0, 0.5, 0.0])
    push = APPLIERS["warp"](im, [0.5, 0.5, 0.8, 1.0, 0.0, 0.5, 0.0])
    assert edge_column(slim) < plain < edge_column(push)
    for out in (slim, push):
        for pt in [(3, 3), (396, 3), (3, 396), (396, 396)]:
            assert out.getpixel(pt) == im.getpixel(pt), "far corners must not budge"
        # inside the box but outside the circle: q = 219 / 160 > 1, so untouched
        assert out.getpixel((45, 45)) == im.getpixel((45, 45))


def test_warp_mode_two_pushes_along_the_angle():
    im = step_frame()

    def top_edge(x, frame):
        # 390 sits between the dark (120) and the lit patch (660), so it lands
        # on the same half-blended seam whichever way the mesh dragged it.
        for y in range(100, 250):
            if sum(frame.getpixel((x, y))) > 3 * 130:
                return y
        return 250

    down = APPLIERS["warp"](im, [0.5, 0.5, 0.8, 1.0, 2.0, 0.5, 90.0])
    left = APPLIERS["warp"](im, [0.5, 0.5, 0.8, 1.0, 2.0, 0.5, 180.0])
    assert top_edge(300, down) > top_edge(300, im)
    assert edge_column(left) < edge_column(im)


def test_warp_clamps_absurd_sizes_and_zero_amount():
    im = step_frame()
    out = APPLIERS["warp"](im, [0.5, 0.5, 5000.0, 1.0, 0.0, 0.5, 0.0])
    assert out.size == im.size
    for pt in [(2, 200), (397, 200)]:
        assert out.getpixel(pt) == im.getpixel(pt), "clamped disc still leaves the frame edge"
    assert APPLIERS["warp"](im, [0.5, 0.5, 0.8, 0.0, 0.0, 0.5, 0.0]).tobytes() == im.tobytes()


def test_eyes_whiten_and_enlarge_together():
    im = Image.new("RGB", (300, 300), (90, 70, 65))
    d = ImageDraw.Draw(im)
    d.ellipse([70, 120, 230, 180], fill=(230, 232, 236))    # sclera
    d.ellipse([130, 128, 170, 172], fill=(80, 55, 150))     # iris
    out = APPLIERS["eyes"](im, [0.5, 0.5, 0.12, 0.9])
    diff = ImageChops.difference(im, out).convert("L")
    assert diff.getbbox() is not None
    assert out.getpixel((145, 150)) != im.getpixel((145, 150))   # iris at the tap
    assert out.getpixel((6, 6)) == im.getpixel((6, 6))


def test_three_smooth_strokes_on_a_600x900_frame_are_fast():
    im = gritty(Image.new("RGB", SIZE, (170, 130, 105)))
    args = [0.3, 0.35, 0.3, 0.8, 0.6, 0.5, 0.25, 0.8, 0.5, 0.7, 0.3, 0.8]
    t0 = time.perf_counter()
    out = APPLIERS["smooth"](im, args)
    secs = time.perf_counter() - t0
    assert out.size == SIZE and ImageChops.difference(im, out).getbbox() is not None
    assert secs < 2.0, f"3 strokes took {secs:.2f}s"


def test_contract_tables_agree_with_the_appliers():
    assert set(APPLIERS) == {"smooth", "texture", "matte", "whiten",
                             "brighten", "tint", "warp", "eyes"}
    assert set(SHAPE) == set(CLAMP) == set(LIMITS) == set(APPLIERS)
    for name, shape in SHAPE.items():
        assert shape[0] == "group" and shape[1] == len(CLAMP[name])
        assert shape[2] == LIMITS[name] and 40 <= LIMITS[name] <= 60
        assert all(len(pair) == 2 and pair[0] <= pair[1] for pair in CLAMP[name])
