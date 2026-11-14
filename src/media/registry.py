"""What the Edit screen shows, and in which order the pipeline runs.

The engines know how to move pixels; this file is the only place that says which control
belongs to which rail, what she calls it, and which argument slot each control writes.
The page is generated from it, so a tool the engine can already run shows up without a
second line of code being written anywhere.

A field's `at` is the position it occupies in the recipe entry. Slots nobody fills stay
zero, which is what makes an untouched control a no-op.
"""

from dataclasses import dataclass


@dataclass
class F:
    """One control, mapped to the argument slot it writes."""
    at: int
    label: str
    kind: str = "slider"        # slider | switch | choice | colour | text | file
    lo: float = 0.0
    hi: float = 1.0
    step: float = 0.05
    value: float = 0.0
    unit: str = ""
    hint: str = ""
    options: tuple = ()


@dataclass
class Tool:
    op: str
    label: str
    fields: tuple
    stroke: bool = False        # she paints positions on the picture for these
    points: tuple = (0, 1)      # which slots the position writes into
    repeats: bool = True        # False keeps exactly one position, the last one she tapped
    note: str = ""


# Pipeline order. Geometry first, because everything after it is measured in fractions of
# whatever frame survives; the brush before the composites, so a text outline never gets
# smoothed and a second photo always lands on top of the finished picture.
RAILS = ("frame", "light", "colour", "lens", "skin", "face", "cut", "design", "layer")
TITLES = {"frame": "Frame", "light": "Light", "colour": "Colour", "lens": "Lens",
          "skin": "Skin", "face": "Face", "cut": "Cut", "design": "Design",
          "layer": "Layers"}

FONTS = ("display", "body", "serif", "condensed", "mono")
BLENDS = ("normal", "multiply", "screen", "overlay", "soft light", "difference",
          "lighten", "darken")
MOTIONS = ("slim sideways", "slim both ways", "push along a line")

SIZE = F(2, "brush", "slider", 0.02, 0.4, 0.005, 0.09,
         "", "how wide the stroke is, against the short edge")
AMOUNT = F(3, "amount", "slider", 0.0, 1.0, 0.02, 0.4)

SKIN = {
    "smooth": Tool("smooth", "Smooth skin", (SIZE, AMOUNT), stroke=True,
                   note="Lifts mid-frequency texture inside the stroke and leaves the shading "
                        "alone. Past about 0.6 skin starts to read as plastic."),
    "texture": Tool("texture", "Return texture",
                    (F(2, "brush", "slider", 0.02, 0.4, 0.005, 0.12),
                     F(3, "amount", "slider", 0, 1, 0.02, 0.5)), stroke=True,
                    note="Puts high-frequency detail back where you smoothed. This is the "
                         "difference between retouched and wax."),
    "matte": Tool("matte", "Kill shine",
                  (F(2, "brush", "slider", 0.02, 0.4, 0.005, 0.1),
                   F(3, "amount", "slider", 0, 1, 0.02, 0.6)), stroke=True,
                  note="Only bright, colourless pixels come down, so a highlight on a cheekbone "
                       "survives and a sweat patch does not."),
    "whiten": Tool("whiten", "Whiten",
                   (F(2, "brush", "slider", 0.01, 0.25, 0.005, 0.05),
                    F(3, "amount", "slider", 0, 1, 0.02, 0.5)), stroke=True,
                   note="Lifts the near-white end of the range and pulls yellow out of it. It "
                        "cannot invent white where the file recorded none."),
    "brighten": Tool("brighten", "Dodge and burn",
                     (F(2, "brush", "slider", 0.02, 0.4, 0.005, 0.1),
                      F(3, "amount", "slider", -1, 1, 0.02, 0.35),
                      F(4, "band", "slider", 0, 1, 0.02, 0.55, "",
                         "which brightness moves: low burns the shadows, high lifts the light")),
                     stroke=True,
                     note="Moves one brightness band at a time - the under-eye, the T-zone, a "
                          "jawline - and leaves the rest of the tonal range alone."),
    "makeup": Tool("makeup", "Recolour",
                   (F(2, "brush", "slider", 0.01, 0.3, 0.005, 0.06),
                    F(3, "amount", "slider", 0, 1, 0.02, 0.5),
                    F(4, "hue", "slider", 0, 360, 1, 350, "°"),
                    F(5, "saturation", "slider", 0, 1, 0.02, 0.7)),
                   stroke=True,
                   note="Rotates pixels that already carry colour toward the hue you chose, so it "
                        "recolours a lip rather than drawing one."),
    "warp": Tool("warp", "Reshape",
                 (F(2, "brush", "slider", 0.02, 0.6, 0.01, 0.14),
                  F(3, "amount", "slider", -1, 1, 0.02, -0.4, "",
                    "negative takes volume off, positive adds it"),
                  F(4, "motion", "slider", 0, 2, 1, 0, "", "", MOTIONS),
                  F(5, "feather", "slider", 0.05, 1, 0.05, 0.4, "",
                    "how soft the rim of the drag is"),
                  F(6, "direction", "slider", 0, 360, 5, 0, "°",
                    "which way it pushes, for the push motion only")),
                 stroke=True,
                 note="A real mesh warp. Pixels move, none are invented, and the background "
                      "moves with them - that is what gives a reshape away."),
    "eyes": Tool("eyes", "Eyes",
                 (F(2, "brush", "slider", 0.01, 0.12, 0.005, 0.045),
                  F(3, "amount", "slider", 0, 1, 0.02, 0.45)), stroke=True,
                 note="Whitens the sclera, puts a little life back in the iris and lifts the size "
                      "a hair. Past 0.6 they look painted, which is the whole skill."),
}

