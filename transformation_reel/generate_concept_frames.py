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

3. **Fixing #1 wasn't actually enough -- real generated Veo clips still came
   back letterboxed.** gemini-2.5-flash-image's aspect_ratio="9:16" returns
   768x1344 (ratio 0.5714), which is close to but not identical to Veo's own
   real output canvas of 720x1280 (ratio 0.5625, confirmed via ffprobe on a
   generated clip). Veo pads that small mismatch with black bars instead of
   cropping to fill. Fixed by center-cropping every source frame to exactly
   720x1280 (`VEO_CANVAS`) via `ImageOps.fit` immediately after generation, so
   the mismatch never reaches Veo at all.

v3 (2026-08-23), prepared for FUTURE runs only -- not yet generated against.
Dev asked for more transformation "wow factor": `generate_before()` escalated
from a mild "unfinished construction site" to genuine abandoned-building decay
(collapsed ceiling section, water staining, crumbled plaster down to bare lath,
a cracked window pane, rubble, mold) while deliberately keeping the window
wall and fireplace opening recognizable -- those are the anchors the whole
chain depends on to still read as the same room. `demo`'s description was
updated to match (early cleanup now deals with rubble and a tarped ceiling,
not just dust). See generate_veo_clips.py's own v3 header for the paired
model-tier and audio-prompting changes.

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

# Veo's actual output canvas for aspect_ratio="9:16" (confirmed via ffprobe on
# a real generated clip). gemini-2.5-flash-image's own aspect_ratio="9:16"
# config returns 768x1344 (ratio 0.5714), which is CLOSE to but not exactly
# 720x1280 (0.5625) -- close enough that it looked fine as a still image, but
# Veo's image-conditioned generation doesn't crop-to-fill that mismatch, it
# pads it, so every real generated clip came back letterboxed even though the
# video container itself was correctly 720x1280. Exact-cropping every source
# frame to Veo's own canvas size before it ever reaches Veo removes the
# mismatch at the source instead of trying to fix it after generation.
VEO_CANVAS = (720, 1280)
MAX_RETRIES = 5
RETRY_BASE_DELAY_S = 20

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
    response = _generate_with_retry(client, [prompt])
    return _first_image(response)


def generate_before(client, after_image):
    # v3: pushed dramatically further into decay than v1/v2's "derelict
    # construction site" -- Dev asked for more transformation "wow factor,"
    # and a mildly unfinished room reads as a small step from the finished
    # one, not a dramatic one. Escalated toward genuine abandoned-building
    # decay while still keeping the window wall and fireplace opening
    # recognizable -- those are the anchors the whole 5-image chain and every
    # Veo clip depend on for reading as the SAME space; wreck everything
    # else, not those.
    prompt = (
        "Show this exact same room, same camera angle, same architecture, same "
        "window wall and fireplace opening position -- but in a state of severe "
        "abandonment and decay, far beyond an ordinary construction site: a "
        "section of the ceiling has collapsed, exposing damaged joists and "
        "hanging insulation; large dark water stains bloom across the walls and "
        "ceiling; plaster has crumbled away in big sheets revealing bare lath "
        "and brick beneath; one window pane is cracked with a spiderweb "
        "fracture; a pile of broken rubble, splintered wood and torn drywall "
        "sits heaped in a corner; rusted exposed pipework and dangling wires "
        "hang from the damaged ceiling; the floor is stained, cracked and "
        "littered with debris and dead leaves blown in from outside; faint mold "
        "staining creeps up one wall. Dim, grim natural light through the "
        "grimy, cracked window wall is the only illumination -- no work-lights, "
        "no fixtures. This should read as genuinely shocking neglect, the kind "
        "of 'before' that makes the finished room feel like a magic trick. "
        f"{SPATIAL_RULE} No people. No text. Keep the room's proportions, "
        "window wall and fireplace position identical to the reference image "
        "so the space is still clearly recognizable as the same room."
    )
    print("--- generating BEFORE (edited from AFTER) ---")
    response = _generate_with_retry(client, [prompt, after_image])
    return _first_image(response)


# Each entry: (stage name, what's different from the PREVIOUS stage in the
# chain). Kept as small, single-step deltas on purpose -- the whole point of
# widening from 3 to 5 keyframes is that each step should be a SMALL, natural
# amount of visible progress, not another big jump.
INTERMEDIATE_STEPS = {
    "demo": (
        "one or two human tradespeople doing heavy early cleanup: hauling "
        "broken rubble and splintered wood into a debris bin, sweeping up "
        "collapsed plaster and dead leaves, a tarp now covering the damaged "
        "section of ceiling overhead. The worst hazards (the rubble pile, the "
        "exposed damaged joists) are visibly being dealt with, but the room is "
        "still rough, stained and largely stripped -- this is the START of "
        "recovery from severe decay, not a finished demo. Tools, a debris bin "
        "and a shop light present."
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
    response = _generate_with_retry(client, [prompt, prev_image, after_image])
    return _first_image(response)


def _generate_with_retry(client, contents):
    # Five chained calls in quick succession tripped this project's per-minute
    # quota for gemini-2.5-flash-image on the very first v2 run (a real 429
    # RESOURCE_EXHAUSTED after just 2 calls, not a permission or config
    # problem) -- widening from 3 to 5 keyframes made this the first time
    # enough calls landed close enough together to hit it. Simple exponential
    # backoff, since this is a transient rate limit, not a hard failure.
    for attempt in range(MAX_RETRIES):
        try:
            return client.models.generate_content(
                model=MODEL, contents=contents, config=IMAGE_CONFIG
            )
        except genai_errors.ClientError as e:
            # Attribute name for the HTTP status on this exception isn't
            # nailed down across SDK versions -- check the rendered message
            # instead of guessing a field name that might not exist.
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
                # Center-crop to Veo's exact canvas ratio right away, so every
                # downstream chained edit is already working from an
                # exact-ratio reference image, not just the final save.
                return ImageOps.fit(img, VEO_CANVAS, method=Image.LANCZOS, centering=(0.5, 0.5))
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
