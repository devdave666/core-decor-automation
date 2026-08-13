"""
Composes the THREE-BAND palette card — the format this project pivoted to, copied
in structure from the reference reel: three full-width horizontal bands of real
material texture, each labelled with its material/colour name in wide-tracked
caps, ink flipping light or dark per band.

This REPLACES the earlier flat-lay swatch layout (physical samples arranged on
concrete with a torn paper card) for the new `d__` series. The original `c01`-`c50`
flat-lay assets are untouched and still drive the original pipeline — see the
naming convention section in llms.txt.

WHY THE BANDS ARE STACKED IN CODE RATHER THAN GENERATED AS ONE IMAGE:
crisp, exact horizontal thirds with hard boundaries is precisely the kind of
geometry image models render inconsistently. Generating three independent texture
tiles and stacking them programmatically makes the band boundaries exact by
construction, and each tile is a simpler prompt so the texture itself comes out
better. Same principle as never letting the model render the type: if code can
guarantee it, don't ask the model to.
"""

from pathlib import Path
from PIL import Image, ImageFont

from label_swatch import (
    FONT_PATH, _mean_luma, _tracked_width, pick_ink, draw_label,
)

W, H = 1080, 1920
N_BANDS = 3
FONT_SIZE = 52
TRACKING = 13          # wide tracking is the luxury/editorial convention
LABEL_Y_FRACTION = 0.5  # vertical position of the label within its own band


def _fill_band(texture_path, band_w, band_h):
    """Center-crop-to-fill a texture into exact band dimensions, no stretching."""
    img = Image.open(texture_path).convert("RGB")
    scale = max(band_w / img.width, band_h / img.height)
    img = img.resize((max(int(img.width * scale), band_w),
                       max(int(img.height * scale), band_h)), Image.LANCZOS)
    left = (img.width - band_w) // 2
    top = (img.height - band_h) // 2
    return img.crop((left, top, left + band_w, top + band_h))


def compose_band_swatch(textures, labels, output_path, font_size=FONT_SIZE,
                         tracking=TRACKING, uppercase=True):
    """
    `textures` and `labels` are parallel lists of three items, top band first:
        textures = [stone_tile, wood_tile, plaster_tile]
        labels   = ["Nero Marquina", "Fumed Oak", "Limewash"]
    """
    if len(textures) != N_BANDS or len(labels) != N_BANDS:
        raise ValueError(f"need exactly {N_BANDS} textures and {N_BANDS} labels")

    band_h = H // N_BANDS
    canvas = Image.new("RGB", (W, H))
    # Any rounding remainder goes to the last band so the canvas is exactly filled
    tops = []
    for i in range(N_BANDS):
        top = i * band_h
        this_h = band_h if i < N_BANDS - 1 else H - top
        canvas.paste(_fill_band(textures[i], W, this_h), (0, top))
        tops.append((top, this_h))

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    font = ImageFont.truetype(FONT_PATH, font_size)

    for (top, this_h), label in zip(tops, labels):
        text = label.upper() if uppercase else label
        w = _tracked_width(text, font, tracking)
        x = (W - w) / 2
        y = top + this_h * LABEL_Y_FRACTION - font_size / 2
        # Sample only the pixels actually behind THIS line, so each band picks its
        # own ink independently — this is what lets one near-black band and one
        # pale band coexist without hand-tuning either. The mean is only a
        # starting point; draw_label's contrasting halo is what covers the case
        # where a single line straddles both light and dark ground.
        luma = _mean_luma(canvas, (x, y, x + w, y + font_size))
        ink, shadow_a, halo = pick_ink(luma)
        overlay = draw_label(overlay, (x, y), text, font, tracking, ink, shadow_a, halo)

    out = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    out.save(output_path)
    return output_path
