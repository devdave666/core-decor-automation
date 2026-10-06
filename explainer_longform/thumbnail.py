"""Thumbnail: before/after diagonal split from the episode's own images + a bold hook."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from render import SANS, _font

TW, TH = 1280, 720


def make_thumbnail(spec, paths, out_path):
    before = Image.open(paths["base"]).convert("RGB").resize((TW, TH), Image.LANCZOS)
    after = Image.open(paths[spec["final"]]).convert("RGB").resize((TW, TH), Image.LANCZOS)
    before = ImageEnhance.Color(before).enhance(0.5)
    before = ImageEnhance.Brightness(before).enhance(0.8)
    after = ImageEnhance.Color(after).enhance(1.2)
    after = ImageEnhance.Contrast(after).enhance(1.08)

    mask = Image.new("L", (TW, TH), 0)
    ImageDraw.Draw(mask).polygon([(0, 0), (int(TW * 0.52), 0), (int(TW * 0.40), TH), (0, TH)],
                                 fill=255)
    img = Image.composite(before, after, mask)
    d = ImageDraw.Draw(img)
    d.line([(int(TW * 0.52), 0), (int(TW * 0.40), TH)], fill=(255, 255, 255), width=10)

    small = _font(SANS, 54)
    d.text((40, 36), "BEFORE", font=small, fill=(255, 255, 255), stroke_width=6,
           stroke_fill=(0, 0, 0))
    d.text((TW - 250, 36), "AFTER", font=small, fill=(255, 214, 10), stroke_width=6,
           stroke_fill=(0, 0, 0))

    big = _font(SANS, 118)
    text = spec["thumb_text"]
    while big.getlength(text) > TW - 80 and big.size > 60:
        big = _font(SANS, big.size - 6)
    x = (TW - big.getlength(text)) / 2
    d.text((x, TH - 190), text, font=big, fill=(255, 214, 10), stroke_width=12,
           stroke_fill=(0, 0, 0))
    img.save(out_path, quality=92)
    return out_path