EFFECTS = {
    "auto": Tool("auto", "Auto enhance",
                 (F(0, "amount", "slider", 0, 1, 0.05, 0.7, "",
                    "how far to push what it read off the histogram"),),
                 note="Finds where this file's blacks and whites actually land and stretches them "
                      "toward the ends, then a proportional contrast and colour lift."),
    "perspective": Tool(
        "perspective", "Keystone",
        tuple(F(i, f"{name} x" if i % 2 == 0 else f"{name} y", "slider", 0, 1, 0.005, v, "",
                "where that corner pulls from")
              for i, (name, v) in enumerate((("top left", 0.0), ("top right", 1.0),
                                             ("bottom right", 1.0), ("bottom left", 0.0)))),
        note="Straightens a leaning building or a photographed screen by remapping four corners."),
    "stretch": Tool("stretch", "Proportions",
                    (F(0, "line", "slider", 0, 1, 0.01, 0.55, "",
                       "the height everything below it moves from"),
                     F(1, "amount", "slider", -0.5, 0.5, 0.01, 0.08),
                     F(2, "blend", "slider", 0.02, 1, 0.05, 0.5, "", "how soft the seam is")),
                    note="Lengthens or shortens everything below the line. Walls, door frames and "
                         "tiles give it away, so keep it modest and check the background."),
    "upscale": Tool("upscale", "Enlarge",
                    (F(0, "factor", "slider", 1, 4, 0.5, 2, "×"),),
                    note="Lanczos with a light denoise and unsharp, capped at 4000 px. A resample, "
                         "not a hallucination - detail the lens missed does not arrive."),
    "cutout": Tool("cutout", "Cut out",
                   (F(0, "tolerance", "slider", 0, 1, 0.02, 0.25, "",
                      "how far a shade drifts before it stops counting as background"),
                    F(1, "feather", "slider", 0, 1, 0.05, 0.35),
                    F(2, "flat colour instead of transparent", "switch"),
                    F(3, "backdrop hue", "slider", 0, 360, 1, 0, "°",
                       "only when filling: the wall's own brightness and colour, retinted")),
                   note="Flood-fills inward from the edges on colour proximity. It loves an even "
                        "wall and hates a busy street - look at the hair line before you post."),
    "splash": Tool("splash", "Colour splash",
                   (F(0, "hue", "slider", 0, 360, 1, 0, "°"),
                    F(1, "range", "slider", 0, 180, 1, 40, "°"),
                    F(2, "keep", "slider", 0, 1, 0.05, 1.0),
                    F(3, "desaturate rest", "slider", 0, 1, 0.05, 0.9)),
                   note="Everything except one band of hue goes grey."),
    "duotone": Tool("duotone", "Duotone",
                    (F(0, "shadows", "colour", value="#0a0a0a"),
                     F(3, "highlights", "colour", value="#e5e5e5"),
                     F(6, "amount", "slider", 0, 1, 0.02, 0.7)),
                    note="Maps the whole brightness ramp onto two colours - the poster look."),
    "pixelate": Tool("pixelate", "Mosaic",
                     (F(2, "brush", "slider", 0.03, 0.5, 0.01, 0.12),
                      F(3, "block", "slider", 0.01, 0.2, 0.005, 0.04, "",
                         "how coarse the squares are")), stroke=True,
                     note="For the face in the background that never agreed to be in your post."),
    "rays": Tool("rays", "Light leak",
                 (F(0, "x", "slider", 0, 1, 0.01, 0.75),
                  F(1, "y", "slider", 0, 1, 0.01, 0.15),
                  F(2, "spread", "slider", 0.05, 1, 0.05, 0.5),
                  F(3, "amount", "slider", 0, 1, 0.02, 0.4)),
                 note="A warm glow composited in screen mode, anchored wherever you want the sun."),
    "softfocus": Tool("softfocus", "Bloom",
                      (F(0, "amount", "slider", 0, 1, 0.02, 0.3),
                       F(1, "glow", "slider", 0, 1, 0.02, 0.4)),
                      note="Bright areas spill into their neighbours the way a fast lens does. It "
                           "softens light, not skin - that is what the smooth brush is for."),
    "mirror": Tool("mirror", "Kaleidoscope",
                   (F(0, "the fold runs", "choice", 0, 2, 1, 0, "", "",
                      ("side to side", "top to bottom", "diagonal")),
                    F(1, "panels", "slider", 1, 8, 1, 2, "",
                      "how many times the strip repeats across the frame"),
                    F(2, "soften the seam", "slider", 0, 0.5, 0.02, 0.0, "",
                      "blur just the join, so a fold does not read as a cut")),
                   repeats=False,
                   note="One strip of your own photo, mirrored and tiled across the frame - the "
                        "kaleidoscope both apps sell. Every panel is real pixels from that strip; "
                        "nothing is invented."),
}

