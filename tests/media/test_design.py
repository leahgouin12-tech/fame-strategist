import pytest
from PIL import Image, ImageChops, ImageDraw

from src.media import design
from tests.timing import median_of

SIZE = (600, 800)
PREVIEW = (900, 1200)        # the 900 px preview the budget in this file is quoted against
BASE = (150, 160, 170)
BLOCK = (230, 210, 190)
INK = (10, 10, 10)
WALL = (30, 40, 50)
DISC = (235, 205, 175)
CYAN = (20, 200, 240)


def photo():
    """Flat and light, so any pixel that moved is obvious."""
    im = Image.new("RGB", SIZE, BASE)
    ImageDraw.Draw(im).rectangle([80, 80, 300, 340], fill=BLOCK)
    return im


def subject(size=SIZE):
    """A solid shape on an even wall - the frame a flood-fill cutout can actually find."""
    wide, tall = size
    im = Image.new("RGB", size, WALL)
    ImageDraw.Draw(im).ellipse((int(0.3 * wide), int(0.32 * tall),
                                int(0.7 * wide), int(0.68 * tall)), fill=DISC)
    return im


def run(name, im, args):
    return design.APPLIERS[name](im, args)


def diff(im, out):
    return ImageChops.difference(im.convert("RGB"), out.convert("RGB")).convert("L")


def ink_box(im, out):
    return diff(im, out).getbbox()


def ink_fraction(im, out):
    hist = diff(im, out).histogram()
    return sum(hist[2:]) / (im.width * im.height)


def near(pixel, colour, slack=8):
    return sum(abs(a - b) for a, b in zip(pixel, colour)) <= slack


def silhouette(im, out, floor=24):
    """The moved pixels as a black-and-white map, for comparing one shape with another."""
    return diff(im, out).point(lambda v: 255 if v > floor else 0)


