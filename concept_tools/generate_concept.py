"""
Generates ONE three-band concept pair (band-swatch card + matching room shot)
via the BFL FLUX API, then labels the card and commits nothing — the calling
workflow handles git.

RUNS INSIDE GITHUB ACTIONS BY DESIGN. BFL_API_KEY lives in GitHub Actions
secrets, and that API is write-only — a value can be set but never read back,
and there is no local copy. Rather than move the secret out of the secret store
just so it could be used locally, generation runs where the secret already is
and commits the finished images back to the repo for review. Trigger via
workflow_dispatch on generate-concept.yml.

BFL API specifics worth not rediscovering:
- Auth header is `x-key`, NOT `Authorization: Bearer`.
- POST returns {id, polling_url}; you must poll the RETURNED polling_url, not a
  URL you construct yourself — the global endpoint load-balances across clusters.
- Poll status values are Pending / Ready / Error.
- The result URL EXPIRES IN 10 MINUTES. Download bytes immediately on Ready;
  never store or reuse the URL.
- Dimensions should be multiples of 32.
"""

import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from band_swatch import compose_band_swatch  # noqa: E402
from ocr_verify import find_text  # noqa: E402

API_BASE = "https://api.bfl.ai/v1"
MODEL = "flux-2-pro"
FINAL_W, FINAL_H = 1080, 1920
BAND_W, BAND_H = 1024, 608      # ~1080x640 band aspect, multiples of 32
ROOM_W, ROOM_H = 1088, 1920     # ~9:16, multiples of 32

NO_TEXT = (
    " Absolutely no text, no labels, no lettering, no words, no writing, no captions, "
    "no watermarks, no logos, no signage, no numbers anywhere in the image."
)

QUALITY = (
    " Shot on Hasselblad H6D-100c, f/8, ISO 50, maximum depth of field, tack-sharp "
    "focus across the entire frame, high micro-contrast, crisp surface detail, no "
    "lens noise, no motion blur, no CGI smoothness."
)


def _generate(prompt, width, height, label):
    key = os.environ.get("BFL_API_KEY")
    if not key:
        raise SystemExit("BFL_API_KEY not set in environment")
    headers = {"x-key": key, "Content-Type": "application/json", "accept": "application/json"}

    r = requests.post(f"{API_BASE}/{MODEL}",
                       headers=headers,
                       json={"prompt": prompt, "width": width, "height": height,
                             "output_format": "png"},
                       timeout=60)
    if r.status_code >= 400:
        raise SystemExit(f"[{label}] submit failed {r.status_code}: {r.text[:500]}")
    body = r.json()
    polling_url = body.get("polling_url")
    if not polling_url:
        raise SystemExit(f"[{label}] no polling_url in response: {body}")
    print(f"[{label}] submitted id={body.get('id')}", flush=True)

    for attempt in range(120):
        time.sleep(3)
        p = requests.get(polling_url, headers=headers, timeout=30)
        if p.status_code >= 400:
            print(f"[{label}] poll {p.status_code}: {p.text[:200]}", flush=True)
            continue
        pb = p.json()
        status = pb.get("status")
        if status == "Ready":
            result = pb.get("result") or {}
            url = result.get("sample")
            if not url:
                raise SystemExit(f"[{label}] Ready but no sample url: {pb}")
            # URL expires in 10 minutes — fetch bytes now, never cache the URL.
            img = requests.get(url, timeout=180).content
            print(f"[{label}] ready after {attempt + 1} polls, {len(img)} bytes", flush=True)
            return img
        if status in ("Error", "Failed"):
            raise SystemExit(f"[{label}] generation failed: {pb}")
    raise SystemExit(f"[{label}] timed out waiting for Ready")