LAYERS = {
    "text": Tool("text", "Text",
                 (F(2, "size", "slider", 0.02, 0.3, 0.005, 0.08, "",
                    "cap height against the frame"),
                  F(3, "colour", "colour", value="#ffffff"),
                  F(6, "outline", "slider", 0, 0.5, 0.02, 0.0),
                  F(7, "shadow", "slider", 0, 1, 0.05, 0.25),
                  F(8, "align", "slider", 0, 2, 1, 1, "", "", ("left", "centre", "right")),
                  F(9, "typeface", "choice", options=FONTS),
                  F(10, "words", "text")),
                 stroke=True,
                 note="Click where it should sit, then type. Every click is a separate line you "
                      "can change or delete; the controls edit the one you selected."),
    "overlay": Tool("overlay", "Second photo",
                    (F(0, "file", "file"),
                     F(1, "x", "slider", 0, 1, 0.01, 0.5),
                     F(2, "y", "slider", 0, 1, 0.01, 0.5),
                     F(3, "width", "slider", 0.05, 2, 0.01, 0.6, "", "against the frame"),
                     F(4, "angle", "slider", -180, 180, 1, 0, "°"),
                     F(5, "opacity", "slider", 0, 1, 0.02, 1.0),
                     F(6, "blend", "slider", 0, 7, 1, 0, "", "", BLENDS),
                     F(7, "fit", "slider", 0, 2, 1, 0, "", "", ("cover", "contain", "stretch"))),
                    note="Lays another file from the inbox over this one. The blend modes are "
                         "arithmetic, not a filter: a double exposure is screen at low opacity."),
    "frame": Tool("frame", "Border",
                  (F(0, "colour", "colour", value="#121212"),
                   F(3, "matte", "slider", 0, 0.3, 0.005, 0.05, "", "padding around the picture"),
                   F(4, "hairline", "slider", 0, 0.05, 0.002, 0.0),
                   F(5, "corners", "slider", 0, 0.2, 0.005, 0.02)),
                  note="Grows the canvas. A wide matte is how a photo survives being screenshotted "
                       "with someone else's interface around it."),
    "collage": Tool("collage", "Grid",
                    (F(0, "first file", "file"),
                     F(1, "second file", "file"),
                     F(2, "columns", "slider", 1, 3, 1, 2),
                     F(3, "gap", "slider", 0, 0.1, 0.005, 0.015),
                     F(4, "background", "slider", 0, 1, 0.02, 0.07),
                     F(5, "third file", "file")),
                    note="Frames from the inbox side by side - the before/after post, the size "
                         "comparison, the three-look carousel."),
    "watermark": Tool("watermark", "Proof mark",
                      (F(0, "words", "text"),
                       F(1, "x", "slider", 0, 1, 0.01, 0.5),
                       F(2, "y", "slider", 0, 1, 0.01, 0.5),
                       F(3, "size", "slider", 0.01, 0.1, 0.005, 0.03),
                       F(4, "opacity", "slider", 0, 1, 0.02, 0.18),
                       F(5, "tilt", "slider", -60, 60, 1, -30, "°")),
                      note="Repeats your handle diagonally across the frame, for a proof copy you "
                           "are not releasing yet."),
}

