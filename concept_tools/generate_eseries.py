"""
E-Series generator — application-photo-only content built to copy the FORMAT of
a real viral reel type, not any single existing a/b/c/d concept.

Format identified by analyzing "Type 1 - firstchair" (3 real reference reels,
see analyze_reference_reels.py's output and llms.txt): a rapid-cut montage
(~1-2s per cut, hard scene-change cuts) through SEVERAL DIFFERENT ROOMS of one
cohesive home, all sharing ONE consistent material/colour palette, with a
SINGLE static caption overlaid for the entire reel naming the theme (e.g.
"homes with earthy tones>", "what I mean when I say I love earthy tones:").
This is structurally different from every existing content type here:
- Main pipeline / Hot Takes: one room per concept, no shared-palette grouping.
- This format: a SET of rooms per concept, deliberately unified by palette,
  because the whole hook is "look at this one aesthetic across a whole house."

No swatches for this series (Dev's explicit instruction, may change later) --
application photos only, so this reuses the room-prompt machinery from
generate_concept.py (COMPOSITION/STYLING_RULE/SPATIAL_RULE/QUALITY_ROOM/
NO_TEXT are hard-won, measured-and-iterated constants; not duplicating them
here) but swaps materials_sentence + bands for a single palette_sentence
shared across every room in a set, since palette cohesion IS the format.

Lighting direction (ROOM_LIGHT, also reused) is Dev's own established,
validated house style (warm-lamps-against-blue-hour, see generate_concept.py's
extensive tuning notes) -- the reference reels themselves lean daytime-lit,
but matching Dev's own visual identity is the "creative twist" applied on top
of the borrowed format, not a mismatch to fix.

Naming: concept set ids are `e{type}-{set:02d}` (e.g. "e1-01" = e-series,
Type 1 format, first themed set) so the source viral-reel type is legible
directly from the id, not just from a manifest -- per Dev's instruction to
"name appropriately so type matches in actual reel video in future." Room
files within a set follow the existing room-abbreviation convention (liv,
din, off, bath, kit, bed...).

Uses Google's gemini-2.5-flash-image via Vertex AI (confirmed working end-to-
end, see discover_and_test_image_model.py and llms.txt), NOT Black Forest
Labs/FLUX -- deliberately a different model from the a-d series, per Dev's
choice to use Google's models for this new series.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_concept import (  # noqa: E402
    NO_TEXT, QUALITY_ROOM, ROOM_LIGHT, COMPOSITION, SPATIAL_RULE, STYLING_RULE,
    ROOM_W, ROOM_H,
)

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "us-central1"
MODEL = "gemini-2.5-flash-image"

OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "application_eseries"

# First test set only -- ONE room generated and reviewed before committing to
# the rest, same discipline used for the Vertex AI connection test itself.
# "Earthy tones" chosen deliberately: 2 of the 3 Type-1 reference reels used
# that exact theme, so it's a high-confidence format match, not a guess at
# what else might work.
ESERIES_SETS = {
    "e1-01": {
        "source_type": "Type 1 - firstchair",
        "palette_sentence": (
            "a cohesive earthy palette carried through every room: warm burnt-"
            "terracotta plaster walls, deep olive velvet upholstery, dark walnut "
            "and smoked oak millwork and furniture, aged unlacquered brass "
            "fixtures and hardware, and warm cream boucle and linen textiles."
        ),
        "rooms": {
            "liv": {
                "stem": "e1-01_liv",
                "room": "a residential living room",
                "style": "warm organic modern interior with soft rounded forms",
                "styling": (
                    "a deep olive velvet sectional sofa, a freeform live-edge "
                    "walnut coffee table, a single oversized abstract canvas in "
                    "muted earth tones, a large potted fiddle-leaf fig, a "
                    "textured cream boucle armchair, a stack of art books, a "
                    "ceramic vase with dried pampas grass, and a thick jute rug."
                ),
                "fixtures": (
                    "a low-hung round brass disc pendant over the seating area, "
                    "a sculptural brass floor lamp, and concealed cove lighting "
                    "along the ceiling perimeter."
                ),
            },
            "din": {
                "stem": "e1-01_din",
                "room": "a residential dining room",
                "style": "warm organic modern interior with soft rounded forms",
                "styling": (
                    "a long solid walnut dining table with sculptural rounded-"
                    "back olive velvet chairs, a low ceramic bowl of fruit and "
                    "two tall tapered candles on the table, an oversized "
                    "handmade stoneware urn on a walnut sideboard, and "
                    "floor-length unbleached linen curtains beside a tall "
                    "window."
                ),
                "fixtures": (
                    "a hand-formed plaster and brass chandelier hung low over "
                    "the table, a discreet brass wall sconce, and concealed "
                    "cove lighting along the ceiling perimeter."
                ),
            },
            "off": {
                "stem": "e1-01_off",
                "room": "a residential home office and reading nook",
                "style": "warm organic modern interior with soft rounded forms",
                "styling": (
                    "a walnut writing desk with a leather-and-brass task chair, "
                    "built-in walnut shelving lined with books and ceramics, a "
                    "cream boucle swivel armchair in the corner, a small "
                    "potted olive tree, and a vintage wool rug in muted earth "
                    "tones."
                ),
                "fixtures": (
                    "a brass articulating desk lamp, a slim brass wall sconce "
                    "beside the shelving, and concealed cove lighting along the "
                    "ceiling perimeter."
                ),
            },
        },
    },
}


def build_room_prompt(room, palette_sentence):
    return (
        f"Interior photograph of {room['room']}, {room['style']}."
        f" The space is built from exactly this palette, which is the "
        f"defining feature of the room and must be clearly visible: "
        f"{palette_sentence}"
        + ROOM_LIGHT
        + COMPOSITION
        + SPATIAL_RULE
        + f" Furnished and dressed with: {room['styling']}"
        + STYLING_RULE
        + f" The room's own light fittings are: {room['fixtures']}"
        + QUALITY_ROOM + NO_TEXT
    )


def upscale_and_sharpen(image_bytes):
    """
    gemini-2.5-flash-image outputs ~768x1344 (~1.03MP) regardless of the
    documented image_size="4K" config -- confirmed via a real request that
    field is silently ignored on this model (see llms.txt). FLUX's room
    shots render at ROOM_W x ROOM_H (1088x1920, ~2.1MP), so without this
    step every e-series image reads visibly softer next to the a-d series
    at the same display size, not because of a "different model look" but
    a real ~2x pixel-count gap.

    Lanczos resize to the exact FLUX target dimensions (apples-to-apples
    pixel count) plus a mild unsharp mask to restore the apparent edge
    crispness resampling softens. Reviewed against the original by eye
    before adopting this as the standard step -- genuinely sharper,
    no visible halos or artifacts. This does NOT add real detail the
    model didn't generate; it's a deliberate, disclosed trade-off, not a
    claim of higher fidelity. Revisit if Gemini 3 image model access ever
    clears on this GCP project (see llms.txt) -- that may make this step
    unnecessary rather than just improved.
    """
    from io import BytesIO
    from PIL import Image, ImageFilter

    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    upscaled = img.resize((ROOM_W, ROOM_H), Image.LANCZOS)
    sharpened = upscaled.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))
    out = BytesIO()
    sharpened.save(out, format="PNG")
    return out.getvalue()


def generate_room(client, set_id, room_key, model=MODEL):
    from google.genai import types

    set_data = ESERIES_SETS[set_id]
    room = set_data["rooms"][room_key]
    prompt = build_room_prompt(room, set_data["palette_sentence"])

    print(f"--- generating {room['stem']} with {model} ---")
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            image_config=types.ImageConfig(aspect_ratio="9:16"),
        ),
    )

    for candidate in response.candidates:
        for part in candidate.content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                out_path = OUT_DIR / f"{room['stem']}_app.png"
                out_path.write_bytes(upscale_and_sharpen(inline.data))
                print(f"  saved {out_path} (upscaled to {ROOM_W}x{ROOM_H})")
                return out_path
    raise RuntimeError(f"No image data in response for {room['stem']}: {response!r}"[:1000])


def main():
    import argparse
    from google import genai

    parser = argparse.ArgumentParser()
    parser.add_argument("set_id", choices=list(ESERIES_SETS.keys()))
    parser.add_argument("rooms", nargs="*", help="room keys to generate (default: all rooms in the set)")
    parser.add_argument("--model", default=MODEL, help=f"override the model id (default: {MODEL})")
    args = parser.parse_args()

    room_keys = args.rooms or list(ESERIES_SETS[args.set_id]["rooms"].keys())
    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    for room_key in room_keys:
        generate_room(client, args.set_id, room_key, model=args.model)


if __name__ == "__main__":
    main()
