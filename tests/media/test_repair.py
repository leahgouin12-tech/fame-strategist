"""What each repair tool actually touches, and what it leaves alone.

Every test here is a placement proof: the pixels a tool claims to change do change, and
the pixels it does not claim stay byte-identical. The two colour-window tools are also
tested for what they honestly catch by mistake - a terracotta tile inside the skin
window is selected exactly like a cheek, and that is in their notes, so it is in here.
Nothing is written outside tmp_path.
"""

import colorsys
import math

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageMath

from src.media import repair
from src.media.repair import APPLIERS, CLAMP, LIMITS, SHAPE

SIZE = (600, 600)


def grit(im, sigma=34, amt=0.5):
    """Per-pixel grey noise around the colours already there, without wrecking them."""
    n = Image.effect_noise(im.size, sigma).convert("L").convert("I")
    return Image.merge("RGB", tuple(
        ImageMath.unsafe_eval("convert(c + (n - 128) * a, 'L')", c=c.convert("I"), n=n, a=amt)
        for c in im.split()))


def diff(im, out):
    return ImageChops.difference(im.convert("RGB"), out.convert("RGB")).convert("L")


def ink_box(im, out):
    return diff(im, out).getbbox()


def ink_fraction(im, out):
    hist = diff(im, out).histogram()
    return sum(hist[2:]) / (im.width * im.height)


def mean_std(crop):
    """Mean and spread per band, off the histogram: that is how this project does numpy."""
    out = []
    for ch in crop.split():
        h = ch.histogram()
        n = sum(h) or 1
        mu = sum(i * h[i] for i in range(256)) / n
        var = sum((i - mu) ** 2 * h[i] for i in range(256)) / n
        out.append((mu, math.sqrt(max(var, 0.0))))
    return out


def luma(pixel):
    return 0.299 * pixel[0] + 0.587 * pixel[1] + 0.114 * pixel[2]


def hsv_of(pixel):
    h, s, v = colorsys.rgb_to_hsv(*(c / 255.0 for c in pixel[:3]))
    return h * 360.0, s * 255.0, v * 255.0


def inside(box, point):
    return box[0] <= point[0] < box[2] and box[1] <= point[1] < box[3]


# --------------------------------------------------------------------------- patch

STRIPES = (120, 400, 260, 520)


def patch_scene():
    """A bright blemish on dark skin where she taps, real texture 0.47 frame-heights below."""
    im = Image.new("RGB", SIZE, (150, 120, 100))
    d = ImageDraw.Draw(im)
    d.rectangle([200, 80, 400, 280], fill=(70, 55, 45))
    d.ellipse([272, 152, 328, 208], fill=(205, 185, 170))
    for x in range(STRIPES[0], STRIPES[2], 8):
        d.rectangle([x, STRIPES[1], x + 4, STRIPES[3]], fill=(235, 230, 225))
    return im


def test_patch_lands_source_texture_and_tone_match_closes_the_mean_gap():
    im = patch_scene()
    stroke = [0.5, 0.30, 0.20, 0.85, -0.18, 0.47]      # tap, brush, radius, sample offset

    flat = APPLIERS["patch"](im, stroke + [0.40, 0.0])   # tone match off
    box = ink_box(im, flat)
    assert box is not None
    assert 216 <= box[0] and box[2] <= 384, "the paste left its disc horizontally"
    assert 114 <= box[1] and box[3] <= 246, "the paste left its disc vertically"
    assert im.getpixel((6, SIZE[1] - 6)) == flat.getpixel((6, SIZE[1] - 6))
    assert im.getpixel((SIZE[0] - 6, 6)) == flat.getpixel((SIZE[0] - 6, 6))

    here = (282, 162, 318, 198)      # the middle of the pasted disc, mask at full weight
    there = (166, 436, 218, 488)     # the middle of the disc it was sampled from
    before = mean_std(im.crop(here))
    after = mean_std(flat.crop(here))
    src = mean_std(im.crop(there))
    assert before[0][1] < 2.0, "the blemish should start out flat"
    assert after[0][1] > before[0][1] + 25, "no texture arrived in the destination"
    assert abs(after[0][0] - src[0][0]) < 12, "the pixels are not the sample's own"

    matched = APPLIERS["patch"](im, stroke + [0.40, 1.0])   # tone match on
    ring = mean_std(im.crop((210, 215, 390, 275)))[0][0]     # the skin around the blemish
    gap_before = abs(before[0][0] - ring)
    gap_after = abs(mean_std(matched.crop(here))[0][0] - ring)
    assert gap_before > 60, "the scene has no mean gap to close"
    assert gap_after < 0.25 * gap_before, f"tone match closed only {gap_after} of {gap_before}"
    assert matched.getpixel((6, 6)) == im.getpixel((6, 6))
    assert ink_fraction(im, matched) < 0.04


