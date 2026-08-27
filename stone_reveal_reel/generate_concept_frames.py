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
  UNLIKE every sibling format, `slabs_delivered` (the bare room) is
  generated FIRST from text, and `after` is edited FROM it, adding the
  finished styling -- see generate_slabs_delivered()'s docstring for why
  this is reversed from the sibling formats' "after first, edit it down"
  pattern (image editors resist removing large established fixtures far
  more than they resist adding them). installation/lighting then chain
  forward from slabs_delivered toward after with growing history, same
  as the sibling formats' pattern.
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


def generate_slabs_delivered(client, concept):
    # v3 fix: v2's "edit AFTER down to bare" approach (itemized, then
    # absolute-baseline) failed TWICE on a real run -- the tub, sink,
    # mirror and floor lamp survived both attempts regardless of how
    # forcefully the prompt demanded their removal. Root cause isn't
    # wording, it's direction: gemini-2.5-flash-image's image-EDITING
    # mode is heavily biased toward preserving an established reference
    # photo's large fixtures even when explicitly told to remove them --
    # removing a bathtub from a finished bathroom photo is a much bigger
    # ask than the ADD-direction edits this project's other formats rely
    # on (adding decay, adding a bracket, adding an LED strip). Fixed by
    # flipping the whole room chain's generation order: this stage is now
    # generated FIRST, from TEXT ONLY (same technique as generate_quarry_
    # slab -- no reference image to fight against), and `after` is
    # generated by EDITING this bare shell to ADD the finished styling --
    # the direction image editors actually handle well.
    prompt = (
        f"A photorealistic photograph of {concept['room']}, in a bare, "
        "unfinished construction stage: bare subfloor or concrete, bare "
        "unfinished walls, no furniture, no fixtures, no tub, no sink, no "
        "mirror, no lighting fixtures -- an empty shell. Leaning against "
        f"one bare wall are several large finished, polished "
        f"{concept['stone']} slabs, cut to size and ready for "
        "installation, plus a box of LED strip lighting and basic hand "
        "tools on the bare floor -- the only objects in the room. Eye-"
        "level three-quarter view, real depth. No text or logos visible "
        f"on any packaging. {SPATIAL_RULE} No text, no watermark, no "
        "people."
    )
    print("--- generating SLABS_DELIVERED (text-only, bare shell) ---")
    response = _generate_with_retry(client, [prompt])
    return _first_image(response)


def generate_after(client, concept, slabs_delivered_image):
    prompt = (
        "Show this exact same room, same camera angle, same window and "
        "wall positions -- but now fully finished and styled: "
        f"{concept['final_feature']}, styled in {concept['room_style']}. "
        "The stone slabs have been installed as a finished floor with "
        "LED-lit seams, the walls are finished, and the room is fully "
        "furnished with a freestanding tub, sink/vanity, mirror, floor "
        "lamp, bench and styling objects. Warm late-afternoon light "
        "through the glass, shadows holding real detail, no blown "
        f"highlights. {SPATIAL_RULE} Fully finished, high-end, magazine-"
        "quality real estate photography, no text, no watermark, no "
        "people. Keep the room's proportions, window and wall positions "
        "identical to the reference image so this is still clearly the "
        "same room."
    )
    print("--- generating AFTER (edited from SLABS_DELIVERED) ---")
    response = _generate_with_retry(client, [prompt, slabs_delivered_image])
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

    images["slabs_delivered"] = generate_slabs_delivered(client, concept)
    images["after"] = generate_after(client, concept, images["slabs_delivered"])
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