HUE_BANDS = ("every colour", "reds", "oranges", "yellows", "greens", "cyans", "blues",
             "purples", "skin")
STICKERS = ("arrow", "star", "ring", "speech bubble", "badge", "heart", "sparkle", "cross")
CUTSHAPES = ("circle", "hexagon", "rounded rectangle", "arch", "star")
EDGES = ("all four sides", "top", "bottom", "left", "right")
FITS = ("cover", "contain", "stretch")

# The tone rail moves whole curves; these ten move parts of one, or one hue at a time.
COLOUR = {
    "curves": Tool("curves", "Curves",
                   (F(0, "channel", "choice", 0, 3, 1, 0, "", "",
                      ("everything", "reds", "greens", "blues")),
                    F(1, "darks", "slider", -1, 1, 0.02, 0.0),
                    F(2, "mids", "slider", -1, 1, 0.02, 0.0),
                    F(3, "lights", "slider", -1, 1, 0.02, 0.0)),
                   repeats=False,
                   note="Three handles on one ramp, for the whole picture or a single channel. "
                        "It moves the tones the file already has - detail gone in a blown sky "
                        "does not come back."),
    "levels": Tool("levels", "Black & white points",
                   (F(0, "from black", "slider", 0, 0.5, 0.005, 0.0, "",
                      "everything at or under this goes solid black"),
                    F(1, "to white", "slider", 0.5, 1, 0.005, 1.0, "",
                      "everything at or over this goes pure white"),
                    F(2, "mids", "slider", -1, 1, 0.02, 0.0)),
                   repeats=False,
                   note="The fastest way out of a milky photo: it says where this file's black "
                        "and white actually land. Anything outside the two points is gone."),
    "vibrance": Tool("vibrance", "Vibrance",
                     (F(0, "amount", "slider", -1, 1, 0.02, 0.0),),
                     repeats=False,
                     note="Raises the flat colours and leaves the already-vivid ones alone, so "
                          "a red dress comes up without the face in it going orange."),
    "clarity": Tool("clarity", "Clarity",
                    (F(0, "amount", "slider", -1, 1, 0.02, 0.3),
                     F(1, "width", "slider", 0.005, 0.08, 0.001, 0.03, "",
                       "how large a detail counts as mid-tone texture")),
                    repeats=False,
                    note="Local contrast: edges get harder, the flat areas between them get "
                         "smoother. Past 0.6 on a face it starts looking like stone."),
    "dehaze": Tool("dehaze", "Dehaze",
                   (F(0, "amount", "slider", 0, 1, 0.02, 0.3),
                    F(1, "black back", "slider", 0, 1, 0.02, 0.3, "",
                       "how much density to put under the recovery")),
                   repeats=False,
                   note="Cuts through a milky wash by widening the range a foggy scene "
                        "compressed. Negative value hazes a clean shot, which is a look."),
    "hsl": Tool("hsl", "Colour by band",
                (F(0, "band", "choice", 0, 7, 1, 7, "", "", HUE_BANDS),
                 F(1, "hue", "slider", -1, 1, 0.02, 0.0),
                 F(2, "colour amount", "slider", -1, 1, 0.02, 0.0),
                 F(3, "lightness", "slider", -1, 1, 0.02, 0.0),
                 F(4, "how wide", "slider", 0.1, 1, 0.05, 0.5, "",
                     "how far past the band's middle the change reaches")),
                repeats=False,
                note="One hue at a time - greens out of a background, red down in a lipstick. "
                     "\"Skin\" is the warm band the retouch tools use, so the two agree."),
    "hue_rotate": Tool("hue_rotate", "Hue shift",
                       (F(0, "turn", "slider", -180, 180, 1, 0, "°"),
                        F(1, "which colours", "choice", 0, 7, 1, 0, "", "", HUE_BANDS)),
                       repeats=False,
                       note="Turns one colour into another - the violet dress from the red one. "
                            "It goes by hue alone, so anything sharing that hue moves too, "
                            "including the wall behind."),
    "split_tone": Tool("split_tone", "Split tone",
                       (F(0, "into darks", "colour", value="#6b8ac7"),
                        F(3, "into lights", "colour", value="#fad6a8"),
                        F(6, "balance", "slider", -1, 1, 0.02, 0.0, "",
                          "which half of the ramp each colour gets"),
                        F(7, "amount", "slider", 0, 1, 0.02, 0.25)),
                       repeats=False,
                       note="One colour tinted into the shadows, another into the highlights - "
                            "the teal-and-orange grade. At 0 amount nothing happens, so start "
                            "low and stop before the whites look flavoured."),
    "posterize": Tool("posterize", "Posterise",
                      (F(0, "levels", "slider", 2, 16, 1, 12, "",
                         "how many shades each colour is allowed"),),
                      repeats=False,
                      note="Flattens the ramp into steps. 12 is barely visible, 4 is a screen "
                            "print, 2 is a silhouette."),
    "invert": Tool("invert", "Invert",
                   (F(0, "amount", "slider", 0, 1, 0.02, 1.0),),
                   repeats=False,
                   note="Every colour to its opposite. Halfway is the ghost image; past 0.8 "
                        "skin goes cyan, which is either a mistake or the whole point."),
}

