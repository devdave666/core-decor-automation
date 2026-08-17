"""
Converts a source asset PNG into an Instagram/Facebook-safe JPEG for the
carousel pipeline. Two real constraints forced this, confirmed against Meta's
own current docs before writing any code: the content-publishing API accepts
JPEG only (a PNG image_url is rejected outright), and feed/carousel images
must fall within a 4:5 (portrait) to 1.91:1 (landscape) aspect ratio.

This project's swatch and application assets are 9:16 (1072x1920, ratio
0.5625) — built for the video reels — which is far outside that band.

FIRST VERSION of this function fit the whole 9:16 source inside a 4:5 canvas
and filled the leftover left/right space with a blurred extension of the same
image, so nothing in the original frame was ever lost. Shipped, posted for
real, and Dev's verdict on the live result was that the blurred side bars just
read as empty space — not the desired look. Replaced with a full-bleed CROP
instead: scale the source to COVER the 4:5 canvas completely and crop the
overflow, on Dev's explicit instruction that losing some top/bottom is fine
as long as the swatch card's material-name text stays visible.

Since 4:5 (0.8) is proportionally WIDER per unit height than 9:16 (0.5625),
covering a 4:5 canvas with a 9:16 source means width is always the binding
dimension — the overflow is always in HEIGHT, so the crop only ever comes off
the top and/or bottom, never the sides. `anchor_y` controls where that crop
window sits vertically (0.0 = keep the top, lose the bottom; 1.0 = keep the
bottom, lose the top; 0.5 = centered). The swatch card's material-name label
sits in roughly the bottom fifth of the frame (verified by eye on c01), so
`carousel_pipeline.py` calls this with anchor_y=1.0 for swatches — crop only
ever comes off the top, guaranteeing the label survives regardless of exactly
where it sits on any given concept. Application (room) shots have no such
constraint, so they use anchor_y=0.5 (a normal centered crop).
"""
from pathlib import Path

from PIL import Image

CANVAS_SIZE = (1080, 1350)  # Instagram's standard 4:5 feed/carousel size


def prepare_carousel_image(src_path, dest_path, anchor_y=0.5):
    canvas_w, canvas_h = CANVAS_SIZE
    src = Image.open(src_path).convert("RGB")

    cover_scale = max(canvas_w / src.width, canvas_h / src.height)
    scaled = src.resize((round(src.width * cover_scale), round(src.height * cover_scale)), Image.LANCZOS)

    overflow_y = scaled.height - canvas_h
    top = round(overflow_y * max(0.0, min(1.0, anchor_y)))
    canvas = scaled.crop((0, top, canvas_w, top + canvas_h))

    dest_path = Path(dest_path)
    canvas.save(dest_path, "JPEG", quality=92)
    return dest_path
