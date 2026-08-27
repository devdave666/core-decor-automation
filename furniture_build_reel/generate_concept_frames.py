"""
Asset prep for the furniture-build-reel format (a NEW, standalone content type,
sibling to transformation_reel/ -- see llms.txt). Different narrative shape:
ONE person hand-building a single furniture piece from raw materials to a
finished, LED-lit reveal, not a crew renovating a whole room. Inspired by a
Dev-supplied reference (a TikTok pallet-wood canopy-bed build) but deliberately
different in the specific piece/materials, not a copy of it.

Reuses transformation_reel/generate_concept_frames.py's proven machinery
wholesale (gemini-2.5-flash-image on Vertex AI, the aspect-ratio config fix,
the VEO_CANVAS exact-crop fix, chained edit-forward generation, the 429 retry)
rather than re-deriving any of it -- only the STAGE NAMES and PROMPT CONTENT
are new.

Chained generation, same reasoning as transformation_reel: "after" (finished,
LED-lit) generated first from text, "materials" (raw/unbuilt) edited from
"after", then framing/building/lighting each edited from the PREVIOUS stage
(with "after" also passed as a second reference so intermediate stages
visibly progress toward it) -- wall, window and camera framing have to MATCH
across every stage for Veo's first/last-frame conditioning to read as one
continuous space.

Usage: python furniture_build_reel/generate_concept_frames.py <concept_id> <out_dir>
Writes <out_dir>/<concept_id>_{materials,framing,building,lighting,after}.png
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

# Same exact-crop fix as transformation_reel -- Veo's real output canvas for
# aspect_ratio="9:16" (confirmed via ffprobe), not gemini-2.5-flash-image's
# own slightly-different 768x1344.
VEO_CANVAS = (720, 1280)
MAX_RETRIES = 5
RETRY_BASE_DELAY_S = 20

IMAGE_CONFIG = types.GenerateContentConfig(
    image_config=types.ImageConfig(aspect_ratio="9:16")
)

STAGES = ["materials", "framing", "building", "lighting", "after"]

SPATIAL_RULE = (
    "The room is a coherent, physically real 3D space: every board, bracket "
    "and object is fully separated from every other by visible floor or "
    "wall, nothing floats or intersects, and the finished piece rests "
    "believably on its supports."
)


def generate_after(client, concept):
    prompt = (
        f"A photorealistic interior photograph of {concept['room']}. A fully "
        f"finished {concept['piece']}, built from {concept['materials']}, "
        f"styled in {concept['style']}. The piece is fully assembled and "
        f"finished, a warm LED light strip glows along one of its edges, "
        f"washing nearby surfaces in soft warm light. Warm late-afternoon "
        f"light through the window mixes with the LED glow, shadows holding "
        f"real detail, no blown highlights. Eye-level three-quarter view, "
        f"real depth with objects in the near field. {SPATIAL_RULE} Fully "
        f"finished, high-end, magazine-quality real estate photography, no "
        f"text, no watermark, no people."
    )
    print("--- generating AFTER ---")
    response = _generate_with_retry(client, [prompt])
    return _first_image(response)


def generate_materials(client, concept, after_image):
    # Forceful/itemized on purpose -- a first pass on a built-IN (wall-
    # mounted millwork) concept came back with the wall still almost fully
    # built, just with a few raw-material props added on top, because a
    # softer "with none of the piece built yet" instruction wasn't strong
    # enough to make the model actually remove existing built-in structure
    # via editing (freestanding-furniture concepts reverted fine; built-in
    # wall units didn't). Same escalation shape as transformation_reel's
    # generate_before() needing itemized decay instead of a mild summary.
    prompt = (
        "Show this exact same room, same camera angle, same wall and window "
        "position -- but the wall must be shown COMPLETELY BARE and EMPTY: "
        "no shelving, no millwork, no framework, no panels, nothing at all "
        "attached to or built into the wall. It is a plain, empty painted "
        f"wall. NONE of the {concept['piece']} exists yet in any form -- "
        "not partially built, not started, completely absent. All that is "
        "in the room are the raw, unassembled materials for it, sitting in "
        f"a loose, disorganized pile on the bare floor -- {concept['raw_materials']}, "
        "plus a cordless drill, a box of screws and a tape measure laid out "
        "nearby. No text or logos visible on any packaging or boxes. The "
        "floor is otherwise empty, warm daylight through the window. "
        f"{SPATIAL_RULE} No people. No text. Keep the room's proportions, "
        "wall and window position identical to the reference image so the "
        "space is still clearly recognizable as the same room -- but the "
        "wall itself must be completely empty and unbuilt, not partially "
        "finished."
    )
    print("--- generating MATERIALS (edited from AFTER) ---")
    response = _generate_with_retry(client, [prompt, after_image])
    return _first_image(response)


INTERMEDIATE_STEPS = {
    "framing": (
        "a carpenter mounting the structural brackets/frame to the wall with "
        "a cordless drill and fitting the first support boards across them -- "
        "just the bare structural frame going up, no surface finish, no LED, "
        "no styling yet."
    ),
    "building": (
        "the carpenter fitting most of the remaining boards across the frame, "
        "the piece now mostly built but still bare/unfinished wood, no LED "
        "glow yet, no styling."
    ),
    "lighting": (
        "the carpenter pressing a warm LED light strip into a channel along "
        "one edge of the now-finished piece, the first warm glow just "
        "beginning to show -- the wood is fully built and finished, but no "
        "final styling (cushions/throw/decor) yet."
    ),
}


def generate_intermediate(client, stage_name, concept, prev_image, after_image):
    prompt = (
        "Show this exact same room, same camera angle, same wall and window "
        f"positions as both reference images. This is the NEXT step after "
        f"the first reference image, showing {INTERMEDIATE_STEPS[stage_name]} "
        "The second reference image shows where this build is ultimately "
        "headed -- move visibly one step closer to it, not all the way "
        f"there. {SPATIAL_RULE} No text. Keep proportions, wall and window "
        "positions identical to both reference images."
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
    "f01": {
        "room": "a sunlit corner nook beside a large window in an otherwise "
        "empty modern room",
        "piece": "floating wall-mounted daybed nook with a slatted privacy "
        "screen",
        "style": "warm minimalist Japandi-inspired craftsmanship",
        "materials": "reclaimed scaffold-board planks with a warm walnut oil "
        "finish, blackened steel L-brackets, a slatted wood privacy screen, "
        "integrated warm LED strip lighting, a linen throw and boucle "
        "cushions styled on top",
        "raw_materials": "a stack of raw reclaimed scaffold-board planks, a "
        "coil of warm LED strip lighting, a small pile of blackened steel "
        "L-brackets",
    },
    "f02": {
        "room": "a plain wall beside a large window in an otherwise empty "
        "modern bedroom",
        "piece": "full-height built-in bookshelf wall with a hidden "
        "fold-down bed integrated into its center bay, the bed panel "
        "folded down and fully made up like a normal bed, blending "
        "seamlessly into the shelving around it",
        "style": "warm modern craftsman, quiet luxury",
        "materials": "rift-cut white oak shelving and paneling, blackened "
        "steel hardware, an upholstered bouclé fold-down bed panel, "
        "integrated warm LED strip lighting along the shelf undersides, "
        "styled books and objects filling the surrounding bays",
        "raw_materials": "a stack of raw white oak boards and plywood "
        "panels, a folded fold-down bed hardware kit still in its box, a "
        "coil of warm LED strip lighting, a small pile of blackened steel "
        "brackets",
    },
    "f03": {
        "room": "a plain wall beside a large window in an otherwise empty "
        "modern living room",
        "piece": "floating built-in media console and fireplace wall with "
        "a linear gas fireplace insert and concealed storage",
        "style": "warm modern industrial, quiet luxury",
        "materials": "blackened steel framing, wide-plank white oak "
        "paneling, a linear gas fireplace insert, a floating white oak "
        "media shelf, integrated warm LED strip lighting along the "
        "console's underside",
        "raw_materials": "a stack of raw white oak boards, a coiled roll "
        "of blackened steel angle stock, a boxed linear fireplace insert, "
        "a coil of warm LED strip lighting",
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
    images["materials"] = generate_materials(client, concept, images["after"])

    prev = images["materials"]
    for stage_name in ["framing", "building", "lighting"]:
        img = generate_intermediate(client, stage_name, concept, prev, images["after"])
        images[stage_name] = img
        prev = img

    for stage_name in STAGES:
        path = out_dir / f"{concept_id}_{stage_name}.png"
        images[stage_name].save(path)
        print(f"Saved {path}")


if __name__ == "__main__":
    main()