OPTICS = {
    "tiltshift": Tool("tiltshift", "Tilt-shift",
                      (F(0, "line", "slider", 0, 1, 0.005, 0.5, "", "the band that stays sharp"),
                       F(1, "how thick", "slider", 0.02, 0.5, 0.005, 0.22),
                       F(2, "blur", "slider", 0, 1, 0.02, 0.6),
                       F(3, "tilt", "slider", -45, 45, 1, 0, "°")),
                      repeats=False,
                      note="A strip stays in focus and the frame falls away above and below it. "
                            "Tilted, it reads as a shallow plane rather than a toy model."),
    "motion_blur": Tool("motion_blur", "Motion blur",
                        (F(0, "direction", "slider", 0, 180, 1, 0, "°"),
                         F(1, "length", "slider", 0, 0.2, 0.005, 0.05, "",
                           "how far the streak runs, against the short edge")),
                        repeats=False,
                        note="The whole frame averaged along one line - a pan, a car leaving. "
                             "It streaks faces with everything else, so it wants a wide shot."),
    "radial_blur": Tool("radial_blur", "Zoom blur",
                        (F(0, "x", "slider", 0, 1, 0.01, 0.5),
                         F(1, "y", "slider", 0, 1, 0.01, 0.5),
                         F(2, "amount", "slider", 0, 1, 0.02, 0.35),
                         F(3, "reach", "slider", 0, 1, 0.02, 0.4, "",
                              "how far out from the point it drags")),
                       repeats=False,
                       note="Streaks run outward from one point, so the frame reads as moving "
                            "toward it. Put the point on what you want looked at."),
    "fisheye": Tool("fisheye", "Bulge",
                    (F(0, "amount", "slider", -1, 1, 0.02, 0.3),
                     F(1, "x", "slider", 0, 1, 0.01, 0.5),
                     F(2, "y", "slider", 0, 1, 0.01, 0.5)),
                    repeats=False,
                    note="A radial remap: positive pushes the middle out at the cost of the rim, "
                            "negative sucks it in. The corners stay pinned where they started."),
    "prism": Tool("prism", "Chromatic split",
                  (F(0, "amount", "slider", 0, 1, 0.02, 0.3),
                   F(1, "x", "slider", 0, 1, 0.01, 0.5),
                   F(2, "y", "slider", 0, 1, 0.01, 0.5)),
                  repeats=False,
                  note="The three colour channels grow at three slightly different rates about "
                        "one point, so colour fringes the edges and flat areas stay clean."),
    "bokeh": Tool("bokeh", "Light points",
                  (F(0, "from how bright", "slider", 0, 1, 0.02, 0.7),
                   F(1, "bloom", "slider", 0, 1, 0.02, 0.4),
                   F(2, "disc", "slider", 0.01, 0.15, 0.005, 0.05, "",
                       "how big the points open up"),
                   F(3, "shape", "slider", 0, 360, 1, 0, "°", "",
                       "0 is round, 90 pulls them into ovals")),
                  repeats=False,
                  note="Only what is already bright lifts into a soft disc and is laid back in "
                        "screen mode. Under the threshold the shadows keep their own pixels."),
    "orton": Tool("orton", "Glow plate",
                  (F(0, "amount", "slider", 0, 1, 0.02, 0.3),
                   F(1, "softness", "slider", 0, 1, 0.02, 0.4)),
                  repeats=False,
                  note="The frame screened against a blurred copy of itself: light spills into "
                        "light, density leaves the shadows. A true black stays a true black."),
    "lightleak": Tool("lightleak", "Case leak",
                      (F(0, "angle", "slider", 0, 360, 1, 0, "°"),
                       F(1, "colour", "colour", value="#ff9452"),
                       F(4, "amount", "slider", 0, 1, 0.02, 0.3)),
                      repeats=False,
                      note="A leak in from one edge, added only - it can brighten, never paint "
                            "over. The far side of the frame stays exactly what it was."),
    "glitch": Tool("glitch", "Digital damage",
                   (F(0, "amount", "slider", 0, 1, 0.02, 0.3),
                    F(1, "slices", "slider", 0, 1, 0.02, 0.4, "", "how many bands get moved"),
                    F(2, "shift", "slider", 0, 1, 0.02, 0.3, "", "how far each band slides"),
                    F(3, "seed", "slider", 0, 1, 0.01, 0.2, "",
                       "which bands - the same seed gives the same damage")),
                   repeats=False,
                   note="Bands of the frame displaced and their colour channels split. The seed "
                        "makes it repeatable, so re-exporting a recipe does not reshuffle it."),
}

