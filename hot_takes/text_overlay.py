"""
Renders the "They: / Me:" style meme-text overlay as a transparent PNG, sized to
the 1080x1920 reel frame. Kept as pre-rendered PNGs composited via MoviePy rather
than MoviePy's own TextClip, which depends on ImageMagick being correctly configured
— PIL has no such dependency and gives full control over stroke/shadow styling.

Text is deliberately fully static — no slide-in, no scale, no motion of any kind.
It should never compete with the background's own motion (which now cuts between
multiple application photos in sync with the beat, not one static hold) — the text
anchors in place as a stable reference point while the world underneath changes.
A subtle dark backdrop band sits behind the text block for that reason too:
without it, legibility would vary shot to shot depending on how light or dark
whatever application photo happens to be behind it at that moment.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SIZE = 68
LINE_SPACING = 16
STROKE_WIDTH = 5
MARGIN_X = 90
BACKDROP_PAD_X = 50
BACKDROP_PAD_Y = 36
BACKDROP_OPACITY = 130  # out of 255 — subtle, not a solid black bar
CENTER_Y_FRACTION = 0.40  # vertical center of the whole text block, as a fraction of H


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


def render_text_block(setup, punchline, output_dir):
    """
    Renders the setup and punchline as TWO SEPARATE transparent PNGs at full
    canvas size, both already positioned at their final on-screen location — the
    pipeline controls reveal timing by choosing when each clip's own visibility
    starts, not by moving anything. Both share one backdrop band sized to fit
    whichever is taller when both lines are showing, so the backdrop doesn't
    resize or shift when the punchline appears — only the punchline's own text
    fades into existence within it.

    Returns (setup_png_path, punchline_png_path, backdrop_png_path).
    """
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    max_width = W - 2 * MARGIN_X

    setup_lines = _wrap_text(setup, font, max_width, dummy_draw)
    punchline_lines = _wrap_text(punchline, font, max_width, dummy_draw)

    setup_w, setup_h = _measure_block(setup_lines, font, dummy_draw)
    punch_w, punch_h = _measure_block(punchline_lines, font, dummy_draw)

    gap = FONT_SIZE // 2
    total_h = setup_h + gap + punch_h
    total_w = max(setup_w, punch_w)
    block_top = int(H * CENTER_Y_FRACTION - total_h / 2)

    # Backdrop: one static rounded band behind the whole block, sized for BOTH
    # lines from the start, so it never resizes when the punchline appears.
    backdrop = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd_draw = ImageDraw.Draw(backdrop)
    box = (
        W / 2 - total_w / 2 - BACKDROP_PAD_X,
        block_top - BACKDROP_PAD_Y,
        W / 2 + total_w / 2 + BACKDROP_PAD_X,
        block_top + total_h + BACKDROP_PAD_Y,
    )
    bd_draw.rounded_rectangle(box, radius=28, fill=(0, 0, 0, BACKDROP_OPACITY))
    backdrop_path = Path(output_dir) / "backdrop.png"
    backdrop.save(backdrop_path)

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

    return setup_path, punch_path, backdrop_path
