"""
Asset prep for the transformation-reel format (a NEW, standalone content type --
see llms.txt. Not the c/d swatch+application series, not the e-series montage
format; this one is "derelict room becomes a finished luxury room, human workers
mid-transformation" and it needs several images of the SAME architectural space,
not a swatch/application pair).

v2, revised after reviewing the first real t01 output with Dev. Two real
problems in v1, both fixed here:

1. **Aspect ratio was never actually vertical.** v1 asked for "vertical 9:16
   composition" in the prompt TEXT only. The e-series build running in parallel
   on this same project already found (see llms.txt) that gemini-2.5-flash-image
   needs the aspect ratio set via `GenerateContentConfig(image_config=
   ImageConfig(aspect_ratio=...))`, a real config parameter -- prompt text alone
   is not load-bearing for this model's framing. v1 skipped that parameter, so
   the source frames came back closer to square/landscape, and Veo's own 9:16
   video canvas ended up pillarboxing that landscape content instead of framing
   a true vertical shot. Fixed by setting the config on every call below.

2. **Only 3 keyframes (before/mid/after) meant each Veo clip had to cover too
   much narrative distance in 8 seconds** -- workers visibly sped up / motion-
   blurred because "derelict -> half-renovated" is a lot to traverse in one
   short clip. Fixed by widening to 5 keyframes (before, demo, framing,
   finishing, after) so each of the 4 resulting Veo clips only has to bridge
   one adjacent, smaller step -- see generate_veo_clips.py for the clip side of
   this change.

Generated with gemini-2.5-flash-image on Vertex AI -- the model this project
already confirmed working end-to-end for the e-series (see llms.txt), not BFL
FLUX (that's the c/d-series' own tool, concept_tools/generate_concept.py, and
stays untouched here).

Chained generation, not five independent prompts: "after" is generated first
from text, "before" is edited from "after", then each of demo/framing/finishing
is edited from the PREVIOUS stage in the chain (with "after" also passed as a
second reference so the intermediate stages visibly progress toward it) --
architecture, camera angle and framing have to MATCH across every stage for
Veo's first/last-frame conditioning to read as one continuous space rather than
different rooms. A fresh independent generation for each state would not
guarantee that; editing the same source image forward does.

Usage: python transformation_reel/generate_concept_frames.py <concept_id> <out_dir>
Writes <out_dir>/<concept_id>_{before,demo,framing,finishing,after}.png, in
that chronological order -- generate_veo_clips.py consumes them as an ordered
STAGES list, not the old fixed 3-name set.
"""
import sys
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "us-central1"
MODEL = "gemini-2.5-flash-image"

IMAGE_CONFIG = types.GenerateContentConfig(
    image_config=types.ImageConfig(aspect_ratio="9:16")
)

# Chronological order -- load-bearing for both this script and
# generate_veo_clips.py, which zips consecutive pairs from this same list.
STAGES = ["before", "demo", "framing", "finishing", "after"]

SPATIAL_RULE = (
    "The room is a coherent, physically real 3D space: every piece of furniture "
    "is fully separated from every other by visible floor or wall, all legs and "
    "bases are complete and resting on the floor, and any doorway or walking "
    "route is left clear and passable."
)


def generate_after(client, concept):
    prompt = (
        f"A photorealistic interior photograph of {concept['room']}, styled in "
        f"{concept['style']}. Materials clearly visible: {concept['materials']}. "
        f"Warm 2700K lamplight at several heights against cool light from the "
        f"windows, shadows holding real detail, no blown highlights, no hard sun "
        f"shafts. Eye-level three-quarter view, real depth with objects in the "
        f"near field. {SPATIAL_RULE} Fully furnished, finished, high-end, "
        f"magazine-quality real estate photography, no text, no watermark, no "
        f"people."
    )
    print("--- generating AFTER ---")
    response = client.models.generate_content(
        model=MODEL, contents=[prompt], config=IMAGE_CONFIG
    )
    return _first_image(response)


