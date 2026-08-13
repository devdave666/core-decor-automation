"""
Confirms a generated swatch texture is genuinely free of model-rendered text
BEFORE real labels get composited on top of it (see label_swatch.py for why).

A generation prompt that excludes text usually works but is not a guarantee —
this is the check, not the hope. Run it on every new texture; treat any hit as
a reason to regenerate, not to paint over.

PSM 11 IS LOAD-BEARING — do not drop it back to the default. Tesseract's default
page segmentation (PSM 3, "auto") assumes a document-like layout and found
ZERO text on a real 1080x1920 swatch card whose three material names were plainly
legible to the eye — a silent false negative that would have made this entire
check useless, passing every texture unconditionally. PSM 11 ("sparse text")
is built for exactly this case: a little text scattered over a busy photographic
background. On the same image it detected every word at 91-96% confidence.
Verified in both directions: it fails a labelled swatch and passes a text-free
room photo.
"""

import sys
from PIL import Image

MIN_CONFIDENCE = 55
MIN_CHARS = 3
TESSERACT_CONFIG = "--psm 11"


def find_text(image_path, min_confidence=MIN_CONFIDENCE, min_chars=MIN_CHARS):
    # Imported here rather than at module scope so that importing this module for
    # its constants does not require tesseract to be installed. The runtime
    # behaviour of the check itself is unchanged — PSM 11 still applies, see above.
    import pytesseract

    img = Image.open(image_path)
    data = pytesseract.image_to_data(img, config=TESSERACT_CONFIG,
                                      output_type=pytesseract.Output.DICT)
    hits = []
    for txt, conf in zip(data["text"], data["conf"]):
        txt = (txt or "").strip()
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            continue
        if len(txt) >= min_chars and conf >= min_confidence and any(c.isalnum() for c in txt):
            hits.append((txt, conf))
    return hits


if __name__ == "__main__":
    for path in sys.argv[1:]:
        hits = find_text(path)
        if hits:
            print(f"FAIL {path}: model-rendered text detected -> {hits}")
        else:
            print(f"CLEAN {path}: no text detected")
