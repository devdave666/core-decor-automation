"""
Renders the "They: / Me:" style text overlay as transparent PNGs, sized to the
1080x1920 reel frame. Kept as pre-rendered PNGs composited via MoviePy rather than
MoviePy's own TextClip, which depends on ImageMagick being correctly configured —
PIL has no such dependency and gives full control over font weight and styling.

Font: Playfair Display (Bold variation of the variable font), bundled directly in
fonts/ rather than relying on whatever's installed on the system — a GitHub Actions
runner won't have this by default, and system fallback fonts (DejaVu Sans, the
original choice) read as generic/utilitarian, not the "good, luxurious" look this
was asked for. Playfair Display is a serif long associated with editorial/fashion/
luxury branding, which matches Core Decor's own swatch-card typography elsewhere
in this pipeline rather than introducing an unrelated new visual language.

Legibility: NO boxed backdrop — an earlier version used a solid semi-transparent
rounded rectangle behind the text, which read as cheap rather than premium. In its
place, a soft cinematic gradient across the top portion of the frame (dark at the
very top, fading to fully transparent by the point text ends) — the same technique
used in high-end real estate and fashion video, not a banner hugging the text.

Text is fully static throughout — no motion, no scale change. Only WHEN each line
is visible changes; nothing about its position or appearance animates.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FONT_PATH = str(Path(__file__).resolve().parent / "fonts" / "PlayfairDisplay-Bold.ttf")
FONT_VARIATION = "Bold"
FONT_SIZE = 74
LINE_SPACING = 20
STROKE_WIDTH = 4
MARGIN_X = 90
CENTER_Y_FRACTION = 0.38  # vertical center of the whole text block, as a fraction of H
GRADIENT_HEIGHT_FRACTION = 0.62  # how far down the frame the top gradient extends
GRADIENT_MAX_OPACITY = 165  # out of 255, at the very top edge — fades to 0 below


def _load_font():
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    font.set_variation_by_name(FONT_VARIATION)
    return font


def _wrap_text(text, font, max_width, draw):
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _measure_block(lines, font, draw):
    line_height = FONT_SIZE + LINE_SPACING
    widths = [draw.textlength(line, font=font) for line in lines]
    return max(widths, default=0), len(lines) * line_height - LINE_SPACING


def render_gradient(output_dir):
    """
    A soft top-down darkening, not a box — full frame width, fading from
    GRADIENT_MAX_OPACITY at the very top edge to fully transparent by
    GRADIENT_HEIGHT_FRACTION down the frame. Static for the whole video; it isn't
    tied to text position, so it never needs to resize or move either.
    """
    grad = Image.new("L", (1, H), 0)
    gradient_px = int(H * GRADIENT_HEIGHT_FRACTION)
    for y in range(gradient_px):
        alpha = int(GRADIENT_MAX_OPACITY * (1 - y / gradient_px))
        grad.putpixel((0, y), alpha)
    alpha_mask = grad.resize((W, H))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    overlay.putalpha(alpha_mask)
    path = Path(output_dir) / "gradient.png"
    overlay.save(path)
    return path


def render_text_block(setup, punchline, output_dir):
    """
    Renders the setup and punchline as TWO SEPARATE transparent PNGs at full
    canvas size, both already positioned at their final on-screen location — the
    pipeline controls reveal timing by choosing when each clip's own visibility
    starts, not by moving anything. Returns (setup_png_path, punchline_png_path).
    """
    font = _load_font()
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    max_width = W - 2 * MARGIN_X

    setup_lines = _wrap_text(setup, font, max_width, dummy_draw)
    punchline_lines = _wrap_text(punchline, font, max_width, dummy_draw)

    _, setup_h = _measure_block(setup_lines, font, dummy_draw)
    _, punch_h = _measure_block(punchline_lines, font, dummy_draw)

    gap = FONT_SIZE // 2
    total_h = setup_h + gap + punch_h
    block_top = int(H * CENTER_Y_FRACTION - total_h / 2)

    def render_lines(lines, top):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        y = top
        for line in lines:
            line_width = draw.textlength(line, font=font)
            x = (W - line_width) / 2
            draw.text((x, y), line, font=font, fill="white",
                       stroke_width=STROKE_WIDTH, stroke_fill="black")
            y += FONT_SIZE + LINE_SPACING
        return img

    setup_img = render_lines(setup_lines, block_top)
    setup_path = Path(output_dir) / "setup.png"
    setup_img.save(setup_path)

    punch_top = block_top + setup_h + gap
    punch_img = render_lines(punchline_lines, punch_top)
    punch_path = Path(output_dir) / "punchline.png"
    punch_img.save(punch_path)

    return setup_path, punch_path