@pytest.fixture
def root(tmp_path, monkeypatch):
    plate = tmp_path / "plate.jpg"
    Image.new("RGB", (400, 300), CYAN).save(plate, quality=95)
    monkeypatch.setattr(design.layers, "ROOT", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------- the brush


def test_a_dab_lands_where_it_was_tapped_and_nowhere_else():
    im = photo()
    out = run("draw", im, [0.3, 0.4, 0.12, 0.04, 0.04, 0.04, 1.0, 0.9])
    box = ink_box(im, out)
    assert box is not None and out.mode == "RGB"
    radius = 0.5 * 0.12 * min(im.size)          # 36 px on this frame
    cx, cy = 0.3 * im.width, 0.4 * im.height
    assert abs((box[0] + box[2]) / 2 - cx) <= 3 and abs((box[1] + box[3]) / 2 - cy) <= 3
    assert box[2] - box[0] <= 2 * radius + 6 and box[3] - box[1] <= 2 * radius + 6
    assert near(out.getpixel((int(cx), int(cy))), INK, 14), "the middle of the dab is ink"
    assert out.getpixel((4, im.height - 4)) == im.getpixel((4, im.height - 4))
    assert out.getpixel((im.width - 4, 4)) == im.getpixel((im.width - 4, 4))


def test_every_tap_carried_in_one_entry_is_painted():
    im = photo()
    dabs = [(0.2, 0.2), (0.8, 0.25), (0.25, 0.75), (0.75, 0.8)]
    args = [v for x, y in dabs for v in (x, y, 0.1, 0.04, 0.04, 0.04, 1.0, 0.85)]
    out = run("draw", im, args)
    for x, y in dabs:
        assert near(out.getpixel((int(x * im.width), int(y * im.height))), INK, 14), (x, y)
    assert 0.01 < ink_fraction(im, out) < 0.25
    # a tail that is not a whole group is dropped, not slid into the previous one
    assert len(design._shape("draw", args[:-3])) == 8 * (len(dabs) - 1)


def test_hardness_and_opacity_both_show_up_in_the_mark():
    im = photo()
    soft = run("draw", im, [0.5, 0.5, 0.2, 0.04, 0.04, 0.04, 1.0, 0.0])
    hard = run("draw", im, [0.5, 0.5, 0.2, 0.04, 0.04, 0.04, 1.0, 0.95])
    pale = run("draw", im, [0.5, 0.5, 0.2, 0.04, 0.04, 0.04, 0.15, 0.95])
    rim = (300, 345)             # 55 px from the centre of a dab with a 60 px radius
    assert sum(soft.getpixel(rim)) > sum(hard.getpixel(rim)), \
        "a soft brush is already fading where a hard one is still solid"
    assert sum(pale.getpixel((300, 400))) > sum(hard.getpixel((300, 400)))
    assert hard.getpixel((300, 400)) == INK
    assert ink_box(im, run("draw", im, [0.5, 0.5, 0.2, 1, 1, 1, 0.0, 0.5])) is None, \
        "zero opacity lays nothing"


# --------------------------------------------------------------------------- the stickers


@pytest.mark.parametrize("kind", range(8))
def test_each_sticker_kind_draws_where_it_was_placed(kind):
    im = subject()
    out = run("sticker", im, [0.5, 0.5, 0.3, kind, 0.04, 0.04, 0.04, 0, 0])
    box = ink_box(im, out)
    edge = 0.3 * min(im.size)                        # 180 px, centred on the tap
    assert box is not None, design.KINDS[kind]
    assert box[0] >= 300 - edge / 2 - 3 and box[2] <= 300 + edge / 2 + 3, design.KINDS[kind]
    assert box[1] >= 400 - edge / 2 - 3 and box[3] <= 400 + edge / 2 + 3, design.KINDS[kind]
    assert box[2] - box[0] > 0.5 * edge, f"{design.KINDS[kind]} barely drew anything"
    assert out.getpixel((6, 6)) == im.getpixel((6, 6)), "and not one pixel outside it"


def test_the_eight_sticker_kinds_are_eight_different_shapes():
    im = subject()
    marks = {}
    for kind in range(8):
        out = run("sticker", im, [0.5, 0.5, 0.34, kind, 0.04, 0.04, 0.04, 0, 0])
        marks[design.KINDS[kind]] = silhouette(im, out)
    assert len(marks) == 8
    names = list(marks)
    for i, first in enumerate(names):
        assert marks[first].histogram()[255] > 2000, f"{first} drew nothing"
        for second in names[i + 1:]:
            a, b = marks[first], marks[second]
            both = ImageChops.lighter(a, b).histogram()[255]
            apart = ImageChops.difference(a, b).histogram()[255]
            assert apart / both > 0.15, f"{first} and {second} are the same drawing"


def test_the_ring_is_hollow_and_the_others_are_not():
    im = subject()
    ring = run("sticker", im, [0.5, 0.5, 0.32, 2, 0.04, 0.04, 0.04, 0, 0])
    filled = run("sticker", im, [0.5, 0.5, 0.32, 7, 0.04, 0.04, 0.04, 0, 0])
    centre = (300, 400)
    assert ring.getpixel(centre) == im.getpixel(centre), "a ring has nothing in the middle"
    assert near(filled.getpixel(centre), INK, 20), "the spark fills through its centre"


def test_turning_a_sticker_and_thickening_its_edge_are_both_real_arguments():
    im = subject()
    straight = run("sticker", im, [0.5, 0.5, 0.3, 0, 0.04, 0.04, 0.04, 0, 0])
    turned = run("sticker", im, [0.5, 0.5, 0.3, 0, 0.04, 0.04, 0.04, 90, 0])
    thin = run("sticker", im, [0.5, 0.5, 0.3, 5, 0.04, 0.04, 0.04, 0, 0])
    fat = run("sticker", im, [0.5, 0.5, 0.3, 5, 0.04, 0.04, 0.04, 0, 0.18])
    tip = (300, 322)                                 # the arrow's point, straight up
    assert near(straight.getpixel(tip), INK, 20), "the arrow points up as drawn"
    assert not near(turned.getpixel(tip), INK, 20), "and points left once turned"
    assert ink_fraction(im, fat) > ink_fraction(im, thin), "the edge is drawn, not offered"
    assert near(fat.getpixel((300, 420)), INK, 20), "the middle stays the fill colour"


# ----------------------------------------------------------------------- words on an arc


def test_the_letters_ride_the_arc_and_the_middle_stays_clean():
    im = photo()
    out = run("curved_text", im, [0.5, 0.62, 0.05, 1, 1, 1, 0, 0, 1, "display",
                                  "SPRING DROP", 0.3, 150])
    box = ink_box(im, out)
    reach = 0.3 * min(im.size)
    cx, cy = 0.5 * im.width, 0.62 * im.height
    assert box is not None
    assert box[3] < cy, "a positive sweep hangs the words over the top of the circle"
    assert abs((box[0] + box[2]) / 2 - cx) < 0.1 * im.width
    assert abs(box[1] - (cy - reach)) < 0.12 * im.height, "the ink sits on the arc, not in it"
    assert out.getpixel((int(cx), int(cy))) == im.getpixel((int(cx), int(cy)))
    assert 0.0005 < ink_fraction(im, out) < 0.2


def test_a_negative_sweep_and_a_different_radius_move_the_whole_line():
    im = photo()
    over = run("curved_text", im, [0.5, 0.5, 0.04, 1, 1, 1, 0, 0, 1, "body",
                                   "READ ME", 0.28, 120])
    under = run("curved_text", im, [0.5, 0.5, 0.04, 1, 1, 1, 0, 0, 1, "body",
                                    "READ ME", 0.28, -120])
    wide = run("curved_text", im, [0.5, 0.5, 0.04, 1, 1, 1, 0, 0, 1, "body",
                                   "READ ME", 0.14, 120])
    assert ink_box(over, under) is not None
    assert ink_box(over, wide) is not None
    assert ink_box(im, under)[1] > 0.5 * im.height, "the valley arc writes below the centre"
    assert ink_box(im, wide)[1] > ink_box(im, over)[1], "a tighter circle sits closer in"


def test_curved_text_wraps_and_outlines_without_leaving_the_frame():
    im = photo()
    out = run("curved_text", im, [0.5, 0.55, 0.05, 1, 0, 0, 0.06, 0.4, 1, "serif",
                                  "the whole collection lands this friday at noon",
                                  0.34, 300])
    box = ink_box(im, out)
    assert out.size == SIZE and out.mode == "RGB"
    assert box[0] >= 0 and box[1] >= 0 and box[2] <= im.width and box[3] <= im.height
    assert ink_fraction(im, out) > 0.002


# ------------------------------------------------------------------------- the cut shapes


@pytest.mark.parametrize("kind", range(5))
def test_shape_crop_clears_the_corners_and_keeps_the_middle(kind):
    im = photo()
    out = run("shape_crop", im, [kind, 0.0, 0.05, 0, 0, 0, 0])
    assert out.mode == "RGBA" and out.size == SIZE
    assert out.getpixel((0, 0))[3] == 0, design.CUTS[kind]
    assert out.getpixel((im.width - 1, 0))[3] == 0, design.CUTS[kind]
    feet = design.CUTS[kind] == "arch"          # a door stands on its two bottom corners
    assert (out.getpixel((0, im.height - 1))[3] == 255) is feet, design.CUTS[kind]
    assert (out.getpixel((im.width - 1, im.height - 1))[3] == 255) is feet, design.CUTS[kind]
    assert out.getpixel((im.width // 2, im.height // 2))[3] == 255, design.CUTS[kind]
    assert out.getpixel((im.width // 2, im.height // 2))[:3] == im.getpixel(
        (im.width // 2, im.height // 2))
    assert diff(im, out).getbbox() is None, "the colours are untouched, only the opacity"


def test_an_inset_pulls_the_keep_out_line_in_from_the_edge():
    im = photo()
    flat = run("shape_crop", im, [0, 0.0, 0.0, 0, 0, 0, 0])
    inset = run("shape_crop", im, [0, 0.1, 0.0, 0, 0, 0, 0])
    edge = int(round(0.1 * min(im.size)))
    assert flat.getpixel((2, im.height // 2))[3] == 255
    assert inset.getpixel((2, im.height // 2))[3] == 0
    assert inset.getpixel((edge + 6, im.height // 2))[3] == 255
    assert inset.getpixel((im.width // 2, im.height // 2))[3] == 255


@pytest.mark.parametrize("mode,colour", [(1, (255, 255, 255)), (2, (255, 0, 0))])
def test_a_filled_mode_lays_a_plate_behind_it_instead_of_a_hole(mode, colour):
    im = photo()
    out = run("shape_crop", im, [0, 0.0, 0.0, mode, *(c / 255 for c in colour)])
    assert out.mode == "RGB"
    assert out.getpixel((1, 1)) == colour, "the corner is the plate, not the picture"
    assert out.getpixel((im.width // 2, im.height // 2)) == im.getpixel(
        (im.width // 2, im.height // 2))


def test_cropping_a_frame_that_is_already_cut_multiplies_the_two_masks():
    cut = run("shape_crop", photo(), [2, 0.0, 0.15, 0, 0, 0, 0])
    again = run("shape_crop", cut, [0, 0.0, 0.0, 0, 0, 0, 0])
    assert again.mode == "RGBA"
    assert again.getpixel((0, 0))[3] == 0
    assert again.getpixel((cut.width // 2, cut.height // 2))[3] == 255


# ----------------------------------------------------------------- the backdrop and the rim


def test_the_backdrop_shows_round_the_subject_and_not_through_it(root):
    im = subject()
    out = run("bg_replace", im, ["", 0.94, 0.94, 0.98, 0.2, 0.0, 0])
    plate = (240, 240, 250)
    assert out.mode == "RGB" and out.size == SIZE
    assert near(out.getpixel((4, 4)), plate, 16), "the wall is gone"
    assert near(out.getpixel((4, im.height - 5)), plate, 16)
    assert near(out.getpixel((300, 400)), DISC, 26), "the subject is still itself"
    assert out.getpixel((300, 400)) == im.getpixel((300, 400)), \
        "the middle of the subject is not repainted at all"


def test_a_file_from_the_inbox_can_be_the_backdrop_instead_of_a_colour(root):
    im = subject()
    flat = run("bg_replace", im, ["", 0.0, 0.0, 0.0, 0.2, 0.0, 0])
    with_a_file = run("bg_replace", im, ["plate.jpg", 0.0, 0.0, 0.0, 0.2, 0.0, 0])
    assert near(flat.getpixel((4, 4)), (0, 0, 0), 20)
    assert near(with_a_file.getpixel((4, 4)), CYAN, 20)
    assert near(with_a_file.getpixel((300, 400)), DISC, 26)
    # a frame that has already been cut out keeps the mask it arrived with
    cut = im.convert("RGBA")
    cut.putalpha(run("shape_crop", cut, [0, 0.0, 0.0, 0, 0, 0, 0]).getchannel("A"))
    dropped = run("bg_replace", cut, ["plate.jpg", 1, 1, 1, 0.0, 0.0, 0])
    assert near(dropped.getpixel((4, 4)), CYAN, 20)


def test_feather_and_expand_change_the_matte_and_which_side_of_it_wins():
    im = subject()
    hard = run("bg_replace", im, ["", 1, 1, 1, 0.0, 0.0, 0])
    grown = run("bg_replace", im, ["", 1, 1, 1, 0.0, 1.0, 0])
    soft = run("bg_replace", im, ["", 1, 1, 1, 1.0, 0.0, 0])
    probe = (300, 258)                       # 2 px above the disc's top edge
    assert hard.getpixel(probe)[:3] != DISC or near(hard.getpixel(probe), (255, 255, 255), 40)
    assert not near(grown.getpixel((300, 240)), (255, 255, 255), 40), \
        "an expanded matte swallows the ring of wall around the subject"
    assert ink_box(hard, soft) is not None, "feathering is not decoration"


def test_the_glow_sits_round_the_subject_without_passing_through_it():
    im = subject()
    glow = (255, 90, 40)
    out = run("glow_edge", im, [*(c / 255 for c in glow), 0.06, 0.9])
    assert out.mode == "RGB" and out.size == SIZE
    assert out.getpixel((300, 400)) == im.getpixel((300, 400)), "the subject is not lit"
    assert out.getpixel((4, 4)) == im.getpixel((4, 4)), "the far corner is not lit either"
    rim = (300, 250)                         # just outside the disc, on the wall
    assert sum(out.getpixel(rim)) > sum(im.getpixel(rim)), "the rim picks up the colour"
    assert out.getpixel(rim)[:2] > im.getpixel(rim)[:2], "and it is the colour asked for"
    box = ink_box(im, out)
    assert box is not None
    assert box[0] > 0 and box[2] < im.width, "the glow is a band, not a wash"


def test_a_glow_with_no_subject_to_hug_still_lights_the_rim_of_the_frame():
    """An evenly lit photo gives the flood-fill cutout nothing to find. A rim glow with no
    rim to sit on used to hand back the frame untouched, which reads as a broken button, so
    it falls back to the edge of the picture and paints there instead."""
    im = Image.new("RGB", SIZE, (150, 151, 150))
    out = run("glow_edge", im, [1, 0.72, 0.48, 0.12, 1.0])
    assert out.size == SIZE and out.mode == "RGB"
    assert ink_box(im, out) is not None, "the glow painted nothing"
    assert sum(out.getpixel((110, 110))) > sum(im.getpixel((110, 110))), "just inside the rim"
    assert out.getpixel((300, 400)) == im.getpixel((300, 400)), "and it stays off the middle"


def test_a_wider_glow_reaches_further_than_a_narrow_one():
    im = subject()
    tight = run("glow_edge", im, [1, 0.2, 0.1, 0.01, 1.0])
    broad = run("glow_edge", im, [1, 0.2, 0.1, 0.12, 1.0])
    probe = (300, 200)                       # 60 px clear of the disc
    assert tight.getpixel(probe) == im.getpixel(probe)
    assert broad.getpixel(probe) != im.getpixel(probe)
    assert ink_fraction(im, broad) > ink_fraction(im, tight)
    cut = run("shape_crop", im, [0, 0.0, 0.0, 0, 0, 0, 0])
    lit = run("glow_edge", cut, [1, 0.2, 0.1, 0.06, 0.8])
    assert lit.mode == "RGBA"
    assert lit.getchannel("A").getpixel(probe) > 0, "the halo carries opacity of its own"


# ------------------------------------------------------------------- the frame that grows


@pytest.mark.parametrize("kind,edges", [
    (0, (120, 120, 120, 120)),     # all four: 0.2 of the short edge on every side
    (1, (0, 120, 0, 0)),           # up
    (2, (0, 0, 0, 120)),           # down
    (3, (120, 0, 0, 0)),           # left
    (4, (0, 0, 120, 0)),           # right
])
def test_the_frame_grows_by_the_amount_asked_for_on_the_side_asked_for(kind, edges):
    im = photo()
    out = run("edge_expand", im, [kind, 0.2, 0.4, 0.3])
    left, top, right, bottom = edges
    assert out.size == (im.width + left + right, im.height + top + bottom)
    grown = out.crop((left, top, left + im.width, top + im.height))
    assert grown.convert("RGB").tobytes() == im.tobytes(), "the original region is untouched"
    assert diff(im, grown).getbbox() is None
    strips = [out.crop(b) for b in ((0, top, left, top + im.height),
                                    (left, 0, left + im.width, top),
                                    (left + im.width, top, out.width, top + im.height),
                                    (left, top + im.height, left + im.width, out.height))
              if b[2] > b[0] and b[3] > b[1]]
    assert len(strips) == (4 if kind == 0 else 1)
    assert max(strips[0].convert("L").getextrema()) > 40, "the band carries picture, not black"


def test_the_new_edge_is_the_neighbouring_background_not_a_empty_colour():
    im = subject()
    out = run("edge_expand", im, [4, 0.3, 0.5, 0.0])
    seam = im.width - 2
    for y in (60, im.height // 2, im.height - 60):
        assert near(out.getpixel((im.width + 4, y)), im.getpixel((seam, y)), 40), \
            "the strip beside the seam is the shade that was already at the edge"
    far = out.getpixel((out.width - 3, im.height // 2 + 0))
    assert near(far, im.getpixel((seam, im.height // 2)), 60), "and it stays that shade"


def test_blur_and_fade_only_act_outside_the_original_picture():
    im = subject()
    args = [4, 0.35, 0.0, 0.0]
    plain = run("edge_expand", im, args)
    blurred = run("edge_expand", im, [4, 0.35, 1.0, 0.0])
    faded = run("edge_expand", im, [4, 0.35, 0.6, 1.0])
    inside = (im.width - 30, 300)
    assert plain.getpixel(inside) == blurred.getpixel(inside) == faded.getpixel(inside)
    outside = (im.width + 120, 300)
    assert plain.getpixel(outside) != blurred.getpixel(outside), "the blur runs"
    near_edge, far_edge = im.width + 4, im.width + 200
    assert sum(faded.getpixel((far_edge, 300))) < sum(faded.getpixel((near_edge, 300))), \
        "and the fade darkens toward the outside"


def test_an_edge_expand_of_zero_is_the_picture_unchanged():
    im = photo()
    assert run("edge_expand", im, [0, 0.0, 0.5, 0.5]).tobytes() == im.tobytes()


# --------------------------------------------------------------------- the tables, shared


def test_the_tables_cover_every_name_the_registry_will_ask_about():
    assert set(design.SHAPE) == set(design.CLAMP) == set(design.LIMITS) == set(design.APPLIERS)
    for name, spec in design.SHAPE.items():
        slots = design.CLAMP[name]
        assert spec[0] in ("list", "group"), name
        if spec[0] == "group":
            assert spec[1] == len(slots) and spec[2] == design.LIMITS[name] >= 1
        else:
            assert len(spec[1]) == len(slots)
            assert all(kind in ("f", "s") for kind in spec[1])
            assert [(slot is None) for slot in slots] == [kind == "s" for kind in spec[1]]
        for slot in slots:
            assert slot is None or (isinstance(slot, tuple) and slot[0] <= slot[1])
    assert design.KINDS == ("arrow", "star", "ring", "bubble", "badge", "heart", "spark",
                            "cross")
    assert design.CUTS == ("circle", "hex", "rounded", "arch", "star")


@pytest.mark.parametrize("name,args", [
    ("draw", []), ("draw", [0.5]), ("draw", ["x", None, 3]),
    ("draw", [0.5, 0.5, 0.1, 1, 1, 1, 1, 1, 0.5]),
    ("sticker", []), ("sticker", [0.5, 0.5, 0.2]),
    ("sticker", [-4, 9, 0, 99, "a", "b", 3, 900, 5]),
    ("curved_text", []), ("curved_text", [0.5, 0.5, 0.05]),
    ("curved_text", [0.5, 0.5, 9, 4, -2, 1, 9, 9, 7, "chalk", "", 0, 0]),
    ("shape_crop", []), ("shape_crop", [9, 5, 5, 5, 3, -1, 2]),
    ("bg_replace", []), ("bg_replace", [None]),
    ("bg_replace", ["../x", "a", "b", "c", 4, -1, 9]),
    ("glow_edge", []), ("glow_edge", [1]), ("glow_edge", [-1, 4, 0, 9, 9]),
    ("edge_expand", []), ("edge_expand", [2]), ("edge_expand", [9, 4, -2, 7]),
])
def test_a_half_written_or_nonsense_entry_is_a_no_op_not_a_crash(name, args):
    im = photo()
    out = run(name, im, args)
    assert out.mode in ("RGB", "RGBA")
    assert max(out.size) <= design.MAX_EDGE


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "P"])
def test_every_op_takes_whatever_the_pipeline_handed_it(mode):
    im = photo().convert(mode)
    every = {
        "draw": [0.5, 0.5, 0.12, 1, 0, 0, 1, 0.6],
        "sticker": [0.5, 0.5, 0.24, 3, 0, 1, 0, 20, 0.05],
        "curved_text": [0.5, 0.5, 0.05, 1, 1, 1, 0, 0.2, 1, "body", "hi", 0.3, 140],
        "shape_crop": [1, 0.02, 0.05, 0, 0, 0, 0],
        "bg_replace": ["", 0.9, 0.1, 0.1, 0.3, 0.2, 1],
        "glow_edge": [0.2, 1, 0.4, 0.05, 0.7],
        "edge_expand": [0, 0.15, 0.5, 0.4],
    }
    for name, args in every.items():
        out = run(name, im, args)
        assert out.mode in ("RGB", "RGBA"), name
        assert out.size[0] > 0 and out.size[1] > 0, name


def test_no_operation_touches_the_picture_it_was_given():
    im = subject()
    before = im.tobytes()
    every = {
        "draw": [0.4, 0.4, 0.2, 1, 1, 0, 1, 0.5],
        "sticker": [0.5, 0.4, 0.3, 6, 0, 0, 1, 0, 0.06],
        "curved_text": [0.5, 0.6, 0.05, 1, 0, 0, 0.04, 0.3, 1, "display", "SALE", 0.3, 160],
        "shape_crop": [3, 0.05, 0.0, 1, 1, 1, 1],
        "bg_replace": ["", 0.1, 0.9, 0.4, 0.2, 0.1, 0],
        "glow_edge": [1, 0, 0.5, 0.08, 0.8],
        "edge_expand": [2, 0.2, 0.4, 0.2],
    }
    for name, args in every.items():
        out = run(name, im, args)
        assert im.tobytes() == before, f"{name} mutated its input"
        assert out is not im, name


def test_no_operation_falls_back_to_walking_pixels():
    """The budget is the one the module promises: the heaviest call a slider can ask for
    on a 900 px preview in about a second and a half. The machine's own whole-frame pass
    sets the exchange rate, so a loaded laptop is not failed for being loaded - and every
    op here is vectorised Pillow, where a Python loop over this frame would cost a
    hundred of those passes and blow the budget on its own.

    The exchange rate is taken again in front of each op, not once at the top of the test.
    `edge_expand` was measured at 1.91 s against a 1.79 s budget in a full suite and inside
    it when this file ran alone: the op is genuinely about eleven passes, so what varied was
    how loaded the laptop was between the two readings, and a budget priced in a quiet instant
    tests the machine's schedule rather than this module."""
    im = subject(PREVIEW)
    every = {
        "draw": [0.5, 0.5, 0.6, 1, 1, 1, 1, 0.5] * 60,        # a whole drag, biggest brush
        "sticker": [0.5, 0.5, 1.0, 0, 1, 0, 0, 37, 0.1],       # a turned frame-wide arrow
        "curved_text": [0.5, 0.5, 0.2, 1, 1, 1, 0.05, 0.4, 1, "display",
                        "A REAL SENTENCE FOR THE POSTER", 0.5, 200],
        "shape_crop": [4, 0.2, 0.2, 2, 0.5, 0.5, 0.5],         # the star over a plate
        "bg_replace": ["", 0.2, 0.6, 0.9, 1.0, 1.0, 0],        # widest feather and expand
        "glow_edge": [0.4, 0.2, 1, 0.5, 1.0],                  # the halo at full reach
        "edge_expand": [0, 0.5, 1.0, 0.5],                     # four sides, blurred, faded
    }
    for name, args in every.items():
        pass_cost, _ = median_of(lambda: ImageChops.add(im, im))
        budget = max(1.5, 75 * pass_cost)
        took, _ = median_of(lambda: run(name, im, args), runs=2)
        assert took < budget, f"{name} cost {took:.2f} s against a {budget:.2f} s budget"