def generate_before(client, after_image):
    prompt = (
        "Show this exact same room, same camera angle, same architecture, same "
        "windows and doorways -- but stripped down to a derelict, unfinished "
        "construction state: bare subfloor or cracked original flooring, patchy "
        "plaster and peeling old paint on the walls, no furniture, no styling, "
        "exposed conduit or wiring in one place, dust sheets, a single bare "
        "work-light or harsh fluorescent tube instead of the finished lighting. "
        f"{SPATIAL_RULE} No people. No text. Keep the room's proportions, "
        "windows and doorway positions identical to the reference image."
    )
    print("--- generating BEFORE (edited from AFTER) ---")
    response = client.models.generate_content(
        model=MODEL, contents=[prompt, after_image], config=IMAGE_CONFIG
    )
    return _first_image(response)


# Each entry: (stage name, what's different from the PREVIOUS stage in the
# chain). Kept as small, single-step deltas on purpose -- the whole point of
# widening from 3 to 5 keyframes is that each step should be a SMALL, natural
# amount of visible progress, not another big jump.
INTERMEDIATE_STEPS = {
    "demo": (
        "one or two human tradespeople doing early demolition/prep work: "
        "clearing debris into a bin, sweeping dust, starting to strip a section "
        "of wall. Still mostly bare and unfinished, but visibly less derelict "
        "than the first reference -- debris being actively removed, not just "
        "sitting there. Tools and a debris bin present."
    ),
    "framing": (
        "two or three human tradespeople actively installing: one laying new "
        "flooring boards, one applying a base coat of paint or plaster to the "
        "wall near the fireplace, materials (flooring boxes, paint cans) staged "
        "on drop cloths. Visibly further along than demo -- new surfaces "
        "partially in, still no furniture."
    ),
    "finishing": (
        "one or two human tradespeople placing furniture and final touches: "
        "positioning a sofa or chair, hanging a light fixture, wiping down a "
        "finished surface. Walls and floor now look finished; furniture is "
        "partially placed but the room isn't fully styled yet -- visibly one "
        "step before the fully finished reference."
    ),
}


def generate_intermediate(client, stage_name, prev_image, after_image):
    prompt = (
        "Show this exact same room, same camera angle, same architecture, "
        "windows and doorway positions as both reference images. This is the "
        f"NEXT step after the first reference image, showing {INTERMEDIATE_STEPS[stage_name]} "
        "The second reference image shows where this renovation is ultimately "
        "headed -- move visibly one step closer to it, not all the way there. "
        f"{SPATIAL_RULE} No text. Keep proportions, windows and doorway "
        "positions identical to both reference images."
    )
    print(f"--- generating {stage_name.upper()} (edited from previous stage) ---")
    response = client.models.generate_content(
        model=MODEL, contents=[prompt, prev_image, after_image], config=IMAGE_CONFIG
    )
    return _first_image(response)


def _first_image(response):
    for candidate in response.candidates:
        for part in candidate.content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                return Image.open(BytesIO(inline.data))
    raise RuntimeError(f"No inline image data in response: {response!r}"[:1000])


CONCEPTS = {
    "t01": {
        "room": "a living room with a large window wall and a fireplace",
        "style": "warm modern minimalism",
        "materials": "white oak flooring, honed limestone fireplace surround, "
        "linen upholstery, brushed brass fixtures",
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
    images["before"] = generate_before(client, images["after"])

    prev = images["before"]
    for stage_name in ["demo", "framing", "finishing"]:
        img = generate_intermediate(client, stage_name, prev, images["after"])
        images[stage_name] = img
        prev = img

    for stage_name in STAGES:
        path = out_dir / f"{concept_id}_{stage_name}.png"
        images[stage_name].save(path)
        print(f"Saved {path}")


if __name__ == "__main__":
    main()