def _save(img_bytes, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(img_bytes)
    return path


def _fit_final(path):
    """Normalize to exactly 1080x1920 by center-crop-to-fill (never stretch)."""
    img = Image.open(path).convert("RGB")
    scale = max(FINAL_W / img.width, FINAL_H / img.height)
    img = img.resize((max(int(img.width * scale), FINAL_W),
                       max(int(img.height * scale), FINAL_H)), Image.LANCZOS)
    left = (img.width - FINAL_W) // 2
    top = (img.height - FINAL_H) // 2
    img.crop((left, top, left + FINAL_W, top + FINAL_H)).save(path)
    return path


def _assert_clean(path, label):
    hits = find_text(path)
    if hits:
        raise SystemExit(
            f"[{label}] OCR found model-rendered text {hits} in {path}. "
            f"Regenerate — do not label over it."
        )
    print(f"[{label}] OCR clean", flush=True)


def build_concept(concept, out_dir):
    stem = concept["stem"]
    out_dir = Path(out_dir)
    tmp = out_dir / "_textures"
    tmp.mkdir(parents=True, exist_ok=True)

    band_paths = []
    for i, band in enumerate(concept["bands"], start=1):
        label = f"{stem} band{i}"
        prompt = (
            f"Extreme close-up flat straight-on macro photograph of {band['texture']}. "
            "The material fills the entire frame edge to edge as one flat even surface, "
            "perfectly parallel to the camera, zero perspective, zero objects or props, "
            "no visible edges, borders, corners or background. Even studio illumination "
            "with subtle low-angle raking light revealing the surface relief. "
            "Deep, rich, saturated, moody dark colour grade." + QUALITY + NO_TEXT
        )
        p = _save(_generate(prompt, BAND_W, BAND_H, label), tmp / f"{stem}_band{i}.png")
        _assert_clean(p, label)
        band_paths.append(p)

    swatch_path = out_dir / f"{stem}_swatch.png"
    compose_band_swatch(band_paths, [b["label"] for b in concept["bands"]], swatch_path)
    _fit_final(swatch_path)
    print(f"[{stem}] band swatch composed -> {swatch_path}", flush=True)

    room_label = f"{stem} room"
    room_prompt = (
        f"Straight-on eye-level architectural interior photograph of {concept['room']}. "
        "Perfectly vertical architectural grid alignment, zero wide-angle lens distortion. "
        f"The space applies exactly these materials: {concept['materials_sentence']} "
        "Dual-source lighting: high-contrast directional natural daylight through large "
        "windows combined with warm 2700K ambient glow from wall sconces and concealed "
        "LED cove strips. Deep moody shadow depth with crisp specular highlights on stone "
        "edges, glass and metal. Bespoke millwork, integrated ceiling coves, shadow-line "
        "baseboards, photorealistic spatial depth. Rich, dark, saturated luxury colour "
        "grade." + QUALITY + NO_TEXT
    )
    app_path = _save(_generate(room_prompt, ROOM_W, ROOM_H, room_label),
                      out_dir / f"{stem}_app.png")
    _assert_clean(app_path, room_label)
    _fit_final(app_path)
    print(f"[{stem}] room shot -> {app_path}", flush=True)
    return swatch_path, app_path


CONCEPTS = {
    "d01": {
        "stem": "d01_lib_oxblood",
        "room": "a private residential library and reading room",
        "bands": [
            {"label": "Nero Marquina",
             "texture": "honed matte deep black Nero Marquina marble with fine crisp "
                         "white mineral veining and visible stone pores"},
            {"label": "Fumed Oak",
             "texture": "fumed smoked oak timber in deep chocolate brown with pronounced "
                         "open grain, deep timber fibres and a satin hand-oiled finish"},
            {"label": "Oxblood Velvet",
             "texture": "heavyweight deep oxblood burgundy cotton velvet with dense short "
                         "pile, soft sheen and subtle directional nap"},
        ],
        "materials_sentence": (
            "honed black Nero Marquina marble on the fireplace surround and hearth, "
            "floor-to-ceiling fumed smoked oak panelling and bookshelves in deep chocolate "
            "brown, deep oxblood burgundy velvet upholstery on the seating, and aged "
            "unlacquered brass picture lights and hardware."
        ),
    },
}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "d01"
    out = sys.argv[2] if len(sys.argv) > 2 else f"concept_review/{which}"
    if which not in CONCEPTS:
        raise SystemExit(f"unknown concept {which}; known: {list(CONCEPTS)}")
    build_concept(CONCEPTS[which], out)