# ------------------------------------------------------------------------- conceal

def eye_scene():
    """Noisy skin, a darker under-eye band under the tap, a highlight inside the brush."""
    im = Image.new("RGB", SIZE, (215, 180, 155))
    d = ImageDraw.Draw(im)
    d.ellipse([210, 250, 390, 350], fill=(150, 115, 105))
    d.ellipse([332, 244, 364, 270], fill=(246, 243, 238))
    return grit(im)


def test_conceal_smooths_and_lifts_the_shadow_band_only():
    im = eye_scene()
    out = APPLIERS["conceal"](im, [0.5, 0.5, 0.34, 0.9, 0.0])
    band = (236, 280, 364, 320)                     # the shadow, away from its own edge
    before, after = mean_std(im.crop(band)), mean_std(out.crop(band))
    assert before[0][1] > 8.0, "the scene should start out grainy"
    assert after[0][1] < before[0][1] - 5, "the grain in the band survived the smooth"
    assert im.getpixel((10, 10)) == out.getpixel((10, 10))

    lifted = APPLIERS["conceal"](im, [0.5, 0.5, 0.34, 0.9, 0.7])
    assert mean_std(lifted.crop(band))[0][0] > mean_std(out.crop(band))[0][0] + 2, \
        "the lift never reached the shadow"
    assert mean_std(lifted.crop(band))[0][1] < before[0][1], "the band is not smoother"
    shine = (340, 250, 358, 264)                    # the highlight, inside the same brush
    assert mean_std(lifted.crop(shine))[0][0] < mean_std(out.crop(shine))[0][0] + 4, \
        "a narrow-band dodge reached a highlight it should leave alone"
    assert lifted.getpixel((10, SIZE[1] - 10)) == im.getpixel((10, SIZE[1] - 10))
    box = ink_box(im, lifted)
    assert 198 <= box[0] and box[2] <= 402 and 198 <= box[1] and box[3] <= 402
    assert ink_fraction(im, lifted) < 0.16


# ------------------------------------------------------------------------ red_eye

def eye_red_scene():
    """A dark-red pupil at the tap on white, with bright red and blue inside the brush."""
    im = Image.new("RGB", SIZE, (238, 236, 232))
    d = ImageDraw.Draw(im)
    d.ellipse([270, 270, 330, 330], fill=(130, 40, 45))
    d.rectangle([256, 224, 286, 254], fill=(205, 45, 45))
    d.rectangle([318, 352, 348, 382], fill=(60, 90, 200))
    return im


def test_red_eye_darkens_the_cluster_and_leaves_white_red_and_blue_alone():
    im = eye_red_scene()
    assert inside((198, 198, 402, 402), (271, 239)) and inside((198, 198, 402, 402), (333, 367))
    out = APPLIERS["red_eye"](im, [0.5, 0.5, 0.34, 0.9])
    was, centre = im.getpixel((300, 300)), out.getpixel((300, 300))
    assert centre[0] < was[0] - 20, "the red did not come down"
    assert centre[0] - centre[2] < 8, "it is still carrying a red cast"
    assert luma(centre) < luma(was), "it was not darkened"
    assert out.getpixel((271, 239)) == im.getpixel((271, 239)), "bright red is not red-eye"
    assert out.getpixel((333, 367)) == im.getpixel((333, 367)), "blue was touched"
    assert out.getpixel((300, 248)) == im.getpixel((300, 248)), "the sclera was touched"
    assert out.getpixel((5, 5)) == im.getpixel((5, 5))
    assert ink_fraction(im, out) < 0.02


# ---------------------------------------------------------------------------- dewy

def shine_scene():
    """Skin with a pale shine at the tap, a saturated cheek and a dark patch, all in reach."""
    im = Image.new("RGB", SIZE, (198, 150, 122))
    d = ImageDraw.Draw(im)
    d.ellipse([262, 262, 338, 338], fill=(236, 233, 229))
    d.rectangle([232, 236, 262, 266], fill=(232, 108, 66))
    d.rectangle([330, 236, 366, 268], fill=(120, 96, 80))
    return im


