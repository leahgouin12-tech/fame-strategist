# Editor parity: Facetune (full) + PicsArt (full)

**Goal:** take the studio from 42 tools to ~80 by closing the gaps against the real, current
feature lists of both apps. Pillow-only, offline, $0, no new dependencies.

**Sources:** facetuneapp.com feature pages + pricing, App Store 1149994032, Play
`com.lightricks.facetune.free`, picsart.com tool pages, support.picsart.com how-tos
(fetched 2026-11-13). Full inventory lives in this file's gap tables; the raw list was
gathered live and is cited at the bottom.

**Naming note:** Facetune is Lightricks' app, not Lummi's. PicsArt's AI features are
credit-metered on their servers; ours run on her machine.

---

## The honest boundary

Facetune's inventory is ~90% **detection-driven**: face landmarks place the jaw/nose/lip
sliders, segmentation supplies the skin, hair, tooth and eye masks, generative models do
backdrop, vanish, clothes and Retake. PicsArt's is a **classical desktop core** (curves,
HSL, clone, warp, blend modes, masks, brushes, layers, text, stickers, collage, templates)
wrapped in a credit-metered generative layer.

This app has no model, no GPU and no network. So:

| Their feature | What we can honestly ship |
|---|---|
| Auto face sliders (jaw, chin, nose, lips, cheekbones, forehead, double chin) | The same geometry, **placed by her brush** — `warp`, `stretch`, `swirl`, `inflate`, `pinch` at the point she taps. No auto placement. |
| Skin / tooth / hair / eye masks from segmentation | **Colour-and-luminance heuristics**: skin-tone band, bright-low-sat specular band, dark-high-freq hair band. Works on most shots, misfires on similar-coloured clothing — the tool says so in its note. |
| Vanish / AI remove / generative fill | **Clone-patch** (sample one area into another, tone-matched) + feathered heal. Real removal, no invented pixels. |
| AI Expand / reframe / outpaint | **Edge-replicate + blur + fill** extension. Fills with the neighbouring background, not with new content. |
| AI background replace / green screen | **Flood-fill cutout** (already shipped) + paste onto a colour or one of her files. |
| Style transfer, cartoon/anime, AI avatars, Retake, virtual try-on | **Not available.** Not faked with a filter and not called by their name. |
| Curves, HSL, split tone, levels, clarity, dehaze, clone, mirror, tilt-shift, glitch, Orton, masks, brushes, stickers, curved text, blend modes | **Fully available.** These are pixel maths. This is where most of the new tools come from. |

Every tool below is classical image processing. Nothing here needs a model, and nothing
here is described to her as AI.

---

## Conventions (all waves must obey)

- Recipe entry = `["name", arg, ...]`. Fraction coordinates are relative to the frame
  **as it exists at that point in the pipeline**. Brush sizes are a fraction of the short
  edge (a *diameter*), except `text`, where size is a fraction of height.
- New engine code goes in the module that already owns that family: `edit.py` (geometry +
  tone), `retouch.py` (brushes + masks), `effects.py` (lens + distort), `layers.py`
  (compositing + text + shapes). Each exports `APPLIERS`, `SHAPE`, `CLAMP`, `LIMITS`.
- Registration is one `Tool(...)` entry in `src/media/registry.py` plus its name in
  `ORDER[rail]`. Rails are `frame light lens skin face cut layer`; a new rail means
  `RAILS`, `TITLES` and `ORDER` together. The page, the ledger and the pipeline order all
  read from the registry, so nothing else needs a second line of code.
- Colour fields are **one hex string in slot `at`**, folded out to three numbers by the
  page. Defaults must be hex (`test_a_colour_default_is_a_hex_the_picker_can_hold`).
- Every tool's `note` says what it does **and where it stops working**. No marketing
  verbs, no "AI", no promises.
- Tests: `tests/media/test_<module>.py`, one behavioural test per tool that proves the
  pixels actually moved where the tool claims and did **not** move where it does not.
  The existing `diff` / `ink_box` / `ink_fraction` helpers in `test_layers.py` are the
  pattern.