MESH = {
    "swirl": Tool("swirl", "Swirl",
                  (SIZE, F(3, "twist", "slider", -360, 360, 1, 90, "°"),
                   F(4, "soft edge", "slider", 0.05, 1, 0.05, 0.45)),
                  stroke=True,
                  note="Turns everything inside the brush about its own middle, and leaves "
                       "outside it exactly alone. Negative twists the other way."),
    "inflate": Tool("inflate", "Inflate",
                    (SIZE, F(3, "amount", "slider", -1, 1, 0.02, 0.4, "",
                             "negative pinches instead of swelling"),
                     F(4, "soft edge", "slider", 0.05, 1, 0.05, 0.45)),
                    stroke=True,
                    note="Pushes pixels outward from the brush, so a shape grows without moving "
                         "where it is. Backgrounds bend, so watch the lines behind what you "
                         "resize."),
}

REPAIR = {
    "patch": Tool("patch", "Clone",
                  (F(2, "brush", "slider", 0.005, 0.4, 0.005, 0.06),
                   F(3, "source size", "slider", 0.2, 1, 0.05, 0.8, "",
                      "how much of the neighbouring area to sample"),
                   F(4, "across", "slider", -0.5, 0.5, 0.005, 0.12, "",
                      "where the pixels are taken from, relative to the tap"),
                   F(5, "down", "slider", -0.5, 0.5, 0.005, 0.0),
                   F(6, "soft edge", "slider", 0.05, 1, 0.05, 0.5),
                   F(7, "match tone", "slider", 0, 1, 0.02, 0.7, "",
                       "how far the patch is retinted to where it lands")),
                  stroke=True,
                  note="Moves real pixels from beside the spot onto the spot and tones them to "
                       "the surroundings - the one that keeps texture, lighting and grain "
                       "honest. Nothing is invented."),
    "conceal": Tool("conceal", "Concealer",
                    (F(2, "brush", "slider", 0.01, 0.3, 0.005, 0.05),
                     F(3, "smooth", "slider", 0, 1, 0.02, 0.5),
                     F(4, "lift", "slider", -1, 1, 0.02, 0.2, "",
                         "up for a shadow under the eye, down for a red mark")),
                    stroke=True,
                    note="A finer softening than the skin brush, then a narrow brightness band - "
                         "the under-eye trick. It evens what is there; it does not remove a "
                         "structure."),
    "red_eye": Tool("red_eye", "Red eye",
                    (F(2, "brush", "slider", 0.005, 0.12, 0.001, 0.025),
                     F(3, "amount", "slider", 0, 1, 0.02, 0.8)),
                    stroke=True,
                    note="Only the small dark-red cluster goes grey and down. White, skin and "
                         "the iris itself are left alone, so it cannot flatten a whole eye."),
    "dewy": Tool("dewy", "Dewy",
                 (F(2, "brush", "slider", 0.01, 0.4, 0.005, 0.1),
                  F(3, "amount", "slider", 0, 1, 0.02, 0.5)),
                 stroke=True,
                 note="The opposite of matte: the bright, nearly colourless pixels go up, so "
                      "cheekbones and the tip of the nose catch the light."),
    "flyaway": Tool("flyaway", "Flyaways",
                    (F(2, "brush", "slider", 0.02, 0.35, 0.005, 0.08),
                     F(3, "amount", "slider", 0, 1, 0.02, 0.7)),
                    stroke=True,
                    note="Smears a strand along the direction it lies, and only where dark sits "
                         "against light - so the hair itself keeps its edge and the loose hairs "
                         "against the background go."),
    "tan": Tool("tan", "Bronzer",
                 (F(0, "amount", "slider", 0, 1, 0.02, 0.3),
                  F(1, "hue", "slider", 20, 45, 1, 33, "°", "",
                     "where the warmed skin tone sits"),
                  F(2, "warmth", "slider", 0, 1, 0.02, 0.45),
                  F(3, "reach", "slider", 0, 1, 0.02, 0.35, "",
                     "how wide a band of colour around that hue counts as skin")),
                 repeats=False,
                 note="Warms and darkens everything inside the skin-colour window, hue and all. "
                      "It is colour maths, not a scan: a red brick wall will take a tan too."),
    "skin_tone": Tool("skin_tone", "Skin balance",
                      (F(0, "hue", "slider", -1, 1, 0.02, 0.0, "",
                         "away from orange, or toward it"),
                       F(1, "colour amount", "slider", -1, 1, 0.02, 0.0),
                       F(2, "amount", "slider", 0, 1, 0.02, 0.4),
                       F(3, "reach", "slider", 0, 1, 0.02, 0.35)),
                      repeats=False,
                      note="Two levers inside the same skin-colour window, so a flushed nose or "
                           "a sallow light comes off without touching the background."),
}

