import pytest
from PIL import Image, ImageChops, ImageDraw

from src.media import layers
from tests.timing import median_of

SIZE = (600, 800)
BASE = (150, 160, 170)
CYAN = (20, 200, 240)
PINK = (240, 30, 90)


def photo():
    im = Image.new("RGB", SIZE, BASE)
    d = ImageDraw.Draw(im)
    d.rectangle([80, 80, 300, 340], fill=(230, 210, 190))
    return im


def run(name, im, args):
    return layers.APPLIERS[name](im, args)


def diff(im, out):
    return ImageChops.difference(im.convert("RGB"), out.convert("RGB")).convert("L")


def ink_box(im, out):
    return diff(im, out).getbbox()


def ink_fraction(im, out):
    hist = diff(im, out).histogram()
    return sum(hist[2:]) / (im.width * im.height)


def near(pixel, colour, slack=8):
    return sum(abs(a - b) for a, b in zip(pixel, colour)) <= slack


@pytest.fixture
def root(tmp_path, monkeypatch):
    plain = tmp_path / "plain.jpg"
    Image.new("RGB", (120, 90), CYAN).save(plain, quality=95)
    alpha = tmp_path / "alpha.png"
    tile = Image.new("RGBA", (100, 100), PINK + (255,))
    ImageDraw.Draw(tile).rectangle([0, 0, 49, 49], fill=(0, 0, 0, 0))
    tile.save(alpha)
    monkeypatch.setattr(layers, "ROOT", tmp_path)
    return tmp_path


def test_text_lays_ink_on_the_block_and_nowhere_else():
    im = photo()
    out = run("text", im, [0.5, 0.25, 0.06, 1, 1, 1, 0, 0, 1, "display", "NEW DROP"])
    box = ink_box(im, out)
    assert box is not None
    assert out.mode == "RGB"
    assert abs((box[0] + box[2]) / 2 - 0.5 * im.width) < 30
    assert box[1] > 0.12 * im.height and box[3] < 0.42 * im.height
    assert 0.0005 < ink_fraction(im, out) < 0.25
    assert out.getpixel((4, im.height - 4)) == im.getpixel((4, im.height - 4))


@pytest.mark.parametrize("stroke,shadow,align", [
    (0, 0, 0), (0, 0, 1), (0, 0, 2), (0.08, 0.5, 1), (0.08, 0.0, 0), (0.0, 0.4, 2),
])
def test_stroke_shadow_and_align_all_take_neutral_and_loud_values(stroke, shadow, align):
    im = photo()
    out = run("text", im, [0.5, 0.5, 0.07, 1, 1, 1, stroke, shadow, align, "body",
                           "spring 24\nin store now"])
    assert out.size == SIZE
    assert ink_fraction(im, out) > 0.0005, (stroke, shadow, align)


