"""
Asset prep for the resort-reveal-reel format (a NEW, standalone content
type, sibling to transformation_reel/ and furniture_build_reel/ -- see
llms.txt). Different narrative shape again: aerial drone-angle landscape
development -- pristine forest timelapsing into an eco-resort that stays
visually PART of the forest (dominant canopy, minimal footprint, no visible
clear-cutting) rather than replacing it. No workers, no interior, no hands
-- Dev asked specifically for drone footage + timelapse, not a build crew.

Reuses transformation_reel/furniture_build_reel's proven machinery wholesale
(gemini-2.5-flash-image on Vertex AI, the aspect-ratio config fix, the
VEO_CANVAS exact-crop fix, chained edit-forward generation, the 429 retry)
-- only the STAGE NAMES, PROMPT CONTENT, and camera framing (aerial, not
eye-level interior) are new.

`generate_forest()` (the "before" analog) is written itemized/emphatic from
the start, not a soft summary -- furniture_build_reel's generate_materials()
needed that same escalation after a real run came back under-regressed for
a built-in structure, and forest-vs-resort is an even bigger structural
delta than a bookshelf wall, so this applies that lesson proactively instead
of waiting to hit the same bug again.

Chained generation, same reasoning as the sibling formats: "after" (finished
resort, still forest-dominant) generated first from text, "forest" (zero
structures) edited from "after", then clearing/foundation/structure each
edited from the PREVIOUS stage (with "after" also passed as a second
reference) -- terrain features (the river bend, the ridge line) and camera
altitude/angle have to MATCH across every stage for Veo's conditioning to
read as one continuous place.

Usage: python resort_reveal_reel/generate_concept_frames.py <concept_id> <out_dir>
Writes <out_dir>/<concept_id>_{forest,clearing,foundation,structure,after}.png
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

STAGES = ["forest", "clearing", "foundation", "structure", "after"]

SPATIAL_RULE = (
    "This is a coherent, physically real aerial landscape: the terrain, "
    "river and tree canopy are geometrically consistent, nothing floats or "
    "intersects impossibly, and any built structure rests believably on "
    "its foundations among the trees."
)

NON_INTRUSIVE_RULE = (
    "The forest canopy remains visually dominant throughout -- any built "
    "structure is nestled UNDER or AMONG the trees, on a minimal footprint, "
    "not in a cleared area, and no bare exposed dirt or clear-cut ground is "
    "visible anywhere."
)


def generate_after(client, concept):
    prompt = (
        f"A photorealistic aerial drone photograph of {concept['location']}. "
        f"In the middle distance, a fully finished {concept['resort']}, "
        f"built from {concept['materials']}, styled in {concept['style']}. "
        f"{NON_INTRUSIVE_RULE} Golden late-afternoon light, warm light "
        f"glowing from within the structures, long soft shadows across the "
        f"canopy, real depth and atmospheric haze toward the horizon. High "
        f"oblique aerial angle, wide establishing composition. {SPATIAL_RULE} "
        f"Fully finished, high-end architectural photography, no text, no "
        f"watermark, no people, no vehicles."
    )
    print("--- generating AFTER ---")
    response = _generate_with_retry(client, [prompt])
    return _first_image(response)


def generate_forest(client, concept, after_image):
    # Itemized/emphatic from the start -- see module docstring. A soft
    # summary risked the same under-regression furniture_build_reel hit on
    # a built-in structure, and this delta (a whole resort) is bigger.
    prompt = (
        "Show this exact same aerial view, same camera angle and altitude, "
        "same terrain and river position -- but showing the land in its "
        "completely pristine, untouched natural state: absolutely NO "
        f"buildings, NO structures, NO walkways, NO {concept['resort']} in "
        "any form -- not partially built, not started, completely absent. "
        "Dense, unbroken forest canopy covers the land, no clearings, no "
        "paths, no bare ground, no construction equipment or materials "
        "anywhere. Just untouched wilderness. No people. No text. No "
        "watermark. Keep the terrain, river position and camera angle/"
        "altitude identical to the reference image so this is still "
        f"clearly recognizable as the same place. {SPATIAL_RULE}"
    )
    print("--- generating FOREST (edited from AFTER) ---")
    response = _generate_with_retry(client, [prompt, after_image])
    return _first_image(response)


INTERMEDIATE_STEPS = {
    "clearing": (
        "the very first, barely-visible sign of development: a single "
        "narrow footpath or boardwalk trail winding through the "
        "undergrowth at canopy floor level, glimpsed only faintly through "
        "gaps in the still-almost-fully-intact canopy from this aerial "
        "angle. No structures yet, no clearings, no bare dirt visible from "
        "above -- the canopy still reads as essentially untouched forest."
    ),
    "foundation": (
        "a few slender elevated stilts and platform frames just beginning "
        "to appear among the trees, still mostly concealed beneath the "
        "canopy from this aerial angle -- visibly more developed than the "
        "bare trail, but the canopy is still clearly the dominant, "
        "unbroken feature of the view."
    ),
    "structure": (
        "several resort structures now visible nestled among the trees, "
        "connected by elevated walkways, timber frames and green roofs "
        "blending with the canopy color -- visibly further along, "
        "structures now clearly present, but not yet fully finished or "
        "lit, and the canopy still dominates the aerial view far more "
        "than the built structures do."
    ),
}


def generate_intermediate(client, stage_name, concept, prev_image, after_image):
    prompt = (
        "Show this exact same aerial view, same camera angle and altitude, "
        "same terrain and river position as both reference images. This is "
        f"the NEXT step after the first reference image, showing "
        f"{INTERMEDIATE_STEPS[stage_name]} The second reference image shows "
        "where this development is ultimately headed -- move visibly one "
        f"step closer to it, not all the way there. {NON_INTRUSIVE_RULE} "
        f"{SPATIAL_RULE} No people. No text. Keep terrain, river and camera "
        "position identical to both reference images."
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
    "r01": {
        "location": "a dense tropical hillside rainforest overlooking a "
        "wide river bend, seen from a high oblique aerial drone angle",
        "resort": "elevated eco-luxury treehouse resort",
        "style": "minimal-footprint eco-architecture, quiet luxury",
        "materials": "weathered dark timber, black standing-seam metal and "
        "living green roofs, slender steel stilts, natural stone accents",
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
    images["forest"] = generate_forest(client, concept, images["after"])

    prev = images["forest"]
    for stage_name in ["clearing", "foundation", "structure"]:
        img = generate_intermediate(client, stage_name, concept, prev, images["after"])
        images[stage_name] = img
        prev = img

    for stage_name in STAGES:
        path = out_dir / f"{concept_id}_{stage_name}.png"
        images[stage_name].save(path)
        print(f"Saved {path}")


if __name__ == "__main__":
    main()
