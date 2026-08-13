"""
Composites material labels onto a generated swatch texture — an ASSET-PREP tool,
not part of the runtime reel pipelines. Run once when building new concept pairs.

WHY THIS EXISTS (do not skip it and let the image model render the type):
Flux and similar models produce unreliable spelling, kerning and alignment on
rendered text. Every swatch texture is therefore generated as a PURE CLEAN
texture — the generation prompt explicitly excludes text, labels and watermarks —
verified OCR-clean via ocr_verify.py, and only then labelled here with real
typography. This is a standing rule for this project, established after real
misrendered output.

TYPE TREATMENT (also established by prior iteration, not arbitrary):
- Fry's Baskerville, not Playfair Display — higher-contrast classical serif, reads
  premium rather than merely "editorial". Bundled in fonts/ and verified via the
  embedded name table, since filename alone proves nothing about what a font
  actually is.
- NO dark scrim, banner or background panel behind the text. A solid panel reads
  cheap. Legibility comes instead from adaptive ink, one subtle offset shadow, and
  a soft contrasting halo (see the CONTRAST HALO block below) that is invisible on
  an even surface and only does work where the ground fights the ink.
- ADAPTIVE INK: the mean luminance of the actual pixels behind each text line is
  sampled, and the ink switches to a warm off-white over dark ground or a deep
  espresso over light ground. This is what lets one code path label both a near
  black marble band and a pale limestone band without hand-tuning either.
- Wide letterspacing (tracking), all caps — the luxury/editorial convention seen
  in the reference material. PIL has no native tracking, so glyphs are drawn one
  at a time with an explicit advance.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_PATH = str(Path(__file__).resolve().parent / "fonts" / "FrysBaskerville.ttf")

INK_LIGHT = (242, 236, 226)   # warm off-white, for dark ground
INK_DARK = (58, 44, 36)       # deep espresso, for light ground
LUMA_THRESHOLD = 118          # below this mean luminance -> use light ink
SHADOW_OFFSET = (2, 3)
SHADOW_OPACITY_LIGHT_INK = 110  # shadow under pale ink on dark ground
SHADOW_OPACITY_DARK_INK = 70    # softer under dark ink on light ground

# CONTRAST HALO — added after a real legibility failure, read before removing.
#
# Adaptive ink picks ONE colour per line from the MEAN luminance behind that line.
# On a uniform surface that is fine. On d04's textures it was not: the chalk
# limestone band contains near-black blotches, so the line mean said "light
# ground, use dark ink" while part of the word sat over near-black.
#
# Measure this PER GLYPH, not per line. The correct metric is the mean luminance
# of a character's own pixels against the ring immediately around it; a per-line
# or per-column average mixes glyph, halo and background together and gives
# nonsense. On the shipped d04 card that metric scores the final 'E' of
# LIMESTONE at 0.9 out of 255 — those letters were not dim, they were invisible —
# while the same card's INDIGO LIMEWASH and AGED ELM lines score 119.8 and 102.7
# and are genuinely fine. A cruder column-average metric wrongly flagged AGED ELM
# as marginal; don't repeat that mistake.
#
# A stronger drop shadow does NOT fix this. The shadow is always black, so under
# DARK ink it adds nothing at all over a dark patch — dark ink plus dark shadow
# on dark ground. The halo is therefore drawn in the CONTRASTING tone: dark behind
# pale ink, pale behind dark ink. That guarantees local separation wherever the
# ground happens to match the ink.
#
# It is a soft blurred contour, NOT a scrim or panel — the no-solid-panel rule in
# this module's header still stands and this deliberately does not break it.
HALO_RADIUS = 11              # gaussian blur radius of the contour
HALO_GAIN = 3.6               # boosts the blurred mask so it reads near the glyph
HALO_ALPHA = 240              # peak opacity of the halo
HALO_FOR_LIGHT_INK = (8, 6, 5)        # dark halo behind pale ink
HALO_FOR_DARK_INK = (250, 248, 244)   # pale halo behind dark ink


def pick_ink(luma):
    """Returns (ink, shadow_alpha, halo_rgb) for a sampled background luminance."""
    if luma < LUMA_THRESHOLD:
        return INK_LIGHT, SHADOW_OPACITY_LIGHT_INK, HALO_FOR_LIGHT_INK
    return INK_DARK, SHADOW_OPACITY_DARK_INK, HALO_FOR_DARK_INK


def draw_label(overlay, xy, text, font, tracking, ink, shadow_alpha, halo_rgb):
    """
    Draws one tracked line onto an RGBA overlay as halo -> shadow -> ink, and
    returns the new overlay (alpha_composite does not mutate in place).
    """
    W, H = overlay.size
    mask = Image.new("L", (W, H), 0)
    _draw_tracked(ImageDraw.Draw(mask), xy, text, font, 255, tracking)
    mask = mask.filter(ImageFilter.GaussianBlur(HALO_RADIUS))
    mask = mask.point(lambda v: min(255, int(v * HALO_GAIN * HALO_ALPHA / 255)))
    halo = Image.new("RGBA", (W, H), tuple(halo_rgb) + (0,))
    halo.putalpha(mask)
    overlay = Image.alpha_composite(overlay, halo)

    draw = ImageDraw.Draw(overlay)
    _draw_tracked(draw, (xy[0] + SHADOW_OFFSET[0], xy[1] + SHADOW_OFFSET[1]),
                   text, font, (0, 0, 0, shadow_alpha), tracking)
    _draw_tracked(draw, xy, text, font, tuple(ink) + (255,), tracking)
    return overlay


def _mean_luma(img, box):
    left, top, right, bottom = [int(v) for v in box]
    left, top = max(left, 0), max(top, 0)
    right, bottom = min(right, img.width), min(bottom, img.height)
    if right <= left or bottom <= top:
        return 128
    region = img.crop((left, top, right, bottom)).convert("L")
    px = list(region.getdata())
    return sum(px) / len(px) if px else 128


def _tracked_width(text, font, tracking):
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    total = 0
    for ch in text:
        total += dummy.textlength(ch, font=font) + tracking
    return total - tracking if text else 0


def _draw_tracked(draw, xy, text, font, fill, tracking):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking


def label_swatch(image_path, lines, output_path, center_xy_fraction=(0.5, 0.78),
                  font_size=44, tracking=7, line_spacing=22, uppercase=True):
    """
    `lines` is a list of material names, e.g.
    ["Nero Marquina", "Fumed Oak", "Aged Brass"].
    `center_xy_fraction` positions the block's center — default sits low, over the
    blank paper card region of the flat-lay layout.
    """
    base = Image.open(image_path).convert("RGB")
    W, H = base.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    font = ImageFont.truetype(FONT_PATH, font_size)

    rendered = [ln.upper() if uppercase else ln for ln in lines]
    widths = [_tracked_width(ln, font, tracking) for ln in rendered]
    line_h = font_size + line_spacing
    total_h = len(rendered) * line_h - line_spacing

    cx, cy = center_xy_fraction[0] * W, center_xy_fraction[1] * H
    y = cy - total_h / 2

    for ln, w in zip(rendered, widths):
        x = cx - w / 2
        luma = _mean_luma(base, (x, y, x + w, y + font_size))
        ink, shadow_a, halo = pick_ink(luma)
        overlay = draw_label(overlay, (x, y), ln, font, tracking, ink, shadow_a, halo)
        y += line_h

    out = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    out.save(output_path)
    return output_path
