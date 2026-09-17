"""
Asset prep for the loft-reveal-reel format. v2 (2026-08-28), rewritten after
Dev supplied external research diagnosing exactly why v1's forensic QA
failed -- see llms.txt for the full failure report and this file's v2 header
in generate_veo_clips.py for the paired pipeline restructuring. The two
findings that changed THIS file:

1. **"Single spatial anchor" principle.** v1 pre-generated all 8 keyframes
   upfront as a chain of independent edits, then handed pairs of them to Veo
   as (start, target) conditioning. The research's diagnosis: each edit call
   is a fresh synthesis, not true pixel-locked inpainting, so architecture
   (window scale, beam position, brick pattern) could drift between any two
   independently-generated stills even when editing forward -- and Veo's
   last_frame= conditioning then had to warp reality to bridge two stills
   that didn't actually describe the same physical room. v2 stops
   pre-generating a full chain of stills. This file now only produces THREE
   images: the character portrait, the "after" master shot (used loosely, as
   a style/architecture reference -- never as a hard Veo target anymore),
   and "infested" (edited from "after", same as v1). Every image AFTER
   "infested" is now produced by generate_veo_clips.py's interleaved loop,
   editing the ACTUAL last frame Veo rendered for the previous clip -- real
   photographed pixels, not another independent synthesis -- one small step
   at a time. `edit_forward()` below is the one generic function that loop
   calls repeatedly.

2. **Fixed the "floor already matches after" logic bug** the QA report
   caught: v1's `generate_infested()` never described the floor as
   different from the finished "after" floor, so the later "she installs
   new flooring" clip had nothing damaged to replace. v2 explicitly makes
   the infested floor dark, worn and damaged -- distinct from "after"'s
   whitewashed oak -- and `edit_forward()`'s per-step delta text (written in
   generate_veo_clips.py) explicitly carries that damaged floor forward
   until the flooring step actually replaces it.

Usage: python loft_reveal_reel/generate_concept_frames.py <concept_id> <out_dir>
Writes <out_dir>/<concept_id>_{character,after,infested}.png only -- the
remaining images in the sequence are produced during video generation, not
here.
"""
import sys
import time
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image, ImageOps

PROJECT = "core-decor-657616"
LOCATION = "us-central1"
MODEL = "gemini-2.5-flash-image"

VEO_CANVAS = (720, 1280)
MAX_RETRIES = 5
RETRY_BASE_DELAY_S = 20

IMAGE_CONFIG = types.GenerateContentConfig(
    image_config=types.ImageConfig(aspect_ratio="9:16")
)

SPATIAL_RULE = (
    "The room is a coherent, physically real 3D space: every piece of "
    "furniture is fully separated from every other by visible floor or "
    "wall, all legs and bases are complete and resting on the floor, and "
    "any doorway or walking route is left clear and passable."
)

# Repeated verbatim in every IMAGE prompt below AND anchored by the reference
# portrait image on every call. Note this stays an image-editing-step-only
# practice in v2 -- the research Dev supplied specifically flags heavy
# identity text as counterproductive during the VIDEO step (Veo should rely
# on the keyframe image alone there), so generate_veo_clips.py's motion
# prompts do NOT repeat this description. Here, for still editing, both
# levers together remain the right call.
CHARACTER_DESCRIPTION = (
    "a striking woman in her early thirties with warm olive skin and long "
    "dark wavy hair tied back in a low, loose bun with a few loose strands "
    "framing her face, wearing a fitted white tank top, rolled-cuff denim "
    "overalls, and a leather tool belt at her hips"
)


def generate_character(client):
    prompt = (
        f"A photorealistic full-body portrait of {CHARACTER_DESCRIPTION}, "
        "standing confidently with arms crossed, direct to camera, "
        "three-quarter angle, plain neutral studio-grey background, soft "
        "even studio lighting, sharp focus on her face and body, no text, "
        "no watermark, no props, no other people."
    )
    print("--- generating CHARACTER reference ---")
    response = _generate_with_retry(client, [prompt])
    return _first_image(response)


def generate_after(client, concept, character_image):
    # v2: still generated, but its role downstream has changed -- see this
    # file's header. No longer a Veo last_frame= target for any clip.
    prompt = (
        f"A photorealistic interior photograph of {concept['room']}, styled "
        f"in {concept['style']}. Materials clearly visible: "
        f"{concept['materials']}. The woman shown in the reference image "
        f"stands in the space, hands on hips, admiring the finished loft "
        f"she renovated single-handedly -- match her face, hair, build and "
        f"clothing exactly to the reference image. Warm 2700K lamplight at "
        f"several heights against cool light from the tall windows, "
        f"shadows holding real detail, no blown highlights. Eye-level "
        f"three-quarter view, real depth with objects in the near field. "
        f"{SPATIAL_RULE} Fully furnished, finished, high-end, magazine-"
        f"quality real estate photography, no text, no watermark, no other "
        f"people."
    )
    print("--- generating AFTER (style/architecture reference only) ---")
    response = _generate_with_retry(client, [prompt, character_image])
    return _first_image(response)


