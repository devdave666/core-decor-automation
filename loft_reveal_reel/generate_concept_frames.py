"""
Asset prep for the loft-reveal-reel format (a NEW, standalone content type --
see llms.txt). Sibling to transformation_reel (same chained-edit machinery,
same whole-room derelict-to-luxury arc) but with two deliberate differences
Dev asked for on this run:

1. **A single named human does the entire renovation alone**, not an
   anonymous crew of tradespeople. Every sibling format with people in it
   (transformation_reel, furniture_build_reel) used interchangeable generic
   workers where identity never had to hold across frames. Here it does --
   the same woman has to be recognizably the same woman in image 1 and image
   8, and in the FIRST and LAST frame of all 7 Veo clips. Fixed with a
   dedicated `generate_character()` reference portrait, generated once and
   passed as an explicit image reference into every single downstream
   generate_content call (after, raw, and all 6 intermediates) alongside a
   fixed `CHARACTER_DESCRIPTION` text block repeated in every prompt --
   identity is anchored by BOTH the reference image and consistent text on
   every call, not just one or the other.
2. **8 keyframes / 7 transition clips instead of the usual 5/4** -- Dev asked
   for exactly 7 four-second clips. Widening the stage count this far (vs.
   transformation_reel's 5) keeps each individual step small even with a
   longer overall arc, consistent with the same "small deltas per clip" logic
   transformation_reel's own v2 fix established.

Mice infestation is depicted through EVIDENCE, not live animals: droppings,
gnaw marks and chewed-through holes at the baseboards, greasy rub marks along
the walls, shredded cardboard and nesting material. Live rodents are
deliberately excluded (see generate_veo_clips.py's NEGATIVE_PROMPT) -- a
small fast-moving animal is exactly the kind of subject this project has
already found Veo can't hold consistent frame-to-frame (see the furniture_
build_reel hallucination saga in llms.txt), and getting it wrong would read
as unintentionally comedic rather than "beat down." The mess mice leave
behind carries the same story without that risk.

Reuses transformation_reel's proven machinery wholesale (gemini-2.5-flash-
image on Vertex AI, the aspect-ratio config fix, the VEO_CANVAS exact-crop
fix, chained edit-forward generation, the 429 retry).

Chained generation: character portrait first (identity anchor), then "after"
(finished loft with her in it) from text + character reference, "infested"
(the wreck) edited from "after" + character reference, then each of the 6
intermediate stages edited from the PREVIOUS stage (with "after" also passed
as a target reference and the character portrait passed on every single call)
so architecture, framing AND her appearance all stay locked across the chain.

Usage: python loft_reveal_reel/generate_concept_frames.py <concept_id> <out_dir>
Writes <out_dir>/<concept_id>_character.png and
<out_dir>/<concept_id>_{infested,clearing,repairing,painting,flooring,
furnishing,styling,after}.png, in that chronological order.
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

# Chronological order -- load-bearing for both this script and
# generate_veo_clips.py, which zips consecutive pairs from this same list.
STAGES = [
    "infested", "clearing", "repairing", "painting",
    "flooring", "furnishing", "styling", "after",
]

SPATIAL_RULE = (
    "The room is a coherent, physically real 3D space: every piece of "
    "furniture is fully separated from every other by visible floor or "
    "wall, all legs and bases are complete and resting on the floor, and "
    "any doorway or walking route is left clear and passable."
)

# Repeated verbatim in every prompt below AND anchored by the reference
# portrait image on every call -- text alone has never been reliable enough
# for identity-locking in this project's own findings, so both levers are
# used together here.
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
    print("--- generating AFTER ---")
    response = _generate_with_retry(client, [prompt, character_image])
    return _first_image(response)


def generate_infested(client, after_image, character_image):
    # Itemized/emphatic from the start -- the lesson every sibling format
    # eventually needed after a soft "before" instruction under-regressed.
    prompt = (
        "Show this exact same room, same camera angle, same architecture, "
        "same exposed brick, windows and beam positions -- but in a state "
        "of severe neglect and rodent infestation, far beyond an ordinary "
        "mess: dark greasy rub marks streak along the base of every wall "
        "where rodents have traveled repeatedly; the baseboards and one "
        "corner of drywall show ragged gnawed-through holes; scattered "
        "rodent droppings are visible on the floor and along the "
        "baseboards; shredded cardboard boxes and torn insulation used as "
        "nesting material spill out of a corner; thick dust and cobwebs "
        "coat every surface and hang from the exposed steel beams; old "
        "food packaging is chewed open and scattered; the floor beneath "
        "is stained, scuffed and littered with debris; peeling paint and "
        "water staining mar the brick and walls. No live rodents visible "
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


# Each entry: what SHE is doing alone at this step, one small delta from the
# previous stage. Single-handed throughout -- no other people ever appear.
INTERMEDIATE_STEPS = {
    "clearing": (
        "the woman alone hauling a full trash bag and a stack of ruined, "
        "chewed-open cardboard boxes toward the door, rubber gloves on, a "
        "dust mask pulled down around her neck, a broom and dustpan resting "
        "against the wall nearby. The worst of the rodent droppings, "
        "shredded nesting material and loose debris are visibly cleared "
        "from the floor, but the gnawed baseboards, grease marks and grimy "
        "walls are all still untouched -- this is the START of cleanup, "
        "not a finished one."
    ),
    "repairing": (
        "the woman alone kneeling at the baseboard, patching a gnawed-"
        "through hole with wire mesh and joint compound, a caulking gun and "
        "a small tray of compound beside her on a drop cloth, knee pads on. "
        "One section of wall/baseboard now looks freshly patched and pale "
        "against the still-grimy wall around it -- visibly further along "
        "than clearing, still no paint or fresh flooring."
    ),
    "painting": (
        "the woman alone rolling fresh light paint onto a section of wall "
        "with a roller on an extension pole, a paint tray and a spare "
        "roller cover on the drop cloth below, one wall now a clean bright "
        "color against the still-bare brick and unfinished floor around "
        "it."
    ),
    "flooring": (
        "the woman alone kneeling to fit a new wide-plank floorboard into "
        "place with a rubber mallet, spacer wedges lined up along the "
        "finished wall edge, a stack of unlaid boards close by. A section "
        "of new flooring now visibly covers part of the old stained floor, "
        "walls behind her now finished and painted."
    ),
    "furnishing": (
        "the woman alone carrying in a single armchair by herself, setting "
        "it down carefully in the now-finished room, a rolled area rug "
        "leaning against the wall waiting to be laid out. Walls and floor "
        "are now fully finished; furniture is only partially placed, room "
        "isn't fully styled yet -- visibly one step before the fully "
        "finished reference."
    ),
    "styling": (
        "the woman alone unrolling the area rug flat onto the new floor "
        "and setting a potted plant down beside the armchair, stepping "
        "back slightly to check the arrangement. Nearly everything from "
        "the finished reference image is now in place, just a couple of "
        "final touches (a throw pillow still on a nearby box, a lamp not "
        "yet switched on) short of fully done."
    ),
}


def generate_intermediate(client, stage_name, prev_image, after_image, character_image):
    prompt = (
        "Show this exact same room, same camera angle, same architecture, "
        "windows and beam positions as both room reference images. This is "
        f"the NEXT step after the first reference image, showing "
        f"{INTERMEDIATE_STEPS[stage_name]} The second room reference image "
        "shows where this renovation is ultimately headed -- move visibly "
        "one step closer to it, not all the way there. The third reference "
        "image shows the woman's face, hair, build and clothing -- match "
        f"her exactly, no other people ever appear. {SPATIAL_RULE} No text. "
        "Keep proportions, windows and beam positions identical to both "
        "room reference images."
    )
    print(f"--- generating {stage_name.upper()} (edited from previous stage) ---")
    response = _generate_with_retry(client, [prompt, prev_image, after_image, character_image])
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

    images = {}
    images["after"] = generate_after(client, concept, character_image)
    images["infested"] = generate_infested(client, images["after"], character_image)

    prev = images["infested"]
    for stage_name in ["clearing", "repairing", "painting", "flooring", "furnishing", "styling"]:
        img = generate_intermediate(client, stage_name, prev, images["after"], character_image)
        images[stage_name] = img
        prev = img

    for stage_name in STAGES:
        path = out_dir / f"{concept_id}_{stage_name}.png"
        images[stage_name].save(path)
        print(f"Saved {path}")


if __name__ == "__main__":
    main()