DESIGN = {
    "edge_expand": Tool("edge_expand", "Grow the frame",
                        (F(0, "which side", "choice", 0, 4, 1, 0, "", "", EDGES),
                         F(1, "how far", "slider", 0, 0.5, 0.01, 0.12, "",
                            "against the short edge"),
                         F(2, "blur", "slider", 0, 1, 0.02, 0.5),
                         F(3, "darken", "slider", 0, 1, 0.02, 0.35)),
                        repeats=False,
                        note="The frame grows into its own edge: the neighbouring background, "
                             "mirrored, blurred and darkened. It buys you a 4:5 from a square - "
                             "it never invents scenery."),
    "bg_replace": Tool("bg_replace", "New backdrop",
                       (F(0, "backdrop file", "file"),
                        F(1, "flat colour", "colour", value="#f4f1ea"),
                        F(4, "soft edge", "slider", 0, 1, 0.05, 0.3),
                        F(5, "reach", "slider", 0, 1, 0.02, 0.2, "",
                           "how far past the subject the cut extends"),
                        F(6, "how it fills", "choice", 0, 2, 1, 0, "", "", FITS)),
                       repeats=False,
                       note="Flood-fills inward from the edges, then drops the subject onto a "
                            "file from your inbox or onto the colour you chose. Needs an even "
                            "background to start with - look at the hair line before you post."),
    "glow_edge": Tool("glow_edge", "Rim glow",
                      (F(0, "colour", "colour", value="#7bd3ff"),
                       F(3, "reach", "slider", 0.005, 0.5, 0.005, 0.06, "",
                          "how far the ring spills out"),
                       F(4, "amount", "slider", 0, 1, 0.02, 0.6)),
                      repeats=False,
                      note="The subject's own silhouette, blurred, tinted and laid behind it. "
                           "Uses the same cutout as the backdrop swap, so on a busy frame the "
                           "glow follows wherever the fill stopped."),
    "shape_crop": Tool("shape_crop", "Cut to shape",
                       (F(0, "shape", "choice", 0, 4, 1, 0, "", "", CUTSHAPES),
                        F(1, "inset", "slider", 0, 0.2, 0.005, 0.0, "",
                           "how much of the edge to leave outside the shape"),
                        F(2, "corner", "slider", 0, 0.2, 0.005, 0.05, "",
                           "rounded rectangle only"),
                        F(3, "outside", "choice", 0, 2, 1, 1, "", "",
                           ("transparent", "white", "the colour below")),
                        F(4, "colour", "colour", value="#f4f1ea")),
                       repeats=False,
                       note="Cuts the print to a silhouette - the circle avatar, the arch for a "
                            "story cover. Transparent keeps the hole; a colour fills it."),
    "draw": Tool("draw", "Brush",
                 (F(2, "brush", "slider", 0.005, 0.6, 0.005, 0.03),
                  F(3, "colour", "colour", value="#ff3b30"),
                  F(6, "opacity", "slider", 0, 1, 0.02, 1.0),
                  F(7, "hard edge", "slider", 0, 1, 0.02, 0.85, "",
                     "0 is a spray, 1 is a marker")),
                 stroke=True,
                 note="A dab of colour wherever you tap, and a line wherever you drag. Every "
                      "tap is its own mark, so one wrong stroke does not take the rest with it."),
    "sticker": Tool("sticker", "Sticker",
                    (F(2, "size", "slider", 0.02, 1, 0.01, 0.14, "",
                       "against the short edge"),
                     F(3, "shape", "choice", 0, 7, 1, 0, "", "", STICKERS),
                     F(4, "colour", "colour", value="#ffd400"),
                     F(7, "turn", "slider", -360, 360, 1, 0, "°"),
                     F(8, "outline", "slider", 0, 0.2, 0.005, 0.04, "",
                        "a darker edge of the same colour")),
                    stroke=True,
                    note="Arrows, stars, rings and bubbles drawn from polygons at four times "
                         "the size and scaled back, so the edges stay crisp. Nothing is loaded "
                         "and nothing is billed."),
    "curved_text": Tool("curved_text", "Text on an arc",
                        (F(2, "size", "slider", 0.01, 0.2, 0.005, 0.08, "",
                           "cap height against the frame"),
                         F(3, "colour", "colour", value="#ffffff"),
                         F(6, "outline", "slider", 0, 0.5, 0.02, 0.0),
                         F(7, "shadow", "slider", 0, 1, 0.05, 0.25),
                         F(8, "align", "choice", 0, 2, 1, 1, "", "",
                            ("left", "centre", "right")),
                         F(9, "typeface", "choice", options=FONTS),
                         F(10, "words", "text"),
                         F(11, "arc radius", "slider", 0.05, 1, 0.01, 0.45, "",
                             "against the short edge"),
                         F(12, "sweep", "slider", -360, 360, 1, 120, "°",
                             "positive hangs over the top, negative under the bottom")),
                        stroke=True,
                        note="Each letter turned on its own so the words ride a circle centred "
                             "where you tapped - the badge, the round sticker, the logo ring. "
                             "Turning letters is the expensive part, so long passages get "
                             "dropped rather than slowed."),
}

