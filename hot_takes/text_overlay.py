"""
Renders the "They: / Me:" style meme-text overlay as a transparent PNG, sized to
the 1080x1920 reel frame. Kept as pre-rendered PNGs composited via MoviePy rather
than MoviePy's own TextClip, which depends on ImageMagick being correctly configured
— PIL has no such dependency and gives full control over stroke/shadow styling.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SIZE = 64
LINE_SPACING = 14
STROKE_WIDTH = 6
MARGIN_X = 80
TOP_Y = 220  # where the first line's top edge sits — upper third, clear of TikTok/IG UI


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


def render_line_png(text, output_path, y_offset=0):
    """
    Renders ONE line of meme text (word-wrapped if needed) as a transparent PNG at
    full 1080x1920 canvas size, positioned at TOP_Y + y_offset. Returns the path.
    Each line is its own PNG so the pipeline can control exactly when each one
    appears (the "They:" / "Me:" reveal timing) independently.
    """
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

    max_width = W - 2 * MARGIN_X
    lines = _wrap_text(text, font, max_width, draw)

    y = TOP_Y + y_offset
    for line in lines:
        line_width = draw.textlength(line, font=font)
        x = (W - line_width) / 2
        # White fill, black stroke — the standard meme-text convention, readable
        # over any background regardless of how light or dark the photo is.
        draw.text((x, y), line, font=font, fill="white",
                   stroke_width=STROKE_WIDTH, stroke_fill="black")
        y += FONT_SIZE + LINE_SPACING

    img.save(output_path)
    return output_path, y - TOP_Y  # also return total height used, for stacking