def test_dewy_lifts_the_pale_shine_and_not_the_colour_or_the_darks():
    im = shine_scene()
    out = APPLIERS["dewy"](im, [0.5, 0.5, 0.28, 0.95])
    before, after = luma(im.getpixel((300, 300))), luma(out.getpixel((300, 300)))
    assert after > before + 4, "the shine did not lift"
    assert hsv_of(out.getpixel((300, 300)))[1] <= hsv_of(im.getpixel((300, 300)))[1] + 6, \
        "the lift added colour instead of gloss"
    assert out.getpixel((247, 251)) == im.getpixel((247, 251)), "a saturated pixel was lifted"
    assert out.getpixel((348, 252)) == im.getpixel((348, 252)), "a dark pixel was lifted"
    assert out.getpixel((4, 4)) == im.getpixel((4, 4))
    box = ink_box(im, out)
    assert box is not None and box[1] >= 0.35 * SIZE[1] and box[3] <= 0.65 * SIZE[1]


# ------------------------------------------------------------------------ flyaway

def hair_scene():
    """Fine dark strands on a light ground, a wide dark block, the same strands outside."""
    im = Image.new("RGB", SIZE, (214, 214, 214))
    d = ImageDraw.Draw(im)
    for x in (230, 250, 270):
        d.rectangle([x, 240, x + 1, 360], fill=(68, 66, 64))
    d.rectangle([330, 240, 400, 320], fill=(60, 58, 56))
    for x in (60, 80, 100):
        d.rectangle([x, 240, x + 1, 360], fill=(68, 66, 64))
    return im


def test_flyaway_softens_dark_strands_on_light_ground_and_nothing_else():
    im = hair_scene()
    out = APPLIERS["flyaway"](im, [0.5, 0.5, 0.34, 0.95])

    def strands(img):
        return sum(luma(img.getpixel((x, 300))) for x in (230, 250, 270)) / 3.0

    def far(img):
        return sum(luma(img.getpixel((x, 300))) for x in (60, 80, 100)) / 3.0

    assert strands(out) > strands(im) + 6, "the strands did not soften into the background"
    assert out.getpixel((365, 280)) == im.getpixel((365, 280)), "a wide dark area was smeared"
    assert out.getpixel((214, 214)) == im.getpixel((214, 214)), "flat background was smeared"
    for x in (60, 80, 100):
        for y in (250, 300, 350):
            assert out.getpixel((x, y)) == im.getpixel((x, y)), "outside the brush was touched"
    assert far(out) == far(im)
    assert out.getpixel((4, 4)) == im.getpixel((4, 4))
    assert ink_fraction(im, out) < 0.05


# ---------------------------------------------------------------------------- tan

def window_scene():
    """Skin, a grey wall, a blue prop, a terracotta tile, pale linen and a dark ground."""
    im = Image.new("RGB", SIZE, (28, 30, 34))
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, 260, 260], fill=(215, 180, 155))
    d.rectangle([300, 40, 560, 260], fill=(182, 182, 182))
    d.rectangle([40, 300, 260, 560], fill=(62, 92, 200))
    d.rectangle([300, 300, 560, 560], fill=(200, 125, 105))
    d.rectangle([40, 566, 560, 594], fill=(232, 214, 190))
    return im


SKIN, WALL, PROP, TILE, LINEN, GROUND = (150, 150), (430, 150), (150, 430), (430, 430), \
    (300, 580), (30, 30)


def test_tan_warms_the_skin_window_and_admits_it_catches_the_tile():
    im = window_scene()
    out = APPLIERS["tan"](im, [1.0, 30.0, 1.0, 0.4])
    was, skin = im.getpixel(SKIN), out.getpixel(SKIN)
    assert skin[0] < was[0], "a tan did not darken the skin at all"
    assert skin[0] - skin[2] > was[0] - was[2], "the skin did not get warmer"
    assert hsv_of(skin)[0] == pytest.approx(30.0, abs=10.0), "the hue slider did not steer"
    assert out.getpixel(WALL) == im.getpixel(WALL), "a grey wall was tanned"
    assert out.getpixel(PROP) == im.getpixel(PROP), "a blue prop was tanned"
    assert out.getpixel(GROUND) == im.getpixel(GROUND), "a dark ground was tanned"
    assert out.getpixel(TILE) != im.getpixel(TILE), \
        "the tool now claims it can tell a terracotta tile from skin, which it cannot"

    # the band slider is the only lever against that: a pale warm cloth sits on the edge
    tight = APPLIERS["tan"](im, [1.0, 30.0, 1.0, 0.0])
    wide = APPLIERS["tan"](im, [1.0, 30.0, 1.0, 1.0])
    assert tight.getpixel(LINEN) == im.getpixel(LINEN), "the narrow window still took the linen"
    assert wide.getpixel(LINEN) != im.getpixel(LINEN), "widening the window did nothing"
    assert ink_fraction(im, tight) < ink_fraction(im, wide), "the band slider does not narrow"
    assert APPLIERS["tan"](im, [0.0, 45.0, 1.0, 1.0]).tobytes() == im.tobytes()


