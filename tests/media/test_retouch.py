import math
import time

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageMath

from src.media.retouch import (APPLIERS, CLAMP, LIMITS, SHAPE, _brush, _hold,
                               _warp_field, reach)

SIZE = (600, 900)

GOOD = {
    "smooth": [0.5, 0.55, 0.25, 0.8],
    "texture": [0.5, 0.55, 0.25, 0.8],
    "matte": [0.5, 0.55, 0.25, 0.9],
    "whiten": [0.5, 0.55, 0.25, 0.9],
    "brighten": [0.5, 0.55, 0.25, 0.8, 0.5],
    "tint": [0.5, 0.55, 0.25, 0.9, 350.0, 0.6],
    "warp": [0.5, 0.55, 0.25, 0.8, 0.0, 0.5, 0.0],
    "slim": [0.5, 0.55, 0.25, 0.8, 0.0, 0.5, 0.0, 2.0],
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


def bars(n=9, size=400, pitch=38, wide=12):
    """A fence of thin dark verticals. This is the honest way to see a fold: a warp that
    turns its own mesh inside out reorders these, and no amount of averaging hides it."""
    im = Image.new("RGB", (size, size), (240, 240, 240))
    d = ImageDraw.Draw(im)
    for i in range(n):
        x = 30 + i * pitch
        d.rectangle([x, 40, x + wide, size - 40], fill=(20, 20, 20))
    return im


def dark_runs(im, row=200, thresh=130, min_wide=4):
    """The centre of every dark bar on one row, left to right.

    Two numbers here are load-bearing. The threshold has to sit at the midpoint of the two
    tones, and a run narrower than min_wide is not a bar: a brush rim drags the edge of the
    neighbouring bar a fraction of a pixel inward, which is what any liquify pinch does, and
    a detector that calls that sliver a bar reports a fold where nothing turned over. What a
    real fold leaves behind is bar-width material laid over itself, and that is what this
    counts.
    """
    runs, start = [], None
    for x in range(im.width + 1):
        dark = x < im.width and sum(im.getpixel((x, row))) < 3 * thresh
        if dark and start is None:
            start = x
        elif not dark and start is not None:
            if x - start >= min_wide:
                runs.append((start + x - 1) / 2)
            start = None
    return runs


def dark_widths(im, row=200, thresh=130, min_wide=4):
    """How wide each dark bar is, left to right, narrow rim slivers dropped."""
    return [w for w, s in _run_table(im, row, thresh) if w >= min_wide]


def _run_table(im, row, thresh):
    out, start, run = [], None, 0
    for x in range(im.width + 1):
        dark = x < im.width and sum(im.getpixel((x, row))) < 3 * thresh
        if dark:
            run += 1
            start = x if start is None else start
        elif run:
            out.append((run, start))
            run, start = 0, None
    return out


def test_slim_at_full_strength_never_folds_the_fence_over():
    """The one claim the extreme range is allowed to make. A small brush at strength 3 is
    exactly where an unguarded mesh turns over, so this is what would fail if HOLD went."""
    im = bars()
    was, wide = dark_runs(im), dark_widths(im)
    out = APPLIERS["slim"](im, [0.45, 0.5, 0.12, -3.0, 0.0, 0.5, 0.0, 4.0])
    now, thick = dark_runs(out), dark_widths(out)
    assert len(now) == len(was), "a bar vanished or split - the mesh laid pixels over itself"
    assert all(b > a for a, b in zip(now, now[1:])), "the bars changed order - that is a fold"
    assert max(thick) <= max(wide) + 2, f"a bar smeared to {max(thick)}px - that is a fold"
    assert any(abs(n - w) > 0.6 for n, w in zip(now, was)), "strength 3 moved nothing"


def test_the_guard_stops_where_the_mapping_turns_back_on_itself():
    """The fold the fence test can only see after the mesh averaged it away, measured on the
    mapping itself: below the guard the source coordinate always runs forward, above it
    some pixels read back over their own neighbours.
    """
    args = [0.5, 0.5, 0.1, -3.0, 0.0, 0.5, 0.0, 1.0]
    row = 450

    def forward(amount):
        st = list(args)
        st[3] = amount
        d = _brush(st, SIZE[0], SIZE[1], st[7], 0.0)
        cx, cy, ra, rb, ca, sa = d[1:7]
        sx = [x - _warp_field(x, row + 0.5, cx, cy, ra, rb, ca, sa,
                              amount, 0, st[5])[0] for x in range(120, 481)]
        return all(b > a for a, b in zip(sx, sx[1:]))

    held = _hold(args[3], _brush(args, SIZE[0], SIZE[1], args[7], 0.0), 0, args[5])
    assert held > args[3], "the guard did not rein the stroke in at all"
    assert forward(held), "a guarded stroke still folds its own mapping"
    assert not forward(-3.0), "an unguarded stroke at 3 does not fold - the guard is dead weight"


def test_the_reach_the_page_is_handed_is_the_amount_the_engine_applies():
    """The strength slider stops on this number, so it has to be the stroke the engine
    actually ran - a second opinion that disagrees with the first is a dead control."""
    for vals in ([0.5, 0.5, 0.22, -3.0, 0.0, 0.55, 0.0, 2.6],
                 [0.5, 0.5, 0.10, -3.0, 1.0, 0.35, 45.0, 1.0],
                 [0.5, 0.5, 0.40, -3.0, 2.0, 0.90, 90.0, 4.0],
                 [0.5, 0.5, 0.30, -3.0, 0.0, 0.05, 0.0, 0.2]):
        top = reach(vals, "slim", SIZE[0], SIZE[1])
        st = list(vals)
        d = _brush(st, SIZE[0], SIZE[1], st[7], math.radians(st[6]))
        assert top == pytest.approx(_hold(3.0, d, int(round(st[4])), st[5]), rel=1e-9)
        assert -top == pytest.approx(_hold(-3.0, d, int(round(st[4])), st[5]), rel=1e-9)


def test_the_picture_is_frozen_above_the_reach_the_slider_offers():
    """Asking for more than the reported ceiling changes nothing, which is exactly why the
    slider must not offer it; asking for less does, so the ceiling is not a blanket no-op."""
    vals = [0.5, 0.5, 0.22, -3.0, 0.0, 0.55, 0.0, 2.6]
    top = reach(vals, "slim", SIZE[0], SIZE[1])
    im = gritty(bars(size=SIZE[0], pitch=44, wide=16))
    at_top = APPLIERS["slim"](im, [0.5, 0.5, 0.22, -top, 0.0, 0.55, 0.0, 2.6])
    over = APPLIERS["slim"](im, [0.5, 0.5, 0.22, -3.0, 0.0, 0.55, 0.0, 2.6])
    under = APPLIERS["slim"](im, [0.5, 0.5, 0.22, -top * 0.6, 0.0, 0.55, 0.0, 2.6])
    assert list(at_top.getdata()) == list(over.getdata()), "the ceiling is not where it stops"
    assert list(at_top.getdata()) != list(under.getdata()), "the ceiling killed the stroke"


def test_the_strength_slider_offers_nothing_the_brushes_cannot_deliver():
    """Every part of the declared range has to be reachable by some brush setting, and the
    settings the tool opens with have to reach the whole of it."""
    from src.media import edit
    spec = [f for f in edit.TOOL_OF["slim"].fields if f.at == 3][0]
    grid = [reach([0.5, 0.5, b, -3.0, m, f, 0.0, o], "slim", SIZE[0], SIZE[1])
            for b in (0.10, 0.22, 0.40) for m in (0.0, 1.0, 2.0)
            for f in (0.05, 0.2, 0.55, 0.8, 1.0) for o in (0.2, 1.0, 2.6, 3.5, 6.0)]
    assert max(grid) == pytest.approx(spec.hi, abs=spec.step), \
        f"the slider tops out at {spec.hi} but the brushes reach {max(grid)}"
    defaults = {f.at: f.value for f in edit.TOOL_OF["slim"].fields}
    opened = reach([0.5, 0.5, defaults[2], -3.0, defaults[4], defaults[5],
                    defaults[6], defaults[7]], "slim", SIZE[0], SIZE[1])
    assert opened >= spec.hi, "the slider starts with dead travel at its top"


def test_only_the_guarded_brush_reports_a_ceiling():
    """A control with no rein must not be handed one, and a half-written stroke must not
    raise on the way to the page that is only trying to size a slider.
    """
    from src.media import edit
    assert reach([0.5, 0.5, 0.2, -1.0, 0.0, 0.5, 0.0], "warp", SIZE[0], SIZE[1]) is None
    assert edit.reach_of("exposure", [0.4], SIZE[0], SIZE[1]) is None
    assert edit.reach_of("slim", ["a", None], SIZE[0], SIZE[1]) is None
    assert edit.reach_of("slim", [0.5, 0.5, 0.22, -3.0], SIZE[0], SIZE[1]) > 0.0


def test_the_ceiling_follows_the_brush_and_not_the_picture():
    """A bigger photo of the same pose takes the same strength: the rein is about how steep
    the mapping gets inside the brush, and both the move and its steepness scale together.
    """
    vals = [0.5, 0.5, 0.22, -3.0, 0.0, 0.55, 0.0, 2.6]
    same = [round(reach(vals, "slim", w, 1459), 6) for w in (400, 942, 2000)]
    assert len(set(same)) == 1, f"the ceiling drifted with the frame: {same}"
    soft = reach([0.5, 0.5, 0.22, -3.0, 0.0, 1.0, 0.0, 2.6], "slim", *SIZE)
    hard = reach([0.5, 0.5, 0.22, -3.0, 0.0, 0.2, 0.0, 2.6], "slim", *SIZE)
    assert soft > hard, "a hard edge is being allowed to go further than a soft one"


def test_slim_pulls_harder_than_reshape_on_the_same_brush():
    im = bars()
    was = dark_runs(im)
    subtle = dark_runs(APPLIERS["warp"](im, [0.45, 0.5, 0.5, -1.0, 0.0, 0.5, 0.0]))
    extreme = dark_runs(APPLIERS["slim"](im, [0.45, 0.5, 0.5, -3.0, 0.0, 0.5, 0.0, 1.0]))
    moved = lambda a: sum(abs(x - y) for x, y in zip(a, was))
    assert moved(extreme) > moved(subtle), "the extreme slider is not more extreme"


def test_a_round_slim_stroke_at_one_is_the_reshape_brush_exactly():
    """Both brushes are the same engine, so the new one cannot quietly disagree with the old
    one - and the recipe file she already saved keeps producing the pixels it produced."""
    im = skin()
    old = APPLIERS["warp"](im, [0.5, 0.55, 0.25, -0.7, 0.0, 0.5, 0.0])
    new = APPLIERS["slim"](im, [0.5, 0.55, 0.25, -0.7, 0.0, 0.5, 0.0, 1.0])
    assert new.tobytes() == old.tobytes()


def test_the_oval_reaches_where_the_dot_cannot():
    """A waist is not round, so the elongated brush has to move ground a round one leaves
    byte-identical - otherwise the extra control is decoration.

    Counted over a band rather than one pixel on purpose: the skin field is noise, and a
    single pixel can land on a shift that reads back the same colour.
    """
    im = skin()
    band = (0, 560, SIZE[0], 700)          # under the round brush's rim, inside the oval
    dot = APPLIERS["slim"](im, [0.5, 0.5, 0.2, -1.4, 0.0, 0.5, 0.0, 1.0])
    long = APPLIERS["slim"](im, [0.5, 0.5, 0.2, -1.4, 0.0, 0.5, 0.0, 4.0])
    area = (band[2] - band[0]) * (band[3] - band[1])
    still = ImageChops.difference(im, dot).convert("L").crop(band).histogram()[0]
    moved = ImageChops.difference(im, long).convert("L").crop(band).histogram()[0]
    assert still == area, "the round brush leaked past its own rim"
    assert area - moved > 4000, "stretching the brush barely changed anything"


def test_the_axis_control_turns_which_way_the_move_acts():
    """The acting axis decides what gets squeezed: at zero it narrows the lit patch, a
    quarter turn later it shortens that patch instead - and neither may move the edge that
    runs across the squeeze.

    The probe column has to sit inside the turned brush, because past its rim the feather
    has nothing left to grip and the pixels there are byte-identical by design.
    """
    im = step_frame()
    flat = APPLIERS["slim"](im, [0.5, 0.5, 0.6, -1.0, 0.0, 0.5, 0.0, 1.0])
    turned = APPLIERS["slim"](im, [0.5, 0.5, 0.6, -1.0, 0.0, 0.5, 90.0, 1.0])
    assert edge_column(flat) < edge_column(im), "the flat squeeze did not narrow the patch"
    assert edge_column(turned) == edge_column(im), "a 90-degree squeeze must not pinch sideways"

    def top_edge(frame, x=260):
        for y in range(100, 250):
            if sum(frame.getpixel((x, y))) > 3 * 130:
                return y
        return 250

    assert top_edge(turned) > top_edge(im), "the turned squeeze did not shorten the patch"
    assert top_edge(flat) == top_edge(im), "a sideways squeeze must not move the top edge"


def test_three_max_stretch_strokes_on_a_phone_frame_are_fast():
    im = gritty(Image.new("RGB", SIZE, (170, 130, 105)))
    args = []
    for y in (0.35, 0.5, 0.65):
        args += [0.5, y, 0.6, -2.2, 0.0, 0.6, 0.0, 6.0]
    t0 = time.perf_counter()
    out = APPLIERS["slim"](im, args)
    secs = time.perf_counter() - t0
    assert out.size == SIZE and ImageChops.difference(im, out).getbbox() is not None
    assert secs < 3.0, f"3 extreme strokes took {secs:.2f}s"


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
                             "brighten", "tint", "warp", "slim", "eyes"}
    assert set(SHAPE) == set(CLAMP) == set(LIMITS) == set(APPLIERS)
    for name, shape in SHAPE.items():
        assert shape[0] == "group" and shape[1] == len(CLAMP[name])
        assert shape[2] == LIMITS[name] and 40 <= LIMITS[name] <= 60
        assert all(len(pair) == 2 and pair[0] <= pair[1] for pair in CLAMP[name])
