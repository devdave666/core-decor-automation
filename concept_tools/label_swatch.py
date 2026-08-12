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
  cheap. Legibility comes instead from adaptive ink plus one subtle offset shadow.
- ADAPTIVE INK: the mean luminance of the actual pixels behind each text line is
  sampled, and the ink switches to a warm off-white over dark ground or a deep
  espresso over light ground. This is what lets one code path label both a near
  black marble band and a pale limestone band without hand-tuning either.
- Wide letterspacing (tracking), all caps — the luxury/editorial convention seen
  in the reference material. PIL has no native tracking, so glyphs are drawn one
  at a time with an explicit advance.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = str(Path(__file__).resolve().parent / "fonts" / "FrysBaskerville.ttf")

INK_LIGHT = (242, 236, 226)   # warm off-white, for dark ground
INK_DARK = (58, 44, 36)       # deep espresso, for light ground
LUMA_THRESHOLD = 118          # below this mean luminance -> use light ink
SHADOW_OFFSET = (2, 3)
SHADOW_OPACITY_LIGHT_INK = 110  # shadow under pale ink on dark ground
SHADOW_OPACITY_DARK_INK = 70    # softer under dark ink on light ground


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
    draw = ImageDraw.Draw(overlay)
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
        if luma < LUMA_THRESHOLD:
            ink, shadow_a = INK_LIGHT, SHADOW_OPACITY_LIGHT_INK
        else:
            ink, shadow_a = INK_DARK, SHADOW_OPACITY_DARK_INK
        _draw_tracked(draw, (x + SHADOW_OFFSET[0], y + SHADOW_OFFSET[1]), ln, font,
                       (0, 0, 0, shadow_a), tracking)
        _draw_tracked(draw, (x, y), ln, font, ink + (255,), tracking)
        y += line_h

    out = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    out.save(output_path)
    return output_path