def generate_infested(client, after_image, character_image):
    # v2: added an explicit, itemized floor description -- dark, worn,
    # damaged -- distinct from "after"'s whitewashed oak. v1 never
    # described the floor at all here, so it silently inherited something
    # close to the finished floor, and the later flooring-replacement clip
    # had nothing damaged left to justify replacing (the QA report's
    # "installing a floor that already existed" finding).
    prompt = (
        "Show this exact same room, same camera angle, same architecture, "
        "same exposed brick, windows and beam positions -- but in a state "
        "of severe neglect and rodent infestation, far beyond an ordinary "
        "mess. The room is a COMPLETELY EMPTY SHELL -- absolutely no sofa, "
        "no armchair, no coffee table, no TV, no rug, no shelving, no "
        "potted plants, no pendant lighting, none of the furniture or "
        "decor from the reference image exists yet, not damaged, not "
        "partial, entirely absent -- only bare walls, bare floor, the "
        "windows and the exposed ceiling beams: dark greasy rub marks "
        "streak along the base of every wall "
        "where rodents have traveled repeatedly; the baseboards and one "
        "corner of drywall show ragged gnawed-through holes; scattered "
        "rodent droppings are visible on the floor and along the "
        "baseboards; shredded cardboard boxes and torn insulation used as "
        "nesting material spill out of a corner; thick dust and cobwebs "
        "coat every surface and hang from the exposed steel beams; old "
        "food packaging is chewed open and scattered; peeling paint and "
        "water staining mar the brick and walls. The wood floor itself is "
        "dark, worn, deeply scuffed, stained and damaged -- visibly aged "
        "and different from any finished flooring, clearly in need of "
        "full replacement, not just cleaning. No live rodents visible "
        "anywhere -- only the evidence they left behind. Dim, grim light "
        "through grimy industrial windows is the only illumination -- no "
        "work-lights, no fixtures. This should read as genuinely shocking "
        "neglect, the kind of 'before' that makes the finished loft feel "
        "like a magic trick. The woman from the reference image now stands "
        "just inside the doorway in work clothes -- fitted tank top, "
        "rolled-cuff overalls, tool belt, rubber gloves in one hand, a "
        "flashlight in the other -- surveying the mess before she starts, "
        "match her face, hair, build and clothing exactly to the reference "
        f"image. {SPATIAL_RULE} No other people. No text. Keep the room's "
        "proportions, windows and beam positions identical to the "
        "reference image so the space is still clearly recognizable as "
        "the same room."
    )
    print("--- generating INFESTED (edited from AFTER) ---")
    response = _generate_with_retry(client, [prompt, after_image, character_image])
    return _first_image(response)


def edit_forward(client, prev_image, character_image, delta_instruction):
    # v2's core new primitive, replacing generate_intermediate(). Called by
    # generate_veo_clips.py's interleaved loop on the ACTUAL last frame Veo
    # rendered for the previous clip (real photographed pixels), never on an
    # independently-imagined still -- this is what "single spatial anchor"
    # means in practice for a model without true mask/depth-conditioned
    # inpainting: keep editing the same real image forward by small deltas
    # instead of re-imagining the room from a text description each time.
    #
    # v2.1 fix (2026-08-28), after a real forensic QA pass on the first v2
    # run caught her tool belt and work gloves vanishing (replaced by knee
    # pads that appeared from nowhere) at one cut. Root cause: this prompt
    # told the model to match her "clothing" to the CHARACTER reference
    # image (the clean studio portrait -- no gloves, no knee pads, since
    # those are work-in-progress items she picks up mid-task) on every
    # single edit call, so each edit silently reset her back toward the
    # portrait's clean state instead of preserving whatever transient gear
    # she actually had on in the real previous frame. Fixed by splitting
    # the two reference images' jobs explicitly: the character image is
    # ONLY for face/hair/build (core identity), while current clothing,
    # tool belt, gloves, knee pads etc. must carry over from the FIRST
    # (previous-frame) reference image exactly, since that's what "nothing
    # else changes" already covers for every other object in the room --
    # her gear is not exempt from that rule just because a character
    # reference also happens to be in play.
    prompt = (
        "Show this exact same room, same camera angle, same architecture, "
        "exact same objects, walls, windows and floor as the FIRST "
        f"reference image -- with ONE small change: {delta_instruction} "
        "Nothing else in the frame changes at all -- same lighting, same "
        "untouched clutter or furniture, same everything except that one "
        "change. The woman's exact current clothing, tool belt, gloves, "
        "knee pads and any other gear must also stay identical to the "
        "FIRST reference image, whatever she currently has on -- do not "
        "reset her to a cleaner or different outfit. The SECOND reference "
        "image (a plain studio portrait) is ONLY for matching her face, "
        f"hair and build -- ignore its clothing entirely. {SPATIAL_RULE} "
        "No text. No other people."
    )
    response = _generate_with_retry(client, [prompt, prev_image, character_image])
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
    "l01": {
        "room": "an open-plan loft apartment with exposed brick walls, "
        "tall industrial steel-framed windows and exposed steel ceiling "
        "beams",
        "style": "airy modern industrial-chic",
        "materials": "wide-plank whitewashed oak flooring, freshly "
        "painted soft white walls against the original exposed brick, "
        "black steel and leather furniture, a large jute area rug, warm "
        "brass pendant lighting hung from the steel beams",
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

    character_image = generate_character(client)
    character_image.save(out_dir / f"{concept_id}_character.png")
    print(f"Saved {out_dir / f'{concept_id}_character.png'}")

    after_image = generate_after(client, concept, character_image)
    after_image.save(out_dir / f"{concept_id}_after.png")
    print(f"Saved {out_dir / f'{concept_id}_after.png'}")

    infested_image = generate_infested(client, after_image, character_image)
    infested_image.save(out_dir / f"{concept_id}_infested.png")
    print(f"Saved {out_dir / f'{concept_id}_infested.png'}")


if __name__ == "__main__":
    main()