- Verify with `.venv/Scripts/python.exe -m pytest -q -p no:warnings` from the repo root.
  Pillow 13 only — no numpy, no scipy, no opencv, no torch, no installs.

---

## Wave 1 — the colour engine (PicsArt "Adjust", 11 tools)

Nothing here exists yet. This is the single biggest gap: the studio currently has sliders
but no *colour* control surface.

| op | rail | args (slot: meaning) | how |
|---|---|---|---|
| `curves` | light | 0: channel (0 rgb, 1 r, 2 g, 3 b) · 1: shadows −1..1 · 2: mids −1..1 · 3: highs −1..1 | build a 256-entry LUT from three control offsets, `Image.point()` per band |
| `levels` | light | 0: black point 0..0.5 · 1: white point 0.5..1 · 2: gamma −1..1 | stretch + power on a LUT |
| `vibrance` | light | 0: amount −1..1 | saturation scaled by `(1 - current saturation)` so already-vivid pixels and skin do not blow out |
| `hue_rotate` | light | 0: degrees −180..180 · 1: band (0 all, else the 7 hue bands) | HSV split, offset H, merge |
| `hsl` | light | 0: band (0 red … 6 purple, 7 skin) · 1: hue −1..1 · 2: saturation −1..1 · 3: lightness −1..1 · 4: range 0.1..1 (how wide the band is) | per-pixel weight from angular distance in H, applied to S and L |
| `split_tone` | light | 0-2: shadow colour (hex at 0) · 3-5: highlight colour (hex at 3) · 6: balance −1..1 · 7: amount 0..1 | multiply a luminance-ramp mask under and over the midpoint |
| `clarity` | light | 0: amount −1..1 · 1: radius 0.005..0.08 (fraction of short edge) | unsharp on a wide radius, mid-tone weighted |
| `dehaze` | light | 0: amount 0..1 · 1: lift 0..1 | black-point raise proportional to local minimum, then contrast + saturation |
| `invert` | light | 0: amount 0..1 | blend toward the negative |
| `posterize` | light | 0: levels 2..16 | `ImageOps.posterize` |
| `sepia` / `b&w` split | light | `blackwhite` exists; add `0: tone (0 neutral … 3 warm/split)` | extend the existing op rather than adding a twin |

## Wave 2 — the lens and the warp (PicsArt "Effects" + Facetune "Reshape", 12 tools)

| op | rail | args | how |
|---|---|---|---|
| `tiltshift` | lens | 0: y · 1: band width · 2: strength · 3: angle −45..45 | blur the frame, composite through a linear gradient mask |
| `motion_blur` | lens | 0: angle 0..180 · 1: length 0..0.2 | average N offset copies of the frame |
| `radial_blur` | lens | 0: x · 1: y · 2: amount · 3: falloff | average scaled copies about the anchor |
| `prism` | lens | 0: amount · 1: x · 2: y | split RGB bands and re-paste each scaled by a different factor (chromatic aberration) |
| `bokeh` | lens | 0: threshold 0..1 · 1: bloom 0..1 · 2: size · 3: angle | lift the points above threshold, blur, screen back |
| `orton` | lens | 0: amount · 1: softness | blur + screen blend against the original |
| `lightleak` | lens | 0: angle · 1-3: colour (hex at 1) · 2 slot free · 4: amount | radial/linear gradient, screen-blended from one edge |
| `glitch` | lens | 0: amount · 1: slices 0..1 · 2: channel shift · 3: seed | displace horizontal slices, offset R and B, optional scanlines |
| `fisheye` | lens | 0: amount −1..1 · 1: x · 2: y | inverse-radius remap through `Image.transform(MESH)` |
| `swirl` | face | 0: x · 1: y · 2: brush · 3: degrees −360..360 · 4: feather | mesh rotation weighted by distance |
| `inflate` | face | 0: x · 1: y · 2: brush · 3: amount −1..1 (negative = pinch) · 4: feather | radial scale weighted by distance |
| `mirror` | frame | 0: axis (0 vertical, 1 horizontal, 2 diagonal) · 1: folds 1..8 · 2: seam | half-frame transpose + tile |

