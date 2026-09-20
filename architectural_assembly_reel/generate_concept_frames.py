"""
Frame generation for architectural_assembly_reel.

Single before/after pair, same 2-image chain as daily_villa_reel/run_daily.py:
"after" (finished villa, dusk) generated first from text as the camera/
terrain anchor, "site" (empty land) edited FROM "after" (itemized, emphatic
full removal). One fixed camera lock across both frames -- the whole
progressive build happens inside the single Veo generation in
generate_veo_clips.py, not across separate staged images.

Uses Nano Banana Pro (gemini-3-pro-image, falling back to
gemini-3.1-flash-image) via Vertex AI, same model chain as
daily_villa_reel/run_daily.py.

Usage: python architectural_assembly_reel/generate_concept_frames.py <out_dir> <concept text>
Writes <out_dir>/{site,after}.png
"""
import sys
import time
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image

PROJECT = "core-decor-657616"
LOCATION = "global"
IMG_MODELS = ["gemini-3-pro-image", "gemini-3.1-flash-image"]

MAX_RETRIES = 5
RETRY_BASE_S = 20

STAGES = ["site", "after"]

_SAFETY_OFF = [
    types.SafetySetting(category=c, threshold="OFF")
    for c in ("HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_DANGEROUS_CONTENT",
              "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_HARASSMENT")
]

# Shared architectural language so the frames (and the Veo build prompt built
# from them) describe the same finished style -- warm-minimalist luxury,
# dark timber + concrete + glass -- per Dev's assembly-reel brief.
STYLE = (
    "a warm-minimalist luxury villa built from dark timber, board-formed "
    "concrete and floor-to-ceiling glass, a flat cantilevered roofline, an "
    "infinity-edge pool, a sunken outdoor fire pit and understated modern "
    "landscaping"
)

CAMERA = "[Camera: static wide angle, ground level, fixed tripod position, locked frame]"


def _img_config(model):
    cfg = dict(response_modalities=["IMAGE"],
               image_config=types.ImageConfig(aspect_ratio="9:16", image_size="2K"),
               safety_settings=_SAFETY_OFF)
    if "flash" in model:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_level="MINIMAL")
    return types.GenerateContentConfig(**cfg)


def _first_image(resp):
    for cand in resp.candidates or []:
        for part in cand.content.parts or []:
            inl = getattr(part, "inline_data", None)
            if inl and getattr(inl, "data", None):
                return Image.open(BytesIO(inl.data)).convert("RGB")
    raise RuntimeError(f"no image in response: {resp!r}"[:600])


def _img_call(client, model, contents):
    for attempt in range(MAX_RETRIES):
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=_img_config(model))
        except genai_errors.ClientError as e:
            msg = str(e)
            if ("429" in msg or "RESOURCE_EXHAUSTED" in msg) and attempt < MAX_RETRIES - 1:
                d = RETRY_BASE_S * (2 ** attempt)
                print(f"  429, retry in {d}s")
                time.sleep(d)
                continue
            raise


class NanoBanana:
    def __init__(self):
        self.client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
        self.model = None

    def gen(self, contents):
        if self.model:
            return _first_image(_img_call(self.client, self.model, contents))
        last = None
        for m in IMG_MODELS:
            try:
                img = _first_image(_img_call(self.client, m, contents))
                print(f"  image model: {m} ({img.width}x{img.height})")
                self.model = m
                return img
            except Exception as e:  # noqa: BLE001
                print(f"  [{m}] failed: {str(e)[:200]}")
                last = e
        raise RuntimeError(f"no image model worked: {last}")


def generate_after(nb, concept):
    prompt = (
        f"Ultra-photorealistic architectural photograph, vertical 9:16 "
        f"composition, dusk / golden hour: {concept}. {STYLE.capitalize()} is "
        f"the centrepiece, fully finished and immaculately integrated into "
        f"the natural setting -- warm interior lights glowing from within, "
        f"the infinity pool filled and reflecting the sky, the fire pit lit, "
        f"landscaping mature and settled. {CAMERA} Cinematic, crisp, high "
        f"dynamic range, magazine real-estate quality. No text, no people, "
        f"no watermark."
    )
    print("--- nano banana: AFTER (finished villa, dusk) ---")
    return nb.gen(prompt)


def generate_site(nb, after_img):
    prompt = (
        "Show this exact same landscape and scenery -- identical camera "
        "angle, identical terrain, horizon, mountains, sky, weather and "
        "light -- but COMPLETELY REMOVE the villa and every man-made trace: "
        "no building, no pool, no fire pit, no terraces, no driveway, no "
        "retaining walls, no landscaping, no construction, nothing built at "
        "all. Leave only raw untouched natural land where the house was -- "
        "bare earth, rock, native grass and the natural contour of the "
        f"ground. Pristine, empty site. {CAMERA} Everything else in the "
        "frame stays exactly the same."
    )
    print("--- nano banana: SITE (empty land, edited from after) ---")
    return nb.gen([prompt, after_img])


def generate_all(concept, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    nb = NanoBanana()

    after_img = generate_after(nb, concept)
    site_img = generate_site(nb, after_img)

    images = {"after": after_img, "site": site_img}
    for stage_name in STAGES:
        path = out_dir / f"{stage_name}.png"
        images[stage_name].save(path)
        print(f"Saved {path}")
    return {stage: out_dir / f"{stage}.png" for stage in STAGES}


def main():
    if len(sys.argv) != 3:
        print("Usage: generate_concept_frames.py <out_dir> <concept text>")
        raise SystemExit(1)
    out_dir, concept = Path(sys.argv[1]), sys.argv[2]
    generate_all(concept, out_dir)


if __name__ == "__main__":
    main()
