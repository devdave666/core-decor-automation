"""
Converts a source asset PNG into an Instagram/Facebook-safe JPEG for the
carousel pipeline. Two real constraints forced this, confirmed against Meta's
own current docs before writing any code: the content-publishing API accepts
JPEG only (a PNG image_url is rejected outright), and feed/carousel images
must fall within a 4:5 (portrait) to 1.91:1 (landscape) aspect ratio.

This project's swatch and application assets are 9:16 (1072x1920, ratio
0.5625) — built for the video reels — which is far outside that band.

Center-cropping the 9:16 source down to 4:5 was considered and rejected: c01's
swatch card carries its material-name label in roughly the bottom fifth of the
frame, close enough to where a symmetric center-crop lands that it risks
slicing through the text. Since 4:5 (0.8) is proportionally WIDER per unit
height than 9:16 (0.5625), fitting the whole source inside a 4:5 canvas means
shrinking to fit the HEIGHT and pillarboxing left/right — never cropping top
or bottom — so nothing in the original frame is ever lost. The pillarbox is
filled with a blurred, darkened extension of the same image rather than a flat
bar, the same technique Instagram's own app uses when a taller photo is
posted to feed.
"""
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

CANVAS_SIZE = (1080, 1350)  # Instagram's standard 4:5 feed/carousel size


def prepare_carousel_image(src_path, dest_path):
    canvas_w, canvas_h = CANVAS_SIZE
    src = Image.open(src_path).convert("RGB")

    # Blurred background: scale to COVER the canvas, center-crop, blur, darken
    # slightly so the sharp foreground still reads clearly against it.
    cover_scale = max(canvas_w / src.width, canvas_h / src.height)
    bg = src.resize((round(src.width * cover_scale), round(src.height * cover_scale)), Image.LANCZOS)
    left = (bg.width - canvas_w) // 2
    top = (bg.height - canvas_h) // 2
    bg = bg.crop((left, top, left + canvas_w, top + canvas_h))
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    bg = ImageEnhance.Brightness(bg).enhance(0.6)

    # Foreground: scale to FIT entirely inside the canvas. The source's own
    # height is always the limiting dimension here (4:5 is wider per unit
    # height than 9:16), so this only ever pillarboxes, never crops.
    fit_scale = min(canvas_w / src.width, canvas_h / src.height)
    fg = src.resize((round(src.width * fit_scale), round(src.height * fit_scale)), Image.LANCZOS)

    canvas = bg.copy()
    canvas.paste(fg, ((canvas_w - fg.width) // 2, (canvas_h - fg.height) // 2))

    dest_path = Path(dest_path)
    canvas.save(dest_path, "JPEG", quality=92)
    return dest_path