`restore` (Facetune's undo brush) is a **stroke-level** feature: a `restore` entry holds
x, y, brush and erases every earlier warp's effect at that point by re-deriving from the
source frame. Implement in `edit.apply` by keeping the pre-warp image and compositing
through the brush mask.

## Wave 3 — repair, skin and design (Facetune "Retouch"/"Hair"/"Backdrop" + PicsArt "Tool"/"Draw"/"Stickers", 14 tools)

| op | rail | args | how |
|---|---|---|---|
| `patch` | skin | 0: x · 1: y · 2: radius · 3: source x · 4: source y · 5: feather · 6: tone match 0..1 | crop the source disc, match its mean/std to the target ring, paste through a feathered mask |
| `conceal` | skin | 0: x · 1: y · 2: brush · 3: amount · 4: brightness lift | smooth at half the radius of `smooth` + a narrow-band dodge |
| `red_eye` | skin | 0: x · 1: y · 2: brush | desaturate and darken only the small dark-red cluster under the tap |
| `tan` | skin | 0: amount · 1: hue 20..45 · 2: warmth | skin-tone-band mask (YCbCr Cr/Cb window), warm shift inside it |
| `skin_tone` | skin | 0: hue −1..1 · 1: saturation −1..1 · 2: amount | same mask, applied in HSV |
| `dewy` | skin | 0: x · 1: y · 2: brush · 3: amount | lift bright, low-saturation pixels inside the brush (the inverse of `matte`) |
| `flyaway` | skin | 0: x · 1: y · 2: brush · 3: amount | directional smoothing where dark high-frequency detail sits against a lighter background |
| `draw` | layer | 0: x · 1: y · 2: brush · 3-5: colour (hex at 3) · 6: opacity · 7: hardness | stamp along the recorded path, feathered |
| `sticker` | layer | 0: x · 1: y · 2: size · 3: kind (arrow, star, ring, bubble, badge, heart, spark, cross) · 4-6: colour · 7: rotate · 8: outline | procedural vector drawn with `ImageDraw`, supersampled 4× then downscaled |
| `curved_text` | layer | same as `text` plus an arc radius and a sweep | render each glyph rotated and stepped along the arc |
| `shape_crop` | cut | 0: shape (circle, hex, rounded, arch, star) · 1: inset · 2: corner radius · 3: fill (transparent / white / colour) | alpha mask multiply |
| `bg_replace` | cut | 0: file (or blank) · 1: colour (hex) · 2: feather · 3: expand · 4: fit | existing `cutout` alpha, then composite |
| `edge_expand` | frame | 0: direction (0 all, 1 up, 2 down, 3 left, 4 right) · 1: amount · 2: blur · 3: fade | replicate + blur the border strip, then darken toward the outside. **Not** outpainting; it fills with the neighbouring background and says so. |
| `glow_edge` | cut | 0: colour · 1: size · 2: amount | blur the cutout alpha, tint, screen behind the subject |

`overlay` gains mask fields (shape / gradient / inverted / feather) rather than a new op.

---

## What this does not claim

After all three waves the studio still cannot place a face slider by itself, cannot invent
a background, cannot restyle a photo, and cannot retouch video frame by frame. Those are
model features and the app has no model. The tools above are the parts of both apps that
are genuinely pixel maths, which is the larger half of PicsArt and the useful half of
Facetune.

## Verification, per wave

1. `pytest -q -p no:warnings tests/media` green.
2. Registry contract tests still pass (every field's range inside the engine's clamp; every
   colour default a hex).
3. A live drive in a real browser tab: build one recipe that uses at least eight of the new
   tools on a photo in `data/inbox`, save it, reopen it, and screenshot — the reopen is what
   catches round-trip bugs, which is where the last colour defect lived.
