"""
Asset prep for the stained-glass-reel format (a NEW, standalone content
type -- see llms.txt). Deliberately different scope from every sibling
format: Dev asked for a NARROW subject (one small architectural detail,
not a whole room or a whole piece of furniture) and for the artisan's
movements to read as slow and deliberate, not rushed. A single leaded
stained-glass window panel being crafted and fitted into a small arched
nook -- tightly, intimately framed throughout, camera never pulling back
to show a wider room.

Reuses transformation_reel's proven machinery wholesale (gemini-2.5-flash-
image on Vertex AI, the aspect-ratio config fix, the VEO_CANVAS exact-crop
fix, chained edit-forward generation, the 429 retry) -- only the STAGE
NAMES and PROMPT CONTENT are new. `generate_raw()` (the "before" analog)
is written itemized/emphatic from the start, applying the lesson every
sibling format eventually needed the hard way: a soft "nothing built yet"
instruction isn't forceful enough on its own, only an absolute-baseline
description reliably works.

Chained generation: "after" (finished, sunlit panel) generated first from
text, "raw" (plain glass + workbench materials) edited from "after", then
assembling/fitting edited forward from the previous stage (with "after"
also passed as a target reference).

Usage: python stained_glass_reel/generate_concept_frames.py <concept_id> <out_dir>
Writes <out_dir>/<concept_id>_{raw,assembling,fitting,after}.png
"""
import sys
import time
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image, ImageOps

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "us-central1"
MODEL = "gemini-2.5-flash-image"

VEO_CANVAS = (720, 1280)
MAX_RETRIES = 5
RETRY_BASE_DELAY_S = 20

IMAGE_CONFIG = types.GenerateContentConfig(
    image_config=types.ImageConfig(aspect_ratio="9:16")
)

STAGES = ["raw", "assembling", "fitting", "after"]

SPATIAL_RULE = (
    "This is a coherent, physically real close-up space: every glass "
    "piece, tool and object rests believably on its surface, nothing "
    "floats or intersects, and the window frame is geometrically "
    "consistent throughout."
)

TIGHT_FRAMING_RULE = (
    "Extremely tight, intimate framing -- only the small arched window "
    "opening, the immediately adjacent wall, and a small workbench are "
    "visible. No wide room view, no other walls, no furniture beyond the "
    "workbench -- this is a close-up detail shot, not an establishing "
    "shot."
)


def generate_after(client, concept):
    prompt = (
        f"An extreme close-up photorealistic photograph of {concept['nook']}. "
        f"A fully finished {concept['piece']}, {concept['description']}. "
        f"Warm late-afternoon sunlight streams directly through the glass, "
        f"casting vivid jewel-colored light and shadow patterns across the "
        f"adjacent wall and floor. {TIGHT_FRAMING_RULE} {SPATIAL_RULE} "
        f"Real depth, photorealistic, no text, no watermark, no people."
    )
    print("--- generating AFTER ---")
    response = _generate_with_retry(client, [prompt])
    return _first_image(response)


def generate_raw(client, concept, after_image):
    # Itemized/emphatic from the start -- every sibling format eventually
    # needed this escalation after a soft instruction came back under-
    # regressed. Applying the lesson proactively here.
    prompt = (
        "Show this exact same extremely tight close-up framing, same "
        "arched window opening, same wall and workbench position -- but "
        "the window must show ONLY a plain, unremarkable pane of clear "
        "glass. Absolutely NO stained glass, no color, no lead came, no "
        f"pattern of any kind -- none of the finished {concept['piece']} "
        "exists yet in any form, not partially made, not started, "
        "completely absent. On the small workbench beside the window are "
        f"only the raw materials for it: {concept['raw_materials']}. No "
        f"text or logos visible on anything. {TIGHT_FRAMING_RULE} "
        f"{SPATIAL_RULE} No people. No text. Keep the window opening, "
        "wall and workbench position identical to the reference image so "
        "this is still clearly the same close-up view."
    )
    print("--- generating RAW (edited from AFTER) ---")
    response = _generate_with_retry(client, [prompt, after_image])
    return _first_image(response)


