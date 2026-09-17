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

Type treatment (matched to the Sleep Archive title-card style):
  - a soft BLURRED drop shadow, not a hard slab stroke — the thick black outline
    an earlier version used read as cheap/meme, not premium. A hairline 2px stroke
    stays only for edge definition over bright rooms.
  - straight quotes/apostrophes are curled ('It's' -> 'It’s').
  - two-line copy is BALANCED (both lines a similar length), not greedily packed.
  - digits are nudged up so Playfair's old-style figures (which sit below the
    baseline and can read as odd) align like lining figures — PIL here has no
    libraqm so the OpenType 'lnum' feature isn't available.

Legibility also leans on a soft cinematic gradient across the top of the frame
(render_gradient) — the same technique used in high-end real estate and fashion
video, not a banner hugging the text.

Text is fully static throughout — no motion, no scale change. Only WHEN each line
is visible changes; nothing about its position or appearance animates.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1080, 1920
FONT_PATH = str(Path(__file__).resolve().parent / "fonts" / "PlayfairDisplay-Bold.ttf")
FONT_VARIATION = "Bold"
FONT_SIZE = 74
LINE_SPACING = 20
STROKE_WIDTH = 2          # hairline only; the shadow does the heavy lifting now
SHADOW_BLUR = 8
SHADOW_OPACITY = 0.55
SHADOW_OFFSET = (0, 5)
DIGIT_LIFT = 0.16         # * FONT_SIZE, to fake lining figures
MARGIN_X = 90
CENTER_Y_FRACTION = 0.38  # vertical center of the whole text block, as a fraction of H
GRADIENT_HEIGHT_FRACTION = 0.62  # how far down the frame the top gradient extends
GRADIENT_MAX_OPACITY = 165  # out of 255, at the very top edge — fades to 0 below


def _load_font():
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    font.set_variation_by_name(FONT_VARIATION)
    return font


def _smart_quotes(text):
    """Curl straight quotes/apostrophes so the copy reads as typeset."""
    out, prev = [], " "
    for ch in text:
        if ch == "'":
            out.append("’")
        elif ch == '"':
            out.append("“" if prev in " \t([{" else "”")
        else:
            out.append(ch)
        prev = ch
    return "".join(out)


def _greedy_wrap(text, font, max_width, draw):
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _wrap_text(text, font, max_width, draw):
    """Greedy-wrap to learn the line count; if it lands on exactly two lines,
    rebalance them so neither is a stub. Longer copy is left greedy."""
    lines = _greedy_wrap(text, font, max_width, draw)
    if len(lines) != 2:
        return lines
    words = text.split()
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        wa, wb = draw.textlength(a, font=font), draw.textlength(b, font=font)
        if max(wa, wb) > max_width:
            continue
        score = abs(wa - wb)
        if a.rstrip().endswith((".", "?", "!", ",", ":", ";")):
            score -= max_width * 0.15
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1] if best else lines


def _measure_block(lines, font, draw):
    line_height = FONT_SIZE + LINE_SPACING
    widths = [draw.textlength(line, font=font) for line in lines]
    return max(widths, default=0), len(lines) * line_height - LINE_SPACING


def _draw_line(draw, x, y, line, font, fill, stroke_fill):
    """Centre-independent line draw that lifts digits to sit like lining figures."""
    if not any(c.isdigit() for c in line):
        draw.text((x, y), line, font=font, fill=fill,
                  stroke_width=STROKE_WIDTH, stroke_fill=stroke_fill)
        return
    cx = x
    lift = FONT_SIZE * DIGIT_LIFT
    for ch in line:
        draw.text((cx, y - (lift if ch.isdigit() else 0)), ch, font=font, fill=fill,
                  stroke_width=STROKE_WIDTH, stroke_fill=stroke_fill)
        cx += draw.textlength(ch, font=font)


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


def _with_shadow(text_layer):
    """Composite a soft blurred drop shadow under an already-rendered text layer."""
    alpha = text_layer.split()[3]
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(SHADOW_BLUR)))
    r, g, b, a = shadow.split()
    a = a.point(lambda p: int(p * SHADOW_OPACITY))
    shadow = Image.merge("RGBA", (Image.new("L", (W, H), 0),) * 3 + (a,))

    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.alpha_composite(shadow, SHADOW_OFFSET)
    out.alpha_composite(text_layer)
    return out


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

    setup = _smart_quotes(setup)
    punchline = _smart_quotes(punchline)

    setup_lines = _wrap_text(setup, font, max_width, dummy_draw)
    punchline_lines = _wrap_text(punchline, font, max_width, dummy_draw)

    _, setup_h = _measure_block(setup_lines, font, dummy_draw)
    _, punch_h = _measure_block(punchline_lines, font, dummy_draw)

    gap = FONT_SIZE // 2
    total_h = setup_h + gap + punch_h
    block_top = int(H * CENTER_Y_FRACTION - total_h / 2)

    def render_lines(lines, top):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        y = top
        for line in lines:
            line_width = draw.textlength(line, font=font)
            x = (W - line_width) / 2
            _draw_line(draw, x, y, line, font, "white", (0, 0, 0, 235))
            y += FONT_SIZE + LINE_SPACING
        return _with_shadow(layer)

    setup_img = render_lines(setup_lines, block_top)
    setup_path = Path(output_dir) / "setup.png"
    setup_img.save(setup_path)

    punch_top = block_top + setup_h + gap
    punch_img = render_lines(punchline_lines, punch_top)
    punch_path = Path(output_dir) / "punchline.png"
    punch_img.save(punch_path)

    return setup_path, punch_path
