"""
Measures whether every labelled character on a band swatch card is actually
legible against the texture behind it. Asset-prep QA, not part of any runtime
pipeline.

WHY PER GLYPH, AND WHY THE RING: legibility fails LOCALLY. d04's chalk limestone
label scored fine on any line-level average while its final letters were
completely invisible, sitting over a near-black blotch in an otherwise pale
stone. The only metric that catches that compares one character's own pixels
against the ring of pixels immediately around it.

DO NOT use a column or line average. Averaging down a column mixes glyph, halo
and background together, which both hides real failures and invents fake ones —
it wrongly flagged AGED ELM at 43.1 on a card where the proper metric scores it
102.7 and it is plainly fine.

Contrast is a mean-luminance difference on a 0-255 scale. Below ~45 a character
is hard to read; in the single real failure so far the worst glyph scored 0.9.

    python concept_tools/check_legibility.py concept_review/d04/*_swatch.png
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from label_swatch import FONT_PATH, _tracked_width, _draw_tracked  # noqa: E402
import band_swatch as B  # noqa: E402

MIN_CONTRAST = 45
RING_SIZE = 9


def per_glyph_contrast(image_path, labels, font_size=None, tracking=None,
                        y_fraction=None):
    """
    Returns [(label, worst_contrast, worst_char)] for a three-band card, using
    band_swatch's own geometry so this measures what was actually drawn.
    """
    font_size = font_size or B.FONT_SIZE
    tracking = tracking if tracking is not None else B.TRACKING
    y_fraction = y_fraction or B.LABEL_Y_FRACTION

    img = Image.open(image_path).convert("RGB")
    grey = img.convert("L")
    W, H = img.size
    band_h = H // B.N_BANDS
    font = ImageFont.truetype(FONT_PATH, font_size)
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))

    results = []
    for i, label in enumerate(labels):
        top = i * band_h
        this_h = band_h if i < B.N_BANDS - 1 else H - top
        text = label.upper()
        w = _tracked_width(text, font, tracking)
        x = (W - w) / 2
        y = top + this_h * y_fraction - font_size / 2

        worst, worst_char = float("inf"), ""
        cx = x
        for ch in text:
            advance = measure.textlength(ch, font=font)
            if ch.strip():
                mask = Image.new("L", (W, H), 0)
                ImageDraw.Draw(mask).text((cx, y), ch, font=font, fill=255)
                core = mask.point(lambda v: 255 if v > 200 else 0)
                ring = (core.filter(ImageFilter.MaxFilter(RING_SIZE))
                             .point(lambda v: 255 if v > 128 else 0))
                core_px, ring_px = [], []
                for px in range(int(cx) - 14, int(cx + advance) + 14):
                    for py in range(int(y) - 12, int(y + font_size) + 12):
                        if 0 <= px < W and 0 <= py < H:
                            if core.getpixel((px, py)) > 128:
                                core_px.append(grey.getpixel((px, py)))
                            elif ring.getpixel((px, py)) > 128:
                                ring_px.append(grey.getpixel((px, py)))
                if core_px and ring_px:
                    c = abs(sum(core_px) / len(core_px) - sum(ring_px) / len(ring_px))
                    if c < worst:
                        worst, worst_char = c, ch
            cx += advance + tracking
        results.append((label, worst, worst_char))
    return results


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from generate_concept import CONCEPTS

    failed = False
    for path in sys.argv[1:]:
        stem = Path(path).name.replace("_swatch.png", "")
        concept = next((c for c in CONCEPTS.values() if c["stem"] == stem), None)
        if not concept:
            print(f"SKIP {path}: no CONCEPTS entry with stem {stem!r}")
            continue
        print(path)
        for label, contrast, ch in per_glyph_contrast(
                path, [b["label"] for b in concept["bands"]]):
            ok = contrast >= MIN_CONTRAST
            failed |= not ok
            print("  %-20s worst %-3r %6.1f  %s"
                  % (label, ch, contrast, "OK" if ok else "** ILLEGIBLE **"))
    sys.exit(1 if failed else 0)