# Each step is ONE slow, deliberate, single action -- Dev asked explicitly
# for the artisan's pace to read as unhurried, not rushed.
INTERMEDIATE_STEPS = {
    "assembling": (
        "the artisan slowly and carefully soldering one seam of lead came "
        "on the workbench, unhurried and precise -- a partial section of "
        "the glass panel has come together, jewel-toned pieces held in "
        "their lead framework, but it is visibly incomplete. The window "
        "itself is still plain clear glass, nothing installed yet."
    ),
    "fitting": (
        "the artisan slowly and carefully lifting the now-complete "
        "stained-glass panel with both hands and easing it into the "
        "window frame -- the panel is now resting in the opening, "
        "unhurried and deliberate, but not yet fully seated or sealed "
        "into place, no sunlight glow through it yet."
    ),
}


def generate_intermediate(client, stage_name, concept, prev_image, after_image):
    prompt = (
        "Show this exact same tight close-up framing, same window opening "
        "and wall position as both reference images. This is the NEXT "
        f"step after the first reference image, showing {INTERMEDIATE_STEPS[stage_name]} "
        "The second reference image shows where this is ultimately headed "
        f"-- move visibly one step closer to it, not all the way there. "
        f"{TIGHT_FRAMING_RULE} {SPATIAL_RULE} No text. Keep the window "
        "opening, wall and workbench position identical to both reference "
        "images."
    )
    print(f"--- generating {stage_name.upper()} (edited from previous stage) ---")
    response = _generate_with_retry(client, [prompt, prev_image, after_image])
    return _first_image(response)


def _generate_with_retry(client, contents):
    for attempt in range(MAX_RETRIES):
        try:
            return client.models.generate_content(
                model=MODEL, contents=contents, config=IMAGE_CONFIG
            )
        except genai_errors.ClientError as e:
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            if not is_rate_limit or attempt == MAX_RETRIES - 1:
                raise
            delay = RETRY_BASE_DELAY_S * (2 ** attempt)
            print(f"  429 rate-limited, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})...")
            time.sleep(delay)


def _first_image(response):
    for candidate in response.candidates:
        for part in candidate.content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                img = Image.open(BytesIO(inline.data)).convert("RGB")
                return ImageOps.fit(img, VEO_CANVAS, method=Image.LANCZOS, centering=(0.5, 0.5))
    raise RuntimeError(f"No inline image data in response: {response!r}"[:1000])


CONCEPTS = {
    "g01": {
        "nook": "a small arched window opening in an otherwise plain "
        "interior wall",
        "piece": "leaded stained-glass window panel",
        "description": "in rich jewel tones -- deep cobalt blue, amber "
        "and ruby red glass pieces arranged in an intricate floral "
        "medallion pattern, dark patinated lead came holding every piece",
        "raw_materials": "hand-cut pieces of jewel-toned glass (cobalt "
        "blue, amber, ruby red) laid out on a paper pattern, coiled lead "
        "came strips, a soldering iron, a glass cutter, a small tin of "
        "flux",
    },
}


def main():
    if len(sys.argv) != 3:
        print("Usage: generate_concept_frames.py <concept_id> <out_dir>")
        raise SystemExit(1)
    concept_id, out_dir = sys.argv[1], Path(sys.argv[2])
    concept = CONCEPTS[concept_id]
    out_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)

    images = {}
    images["after"] = generate_after(client, concept)
    images["raw"] = generate_raw(client, concept, images["after"])

    prev = images["raw"]
    for stage_name in ["assembling", "fitting"]:
        img = generate_intermediate(client, stage_name, concept, prev, images["after"])
        images[stage_name] = img
        prev = img

    for stage_name in STAGES:
        path = out_dir / f"{concept_id}_{stage_name}.png"
        images[stage_name].save(path)
        print(f"Saved {path}")


if __name__ == "__main__":
    main()