def test_align_moves_the_short_line_under_a_long_one():
    words = "THE FULL COLLECTION LANDS FRIDAY\nmembers first"

    def short_line(align):
        out = run("text", photo(), [0.5, 0.5, 0.05, 1, 1, 1, 0, 0, align, "body", words])
        band = diff(photo(), out)
        box = band.getbbox()
        strip = band.crop((0, (box[1] + box[3]) // 2, SIZE[0], SIZE[1]))
        return strip.getbbox()

    left, right = short_line(0), short_line(2)
    assert left is not None and right is not None
    assert left[0] < right[0] and left[2] < right[2], "the short line slides under the long one"


def test_a_runaway_string_is_cut_down_rather_than_crashing():
    words = "x" * 5000
    flat = layers._shape("text", [0.5, 0.5, 0.05, 1, 1, 1, 0, 0, 1, "body", words])
    assert len(flat[10]) == layers.MAX_CHARS
    out = run("text", photo(), [0.5, 0.5, 0.05, 1, 1, 1, 0, 0, 1, "body", words])
    assert out.size == SIZE
    assert ink_box(photo(), out) is not None


def test_a_long_caption_wraps_instead_of_running_off_the_frame():
    im = photo()
    out = run("text", im, [0.5, 0.5, 0.05, 1, 1, 1, 0, 0, 1, "body", "the drop " * 60])
    box = ink_box(im, out)
    assert box[0] >= 0 and box[2] <= im.width and box[3] <= im.height


def test_an_unknown_font_role_falls_back_instead_of_raising():
    assert layers._font("chalk", 28) is not None
    assert layers._font("", 28) is not None
    out = run("text", photo(), [0.5, 0.5, 0.08, 1, 1, 1, 0, 0, 1, "chalk", "hello there"])
    assert ink_fraction(photo(), out) > 0.0005


def test_the_block_sits_in_the_same_place_at_preview_and_export_size():
    args = [0.5, 0.3, 0.08, 1, 1, 1, 0, 0, 1, "display", "SHOP NOW"]
    small = ink_box(photo(), run("text", photo(), args))
    big_im = Image.new("RGB", (3000, 4000), BASE)
    big = ink_box(big_im, run("text", big_im, args))
    for got, edge in ((small, SIZE), (big, (3000, 4000))):
        assert abs((got[0] + got[2]) / 2 / edge[0] - 0.5) < 0.03
        assert abs(got[1] / edge[1] - 0.27) < 0.05
    assert abs(small[3] / SIZE[1] - big[3] / 4000) < 0.03


def test_an_overlay_at_zero_opacity_leaves_the_picture_alone(root):
    im = photo()
    out = run("overlay", im, ["plain.jpg", 0.5, 0.5, 0.3, 0, 0, 0, 0])
    assert out.tobytes() == im.tobytes()


def test_an_overlay_at_full_opacity_lays_the_file_over_it(root):
    im = photo()
    out = run("overlay", im, ["plain.jpg", 0.5, 0.5, 0.3, 0, 1, 0, 0])
    assert near(out.getpixel((300, 400)), CYAN)
    assert ink_fraction(im, out) > 0.05


def test_a_half_opaque_layer_sits_between_the_two(root):
    im = photo()
    hard = run("overlay", im, ["plain.jpg", 0.5, 0.5, 0.3, 0, 1, 0, 0])
    soft = run("overlay", im, ["plain.jpg", 0.5, 0.5, 0.3, 0, 0.4, 0, 0])
    assert diff(im, soft).getbbox() is not None
    assert sum(soft.getpixel((300, 400))) > sum(hard.getpixel((300, 400)))


def test_an_rgba_layer_keeps_its_own_transparency(root):
    im = photo()
    out = run("overlay", im, ["alpha.png", 0.5, 0.5, 0.3, 0, 1, 0, 2])
    assert out.getpixel((240, 320)) == im.getpixel((240, 320)), "the transparent quarter"
    assert near(out.getpixel((360, 460)), PINK), "and the painted part"


def test_a_rotated_layer_reaches_where_the_straight_one_cannot(root):
    im = photo()
    straight = run("overlay", im, ["plain.jpg", 0.5, 0.5, 0.4, 0, 1, 0, 0])
    turned = run("overlay", im, ["plain.jpg", 0.5, 0.5, 0.4, 40, 1, 0, 0])
    assert diff(straight, turned).getbbox() is not None
    # the layer is a 240 px square on this 600 px frame: 150 px right of centre is past
    # its straight edge but well inside the same square turned through 40 degrees
    probe = (450, 400)
    assert straight.getpixel(probe) == im.getpixel(probe)
    assert turned.getpixel(probe) != im.getpixel(probe)


@pytest.mark.parametrize("mode", list(range(8)))
def test_each_fit_and_angle_still_produces_a_picture(root, mode):
    im = photo()
    out = run("overlay", im, ["alpha.png", 0.4, 0.6, 0.35, 15 * mode, 0.8, mode, mode % 3])
    assert out.size == SIZE
    assert out.mode == "RGB"


def test_every_blend_index_renders_the_same_inputs_differently(root):
    im = photo()
    seen = {}
    for mode in range(8):
        out = run("overlay", im, ["plain.jpg", 0.5, 0.5, 0.35, 0, 1, mode, 0])
        seen[mode] = out.getpixel((300, 400))
        assert seen[mode] != im.getpixel((300, 400)), f"blend {mode} did nothing"
    assert len(set(seen.values())) == 8, seen


def test_a_layer_over_a_cut_corner_lays_colour_but_not_opacity(root):
    frame = run("frame", photo(), [0, 0, 0, 0.0, 0.0, 0.12])
    out = run("overlay", frame, ["plain.jpg", 0.0, 0.0, 1.2, 0, 1, 1, 2])
    assert out.mode == "RGBA"
    assert out.getpixel((0, 0))[3] == 0, "the corner she already cut stays cut"
    assert out.getpixel((0, 0))[:3] != frame.getpixel((0, 0))[:3], "but the multiply still ran"


def test_a_layer_file_outside_the_root_is_refused(root, tmp_path):
    secret = tmp_path.parent / "secret.jpg"
    Image.new("RGB", (40, 40), (9, 9, 9)).save(secret)
    assert secret.is_file() and Image.open(secret).size == (40, 40), "the file is readable"
    im = photo()
    for name in (f"../{secret.name}", secret.name, f"{secret.name}/../../x.jpg",
                 "a/plain.jpg", ".\\plain.jpg", "sub/../plain.jpg", "C:/Windows/Fonts/arial.ttf"):
        out = run("overlay", im, [name, 0.5, 0.5, 0.5, 0, 1, 0, 0])
        assert out.tobytes() == im.tobytes(), name
        assert layers._asset(name) is None, name
    secret.unlink()


@pytest.mark.parametrize("bad", ["../secret.jpg", "a/b.jpg", "..\\plain.jpg", "",
                                 "plain.jpgx", "/plain.jpg", "plain.jpg/../plain.jpg",
                                 "C:/Windows/Fonts/arial.ttf", ".", None, 3.0])
def test_a_name_that_is_not_a_bare_file_in_the_root_loads_nothing(root, bad):
    assert layers._asset(bad) is None
    im = photo()
    assert run("overlay", im, [bad, 0.5, 0.5, 0.5, 0, 1, 0, 0]).tobytes() == im.tobytes()


def test_the_loader_never_runs_without_the_root_it_was_given(monkeypatch):
    """The app hands layers its inbox folder when it starts, so "no root" has to be the
    state under test rather than a state the process happens to be in."""
    monkeypatch.setattr(layers, "ROOT", None)
    assert layers._asset("plain.jpg") is None


def test_the_mat_grows_the_canvas_by_exactly_the_padding():
    im = photo()
    out = run("frame", im, [1, 1, 1, 0.1, 0.0, 0.0])
    assert out.size == (SIZE[0] + 120, SIZE[1] + 120)
    assert out.mode == "RGB", "square corners must not add an alpha band"
    assert out.getpixel((6, 6)) == (255, 255, 255)
    assert out.getpixel((61, 360)) == im.getpixel((1, 300))


def test_a_border_lands_on_the_picture_when_there_is_no_mat():
    im = photo()
    out = run("frame", im, [1, 0, 0, 0.0, 0.02, 0.0])
    assert out.size == SIZE
    assert out.mode == "RGB"
    assert out.getpixel((2, 400)) == (255, 0, 0)
    assert out.getpixel((40, 400)) == im.getpixel((40, 400))


def test_rounded_corners_cut_alpha_out_of_the_four_extremes():
    im = photo()
    out = run("frame", im, [0, 0, 0, 0.05, 0.0, 0.08])
    assert out.mode == "RGBA"
    assert out.size == (SIZE[0] + 60, SIZE[1] + 60)
    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((out.width - 1, 0))[3] == 0
    assert out.getpixel((out.width - 1, out.height - 1))[3] == 0
    assert out.getpixel((out.width // 2, out.height // 2))[3] == 255


def test_a_frame_never_grows_past_the_documented_edge():
    im = Image.new("RGB", (5800, 5800), BASE)
    out = run("frame", im, [1, 1, 1, 0.4, 0.2, 0.0])
    assert max(out.size) <= layers.MAX_EDGE


def test_a_mat_built_over_a_rounded_frame_keeps_the_corner_cut():
    cut = run("frame", photo(), [0, 0, 0, 0.0, 0.0, 0.1])
    assert cut.mode == "RGBA" and cut.getpixel((0, 0))[3] == 0
    matted = run("frame", cut, [1, 1, 1, 0.06, 0.0, 0.0])
    assert matted.mode == "RGBA", "the cut is not quietly filled in by the second mat"
    edge = int(round(0.06 * min(photo().size)))
    assert matted.getpixel((edge + 1, edge + 1))[3] == 0, "the print keeps its own rounded corner"
    assert matted.getpixel((0, 0))[3] == 255, "and the mat around it is solid"


def test_two_files_make_an_even_grid_and_the_gap_shows_the_background(root):
    im = photo()
    out = run("collage", im, ["plain.jpg", "alpha.png", 2, 0.05, 0.5, 0])
    assert out.mode == "RGB"
    assert out.size == (2 * 600 + 3 * 30, 2 * 600 + 3 * 30)
    assert out.getpixel((15, 15)) == (128, 128, 128), "the gap is the background"
    assert out.getpixel((400, 400)) == BASE, "the first cell is the picture she opened"
    assert near(out.getpixel((700, 400)), CYAN), "the second cell is plain.jpg"
    assert out.getpixel((700, 700)) == (128, 128, 128), "the empty cell stays background"


def test_a_missing_file_is_left_out_of_the_grid(root):
    im = photo()
    out = run("collage", im, ["plain.jpg", "nope.jpg", 1, 0.05, 0.5, 1])
    assert out.size == (600 + 2 * 30, 2 * 600 + 3 * 30)
    assert run("collage", im, ["gone.jpg", "also-gone.jpg", 2, 0.05, 0.5, 0]) is im


def test_a_wide_gap_cannot_push_the_sheet_past_the_documented_edge(root):
    im = Image.new("RGB", (5000, 5000), BASE)
    out = run("collage", im, ["plain.jpg", "alpha.png", 6, 0.25, 0.5, 0])
    assert max(out.size) <= layers.MAX_EDGE


def test_the_signature_tiles_across_the_frame_and_stays_inside_it():
    im = photo()
    out = run("watermark", im, ["PROOF", 0.5, 0.5, 0.04, 0.5, 0.0])
    box = ink_box(im, out)
    assert out.size == SIZE and out.mode == "RGB"
    assert box is not None and box[0] >= 0 and box[2] <= im.width
    assert box[1] >= 0 and box[3] <= im.height
    assert 0.002 < ink_fraction(im, out) < 0.4


def test_the_tilt_leans_the_tiling_and_every_mark_stays_inside():
    im = photo()
    flat = run("watermark", im, ["PREVIEW", 0.5, 0.5, 0.03, 0.6, 0])
    tilted = run("watermark", im, ["PREVIEW", 0.5, 0.5, 0.03, 0.6, -30])
    assert flat.size == im.size and tilted.size == im.size
    for out in (flat, tilted):
        box = ink_box(im, out)
        assert box is not None
        assert box[0] >= 0 and box[1] >= 0 and box[2] <= im.width and box[3] <= im.height
    assert diff(flat, tilted).getbbox() is not None, "the tilt argument is not decoration"


@pytest.mark.parametrize("name,args", [
    ("text", []), ("text", [0.5]), ("text", ["x"]),
    ("text", [0.5, 0.5, 0.1, 1, 1, 1, 0, 0, 1, "body"]),
    ("text", [None, "y", "big", -5, 9, 1, 0.2, 0.5, 7, "serif", "", 1, 2, 3]),
    ("overlay", []), ("overlay", ["plain.jpg"]),
    ("overlay", ["plain.jpg", "a", "b", "c", "d", "e", "f"]),
    ("overlay", ["../x", 0.5, 0.5, 0.3, 0, 1, 0, 0, 9, 9]),
    ("frame", []), ("frame", [1, 1, 1]), ("frame", ["q", None, 2, -1, -3, 9]),
    ("collage", []), ("collage", ["a", 1]), ("collage", ["plain.jpg", "alpha.png", 0, 9, 2, 5]),
    ("watermark", []), ("watermark", ["PROOF"]), ("watermark", [1, 2, 3, 4, 5, 6]),
])
def test_a_half_written_or_nonsense_entry_is_a_no_op_not_a_crash(name, args):
    im = photo()
    out = run(name, im, args)
    assert out.size == im.size or name == "frame"
    assert out.mode in ("RGB", "RGBA")


def test_the_tables_cover_every_name_the_registry_will_ask_about():
    assert set(layers.SHAPE) == set(layers.CLAMP) == set(layers.LIMITS) == set(layers.APPLIERS)
    assert set(layers.FONTS) == {"display", "body", "mono", "condensed", "serif"}
    assert layers.SHAPE["text"][1] == 11 and layers.SHAPE["overlay"][1] == 8
    assert layers.SHAPE["watermark"][1] == 6
    for name, spec in layers.SHAPE.items():
        slots = layers.CLAMP[name]
        assert spec[0] in ("list", "group"), name
        if spec[0] == "group":
            assert spec[1] == len(slots) and spec[2] == layers.LIMITS[name] >= 1
        else:
            assert len(spec[1]) == len(slots)
            assert all(kind in ("f", "s") for kind in spec[1])
            assert [(slot is None) for slot in slots] == [kind == "s" for kind in spec[1]]
        for slot in slots:
            assert slot is None or (isinstance(slot, tuple) and slot[0] <= slot[1])


def test_no_operation_touches_the_picture_it_was_given(root):
    im = photo()
    before = im.tobytes()
    every = [
        ("text", [0.5, 0.4, 0.08, 1, 1, 1, 0.05, 0.4, 1, "display", "hi there"]),
        ("overlay", ["plain.jpg", 0.5, 0.5, 0.4, 20, 1, 1, 0]),
        ("frame", [1, 1, 1, 0.08, 0.02, 0.0]),
        ("collage", ["plain.jpg", "alpha.png", 2, 0.04, 0.5, 1]),
        ("watermark", ["PROOF", 0.5, 0.5, 0.04, 0.6, 0.1]),
    ]
    for name, args in every:
        out = run(name, im, args)
        assert im.tobytes() == before, f"{name} mutated its input"
        assert diff(im, out).getbbox() is not None, f"{name} did nothing"


def test_no_operation_falls_back_to_walking_pixels(root):
    """The budget is a multiple of one whole-frame Pillow pass, measured on this machine in
    this moment - and measured the same way the operation is measured.

    One sample of each was not enough: three adjacent timings of the identical pass on this
    laptop came out 0.26 s, 0.89 s and 0.32 s, so a baseline caught in a quiet instant made a
    collage that really costs four passes report fourteen and fail a 12-pass budget. Medians
    on both sides keep the test's teeth - a Python pixel loop is 100x, which no amount of
    sampling noise reaches - and the pass is timed again in front of every op, so a budget is
    never quoted for one instant and spent at another.
    """
    im = Image.new("RGB", (4000, 4000), BASE)
    every = [
        ("text", [0.5, 0.82, 0.06, 1, 1, 1, 0.05, 0.6, 1, "display", "THE SHOP NOTE"]),
        ("overlay", ["plain.jpg", 0.35, 0.4, 0.6, 25, 0.9, 4, 0]),
        ("watermark", ["PROOF", 0.5, 0.5, 0.02, 0.3, -20]),
        ("frame", [1, 1, 1, 0.04, 0.01, 0.03]),
        ("collage", ["plain.jpg", "alpha.png", 2, 0.03, 0.5, 0]),
    ]
    out = im
    for name, args in every:
        pass_cost, _ = median_of(lambda: ImageChops.add(im, im), runs=2)
        took, out = median_of(lambda: layers.APPLIERS[name](out, args))
        assert max(out.size) <= layers.MAX_EDGE
        assert took < 12 * pass_cost, f"{name} cost {took:.2f} s against a {pass_cost:.2f} s pass"
