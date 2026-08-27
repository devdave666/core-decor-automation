"""
Asset prep for the stone-reveal-reel format (a NEW, standalone content type,
sibling to transformation_reel/, furniture_build_reel/, and
resort_reveal_reel/ -- see llms.txt). Different narrative shape again: a raw
quarried stone slab travels from an industrial stone yard (cut, polished)
to a finished luxury room built around it -- TWO locations, not one
continuous space, matching a real reference reel Dev supplied (a stone-yard
slab becoming a lit onyx bathroom floor).

Two deliberate pipeline changes Dev asked for on this format specifically,
both applied throughout:

1. **More stages than the sibling formats (7, not 5)** -- finer-grained
   steps mean each Veo clip only has to bridge a smaller visual delta,
   the same reasoning that drove transformation_reel's original 3->5
   widening.
2. **Each generation call references the FULL growing history of prior
   frames in its chain, not just the immediately previous one.** The
   sibling formats' generate_intermediate() only ever passed (prev_image,
   after_image) -- two references. Here, `generate_quarry_chain_stage()`
   and `generate_room_chain_stage()` take a `history_images` list that
   grows by one every stage, so by the last stage in each chain the model
   is seeing every prior frame in that chain at once, not just its
   immediate predecessor -- meant to reduce slow drift across a longer
   chain, not just adjacent-frame inconsistency.

Two locations, two chains, not one -- unlike every sibling format's single
continuous room:
- QUARRY chain (quarry_slab -> cutting -> polishing): forward-chained from
  a text-generated first frame, no distant target needed (it's short).
- ROOM chain (slabs_delivered -> installation -> lighting -> after):
  `after` generated FIRST from text (as in every sibling format),
  `slabs_delivered` edited from it (itemized/emphatic -- see
  generate_slabs_delivered()), then chained forward toward `after` with
  growing history, same as the sibling formats' pattern.
The cut BETWEEN the two chains (polishing -> slabs_delivered) is
deliberately NOT asked of Veo as continuous motion -- see
generate_veo_clips.py for why.

Usage: python stone_reveal_reel/generate_concept_frames.py <concept_id> <out_dir>
Writes <out_dir>/<concept_id>_{quarry_slab,cutting,polishing,slabs_delivered,
installation,lighting,after}.png
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

STAGES = [
    "quarry_slab", "cutting", "polishing",
    "slabs_delivered", "installation", "lighting", "after",
]
QUARRY_STAGES = ["quarry_slab", "cutting", "polishing"]
ROOM_STAGES = ["slabs_delivered", "installation", "lighting", "after"]

SPATIAL_RULE = (
    "This is a coherent, physically real space: every object rests "
    "believably on its surface, nothing floats or intersects impossibly, "
    "and any installed material sits flush and flat."
)


def generate_quarry_slab(client, concept):
    prompt = (
        f"A photorealistic photograph inside {concept['quarry_location']}. "
        f"A massive raw {concept['stone']}, freshly cut from the quarry, "
        f"hangs suspended from overhead crane hooks and chains, its rough "
        f"natural surface showing dramatic mineral veining, a wet concrete "
        f"floor below reflecting overhead lights. Industrial, wide "
        f"establishing shot, real depth. {SPATIAL_RULE} No text, no "
        f"watermark, no people."
    )
    print("--- generating QUARRY_SLAB ---")
    response = _generate_with_retry(client, [prompt])
    return _first_image(response)


def generate_after(client, concept):
    prompt = (
        f"A photorealistic interior photograph of {concept['room']}, "
        f"styled in {concept['room_style']}. {concept['final_feature']}. "
        f"Warm late-afternoon light through the glass, shadows holding "
        f"real detail, no blown highlights. Eye-level three-quarter view, "
        f"real depth with objects in the near field. {SPATIAL_RULE} Fully "
        f"finished, high-end, magazine-quality real estate photography, no "
        f"text, no watermark, no people."
    )
    print("--- generating AFTER ---")
    response = _generate_with_retry(client, [prompt])
    return _first_image(response)


def generate_slabs_delivered(client, concept, after_image):
    # v2 fix: the first real run of this prompt regressed the FLOOR/tub
    # (the only items named in concept['final_feature']) but left every
    # OTHER furnishing the model had independently added to `after` --
    # the mirror, sink, floor lamp, bench, wall tile -- completely intact,
    # because nothing ever told it those had to go too. Naming only what
    # the concept dict itself describes isn't enough; the reference image
    # can contain plenty the concept text never mentioned. Fixed by
    # switching to an absolute-baseline description (an empty unfinished
    # shell, explicitly listing every furnishing that must be absent)
    # instead of itemizing against the concept text -- the same shape of
    # fix that worked cleanly for resort_reveal_reel's generate_forest()
    # on its first attempt.
    prompt = (
        "Show this exact same room as an EMPTY, UNFINISHED CONSTRUCTION-"
        "STAGE SHELL -- same camera angle, same window and wall "
        "positions, same room proportions, but otherwise completely "
        "stripped back. The floor is bare subfloor or concrete, no stone "
        "flooring of any kind. The walls are bare, unfinished drywall or "
        "concrete, no tile, no finish material. There is absolutely NO "
        "furniture and NO fixtures of any kind anywhere in the room -- "
        "no tub, no sink, no vanity, no mirror, no floor lamp, no bench, "
        "no towels, no styling objects, no LED lighting. None of it "
        "exists yet in any form, not partially installed, not started, "
        "completely absent -- the room is a bare empty shell with "
        "nothing in it except what is listed next. Leaning against one "
        f"bare wall are several large finished, polished {concept['stone']} "
        "slabs, cut to size and ready for installation, plus a box of "
        "LED strip lighting and basic hand tools sitting on the bare "
        "floor -- these are the ONLY objects in the room. No text or "
        f"logos visible on any packaging. {SPATIAL_RULE} No people. No "
        "text. Keep the room's proportions, window and wall positions "
        "identical to the reference image so the space is still clearly "
        "recognizable as the same room, empty and unfinished."
    )
    print("--- generating SLABS_DELIVERED (edited from AFTER) ---")
    response = _generate_with_retry(client, [prompt, after_image])
    return _first_image(response)


QUARRY_STEPS = {
    "cutting": (
        "a large stone-cutting saw blade partially through one edge of the "
        "slab, water spraying to cool the cut, a clean flat cut face just "
        "beginning to appear next to the rough natural edge."
    ),
    "polishing": (
        "a polishing head grinding one face of the slab to a wet, glossy, "
        "mirror-like sheen, water and polish residue streaming down, the "
        "polished section dramatically more vivid and saturated than the "
        "still-rough surrounding stone."
    ),
}

ROOM_STEPS = {
    "installation": (
        "one or two installers fitting the polished stone slabs onto the "
        "bare floor, one slab already laid flush, grout lines being set, "
        "tools and the remaining slabs staged nearby -- visibly further "
        "along than the bare floor, but not yet finished."
    ),
    "lighting": (
        "an installer pressing a warm LED light strip into the channel "
        "along a seam line of the now-fully-laid stone floor, the first "
        "warm glow beginning to show along that one seam -- the floor is "
        "fully laid and polished, but not every seam is lit yet, and the "
        "room still lacks the tub, fixtures and final styling."
    ),
}


def generate_quarry_chain_stage(client, stage_name, concept, history_images):
    prompt = (
        "Show this exact same industrial stone yard, same camera angle, "
        "same crane and slab position as every reference image. This is "
        f"the NEXT step after the most recent reference image, showing "
        f"{QUARRY_STEPS[stage_name]} {SPATIAL_RULE} No people. No text. "
        "Keep the yard, crane and slab position identical to every "
        "reference image."
    )
    print(f"--- generating {stage_name.upper()} (referencing {len(history_images)} prior frame(s)) ---")
    response = _generate_with_retry(client, [prompt, *history_images])
    return _first_image(response)


def generate_room_chain_stage(client, stage_name, concept, history_images, after_image):
    prompt = (
        "Show this exact same room, same camera angle, same window and "
        "wall positions as every reference image. This is the NEXT step "
        f"after the most recent reference image, showing {ROOM_STEPS[stage_name]} "
        "The final reference image shows where this installation is "
        "ultimately headed -- move visibly one step closer to it, not all "
        f"the way there. {SPATIAL_RULE} No text. Keep proportions, window "
        "and wall positions identical to every reference image."
    )
    print(f"--- generating {stage_name.upper()} (referencing {len(history_images)} prior frame(s) + after) ---")
    response = _generate_with_retry(client, [prompt, *history_images, after_image])
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
    "s01": {
        "quarry_location": "an industrial stone-cutting yard, an overhead "
        "gantry crane with chain hooks, corrugated metal walls, skylights",
        "stone": "a raw quarried slab of pink and rose-veined onyx",
        "room": "a luxury primary bathroom with floor-to-ceiling glass "
        "walls opening onto a private garden",
        "room_style": "warm minimalist luxury",
        "final_feature": "a book-matched pink onyx floor and a "
        "freestanding stone soaking tub, with a warm LED light strip "
        "glowing along the floor's seam lines",
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
    images["quarry_slab"] = generate_quarry_slab(client, concept)
    images["cutting"] = generate_quarry_chain_stage(
        client, "cutting", concept, [images["quarry_slab"]]
    )
    images["polishing"] = generate_quarry_chain_stage(
        client, "polishing", concept, [images["quarry_slab"], images["cutting"]]
    )

    images["after"] = generate_after(client, concept)
    images["slabs_delivered"] = generate_slabs_delivered(client, concept, images["after"])
    images["installation"] = generate_room_chain_stage(
        client, "installation", concept, [images["slabs_delivered"]], images["after"]
    )
    images["lighting"] = generate_room_chain_stage(
        client, "lighting", concept,
        [images["slabs_delivered"], images["installation"]], images["after"],
    )

    for stage_name in STAGES:
        path = out_dir / f"{concept_id}_{stage_name}.png"
        images[stage_name].save(path)
        print(f"Saved {path}")


if __name__ == "__main__":
    main()