# ---------------------------------------------------------------------- skin_tone

def test_skin_tone_moves_hue_and_colour_inside_the_window_and_not_outside_it():
    im = window_scene()
    warm = APPLIERS["skin_tone"](im, [1.0, 1.0, 1.0, 0.4])
    was, skin = im.getpixel(SKIN), warm.getpixel(SKIN)
    assert abs(hsv_of(skin)[0] - hsv_of(was)[0]) > 2.0, "hue did not move"
    assert hsv_of(skin)[1] > hsv_of(was)[1] + 5, "saturation did not move"
    assert hsv_of(skin)[2] == pytest.approx(hsv_of(was)[2], abs=3.0), "brightness moved"
    assert warm.getpixel(WALL) == im.getpixel(WALL), "a grey wall was retinted"
    assert warm.getpixel(PROP) == im.getpixel(PROP), "a blue prop was retinted"
    assert warm.getpixel(GROUND) == im.getpixel(GROUND), "a dark ground was retinted"
    assert warm.getpixel(TILE) != im.getpixel(TILE), "the tile claim in the note is not true"

    cool = APPLIERS["skin_tone"](im, [-1.0, -1.0, 1.0, 0.4])
    assert hsv_of(cool.getpixel(SKIN))[0] < hsv_of(skin)[0], "the hue lever is not bidirectional"
    assert hsv_of(cool.getpixel(SKIN))[1] < hsv_of(skin)[1], "the saturation lever is not either"
    assert APPLIERS["skin_tone"](im, [1.0, 1.0, 0.0, 0.4]).tobytes() == im.tobytes()


# ------------------------------------------------------------------ shared contract

@pytest.mark.parametrize("name", sorted(APPLIERS))
def test_the_contract_each_op_declares_matches_the_one_the_page_reads(name):
    k = len(CLAMP[name])
    assert SHAPE[name][1] == (["f"] * k if SHAPE[name][0] == "list" else k)
    assert LIMITS[name] >= 1
    for lo, hi in CLAMP[name]:
        assert lo < hi


@pytest.mark.parametrize("name", sorted(APPLIERS))
def test_a_short_or_junky_argument_list_is_dropped_not_run(name):
    im = patch_scene()
    assert APPLIERS[name](im, []).tobytes() == im.tobytes()
    assert APPLIERS[name](im, ["x", None, 9e9] * 4).size == SIZE
    small = [0.5, 0.5, 0.05] if name in repair.GROUPED else [0.5, 0.5, 0.5, 0.5]
    many = small + [0.5] * (len(CLAMP[name]) - len(small))
    assert APPLIERS[name](im, many * (LIMITS[name] + 4)).size == SIZE
    assert APPLIERS[name](im, [0.5] * (len(CLAMP[name]) - 1)).size == SIZE


@pytest.mark.parametrize("name", sorted(APPLIERS))
def test_rgba_goes_in_and_the_same_mode_and_the_same_alpha_come_back(name, tmp_path):
    rgba = window_scene().convert("RGBA")
    rgba.putalpha(0)
    out = APPLIERS[name](rgba, [0.5, 0.5, 0.2, 0.9, 0.5, 0.1, 0.4, 0.8][:len(CLAMP[name])])
    assert out.mode == "RGBA" and out.size == SIZE
    assert out.split()[3].tobytes() == rgba.split()[3].tobytes()
    path = tmp_path / f"{name}.png"
    out.save(path)
    with Image.open(path) as again:
        assert again.mode == "RGBA" and again.size == SIZE
        assert again.split()[3].getpixel((0, 0)) == 0
        assert again.convert("RGB").tobytes() == out.convert("RGB").tobytes()


def test_the_input_image_is_never_written_to():
    im = eye_scene()
    was = im.copy()
    for name, args in (("patch", [0.5, 0.5, 0.2, 0.85, 0.0, 0.2, 0.4, 1.0]),
                       ("conceal", [0.5, 0.5, 0.2, 0.9, 0.6]),
                       ("red_eye", [0.5, 0.5, 0.2, 0.9]),
                       ("dewy", [0.5, 0.5, 0.2, 0.9]),
                       ("flyaway", [0.5, 0.5, 0.2, 0.9]),
                       ("tan", [1.0, 30.0, 1.0, 0.5]),
                       ("skin_tone", [1.0, 1.0, 1.0, 0.5])):
        APPLIERS[name](im, args)
        assert im.tobytes() == was.tobytes(), f"{name} wrote into the caller's image"