ORDER = {
    "frame": ("rotate", "crop", "flip", "mirror", "perspective", "upscale"),
    "light": ("auto", "exposure", "brightness", "contrast", "saturation", "temperature",
              "tint", "highlights", "shadows", "gamma", "fade", "blackwhite", "sharpness",
              "structure", "grain", "vignette", "blur", "duotone", "splash", "softfocus"),
    "colour": ("curves", "levels", "vibrance", "clarity", "dehaze", "hsl", "hue_rotate",
               "split_tone", "posterize", "invert"),
    "lens": ("lens_blur", "tiltshift", "motion_blur", "radial_blur", "fisheye", "prism",
             "bokeh", "orton", "rays", "lightleak", "glitch", "pixelate"),
    "skin": ("smooth", "texture", "matte", "heal", "whiten", "patch", "conceal", "red_eye",
             "dewy", "flyaway", "tan", "skin_tone"),
    "face": ("warp", "swirl", "inflate", "eyes", "brighten", "makeup", "stretch", "restore"),
    "cut": ("cutout", "overlay"),
    "design": ("edge_expand", "bg_replace", "glow_edge", "shape_crop", "draw", "sticker",
               "curved_text"),
    "layer": ("text", "frame", "collage", "watermark"),
}


def tone(name: str, label: str, lo: float, hi: float, step: float, unit: str, note: str) -> Tool:
    """The tone sliders all share one shape, so they are described once here and filled in
    from the engine's own ranges rather than being typed twice."""
    return Tool(name, label, (F(0, label, "slider", lo, hi, step, 0.0, unit, note),), note=note)


RAIL = {name: rail for rail in RAILS for name in ORDER[rail]}
