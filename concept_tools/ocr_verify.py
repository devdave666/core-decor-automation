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

# RAISED FROM 55 TO 85 BY DEV, on accumulated evidence across all nine d-series
# concepts. Every hit this guard has EVER produced was a false positive on macro
# texture or ornate pattern, and every one fell in a 55-83 band:
#   ('Yen.',72) ('fo,',63) ('Vik',61) ('Gar',68) ('SSS',57) ('EERE',67)
#   ('His',55) ('ty:',55) ('Cor',64) ('fen',57) ('CER',62) ('Alls',57)
#   ('N\\A',83) ('iii',56) ('AV,',61) ('EN,',71) ('ine',56) ('Re:',68)
#   ('wake',60) ('ste',66) ('pad',56) ('at;',68)
# Real composited labels scored 91-96 when this module was validated. There has
# never been a single true positive above 83, so 85 sits clear of all observed
# noise while staying well below genuine rendered text.
#
# The cost of leaving it at 55 was not theoretical: d06's room shot never passed
# once in nine attempts and every committed version was hand-placed, and d09 lost
# a whole concept — two already-passing, already-paid-for bands discarded — to
# ('wake', 60.0) on a linen weave.
#
# This does NOT weaken the standing rule that the model must never render type.
# The prompt still excludes text, the guard still runs on every image, and a
# texture that genuinely contains legible words will score far above 85 and still
# fail. If a real rendered word ever slips through below 85, lower this again and
# record the sample — that case has not been observed yet.
MIN_CONFIDENCE = 85
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
