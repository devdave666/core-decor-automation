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

Lighting direction defaults to ROOM_LIGHT (Dev's own established, validated
house style -- warm-lamps-against-blue-hour, see generate_concept.py's
extensive tuning notes), used as-is for e1-01. Once more reference reels were
uploaded, real diversity showed up even within "Type 1" -- not just palette,
but genuinely different color grades/moods (a warm, soft, hazy vintage-film
grade in one reel vs. e1-01's moody blue-hour treatment) and different cut
pacing (some reels average ~1-2s/cut, one is a 32-cut flash-montage in 7.4s).
Dev explicitly asked to capture some of that mood variety rather than force
every set into the same lighting treatment, so sets after e1-01 can supply
their own `light_sentence` to override ROOM_LIGHT -- see build_room_prompt.

Naming: concept set ids are `e{type}-{set:02d}` (e.g. "e1-01" = e-series,
Type 1 format, first themed set) so the source viral-reel type is legible
directly from the id, not just from a manifest -- per Dev's instruction to
"name appropriately so type matches in actual reel video in future." Room
FILES within a set additionally carry a style slug, matching the a-d
series' own `{concept}_{room}_{stylename}` convention exactly (e.g.
`d01_lib_oxblood`) -- e1-01 was missing this at first (`e1-01_liv_app.png`,
no style name) and got corrected once Dev pointed out that with multiple
sets/moods now in play, filenames need to self-document which ones share a
style well enough to "match similar images together" into one reel, not
just which numbered set they belong to. Every set now carries a top-level
`style_slug` used to build each room's `stem` as
`{set_id}_{room}_{style_slug}`.

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
        "style_slug": "earthymoody",
        "palette_sentence": (
            "a cohesive earthy palette carried through every room: warm burnt-"
            "terracotta plaster walls, deep olive velvet upholstery, dark walnut "
            "and smoked oak millwork and furniture, aged unlacquered brass "
            "fixtures and hardware, and warm cream boucle and linen textiles."
        ),
        "rooms": {
            "liv": {
                "stem": "e1-01_liv_earthymoody",
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
                "stem": "e1-01_din_earthymoody",
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
                "stem": "e1-01_off_earthymoody",
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

    # Analyzed from a second reference reel (also captioned around "earthy
    # tones," same hook family as e1-01, but a genuinely different color
    # grade and pace -- soft, warm, hazy, almost vintage-film, and cut MUCH
    # faster: 32 cuts in 7.4s vs. e1-01 source's ~1-2s/cut). Mediterranean/
    # Spanish-colonial leaning styling (dark carved wood, terracotta,
    # checkerboard textiles) rather than e1-01's organic-modern furniture
    # language, since that's what the reference itself showed.
    "e1-02": {
        "source_type": "Type 1 - firstchair (reel 6)",
        "style_slug": "warmvintage",
        "palette_sentence": (
            "a warm, sun-faded palette carried through every room: pale "
            "limewashed plaster walls, dark carved walnut and mahogany "
            "furniture and doors, terracotta tile flooring, aged brass "
            "fixtures and hardware, and antique wool textiles in muted "
            "cream, olive and rust tones."
        ),
        "light_sentence": (
            " Photographed in soft, warm, hazy late-afternoon light with a "
            "gentle vintage film quality: diffused golden sun filters in "
            "through the windows and settles evenly across the room rather "
            "than casting hard shafts, with a fine soft-focus warmth to the "
            "air itself. Colours are gently sun-faded and warm rather than "
            "vivid, contrast is soft rather than dramatic, and shadows are "
            "pale and warm rather than deep or cool. A light, dreamy film "
            "grain sits over the whole image. Nostalgic, sun-warmed and "
            "quietly romantic, closer to an old photograph left in the sun "
            "than a crisp modern architectural shoot."
        ),
        "rooms": {
            "liv": {
                "stem": "e1-02_liv_warmvintage",
                "room": "a residential living room",
                "style": "warm Spanish-colonial-influenced interior with "
                          "carved wood and hand-plastered walls",
                "styling": (
                    "a worn brown leather sofa with woven wool cushions, a "
                    "round hammered-brass coffee table, a large ink line-"
                    "drawing portrait in a gilt frame with its own picture "
                    "light, built-in plaster shelving lined with books and "
                    "a small terracotta urn, a potted olive branch in a "
                    "brass vessel, and a worn antique wool rug in faded "
                    "cream and rust."
                ),
                "fixtures": (
                    "a scalloped brass ceiling flush mount, a slim brass "
                    "picture light above the artwork, and a pair of brass "
                    "wall sconces flanking the shelving."
                ),
            },
            "ent": {
                "stem": "e1-02_ent_warmvintage",
                "room": "a residential entry hallway",
                "style": "warm Spanish-colonial-influenced interior with "
                          "carved wood and hand-plastered walls",
                "styling": (
                    "a carved dark walnut console table with a hammered "
                    "brass table lamp and a stack of books, a large woven "
                    "textile hanging on the wall, a terracotta floor "
                    "runner rug in a bold checkerboard pattern, a pair of "
                    "framed botanical prints, and a tall stoneware urn "
                    "with a dried branch beside an arched doorway."
                ),
                "fixtures": (
                    "a row of small brass pendant lights hung along the "
                    "hallway ceiling, spaced evenly down its length."
                ),
            },
        },
    },

    # Analyzed from a third reference reel: bright, sunny, Mediterranean-
    # coastal mood -- the opposite end of the lighting spectrum from e1-01/
    # e1-02, driven by real daylight rather than lamps or haze. Sage green
    # cabinetry + travertine + brass + woven natural textures, all lit by
    # strong warm sun rather than any artificial source.
    "e1-03": {
        "source_type": "Type 1 - firstchair (reel 4)",
        "style_slug": "sagecoastal",
        "palette_sentence": (
            "a bright Mediterranean coastal palette carried through every "
            "room: sage green painted cabinetry and millwork, warm "
            "honed travertine and limestone surfaces, aged brass fixtures "
            "and hardware, natural white oak flooring, and woven rush and "
            "linen textiles."
        ),
        "light_sentence": (
            " Photographed in bright, warm midday sunlight streaming "
            "directly through large windows: strong golden sunbeams fall "
            "across the floor and surfaces in clearly defined warm pools, "
            "with crisp bright highlights where the light lands and cool "
            "soft shadow everywhere else, full of real contrast. The room "
            "reads as sun-drenched, airy and alive rather than moody -- "
            "high real daylight, clean and warm, with the greenery outside "
            "the window visible and sunlit. Fresh, breezy and optimistic, "
            "like a coastal home at the height of a warm afternoon."
        ),
        "rooms": {
            "kit": {
                "stem": "e1-03_kit_sagecoastal",
                "room": "a residential kitchen",
                "style": "bright Mediterranean coastal interior with warm "
                          "natural materials",
                "styling": (
                    "a large honed travertine island with two woven rush "
                    "counter stools, open wood shelving lined with ceramic "
                    "bowls and ceramic jugs, a wood cutting board leaning "
                    "against the backsplash, a bowl of citrus fruit on the "
                    "island, a small potted herb plant on the windowsill, "
                    "and sheer linen curtains beside a large window."
                ),
                "fixtures": (
                    "two brass fluted pendant lights hung over the island, "
                    "and a brass gooseneck pot-filler faucet above the "
                    "range."
                ),
            },
            "din": {
                "stem": "e1-03_din_sagecoastal",
                "room": "a residential dining room adjoining the kitchen",
                "style": "bright Mediterranean coastal interior with warm "
                          "natural materials",
                "styling": (
                    "a round white oak dining table with woven rush-seat "
                    "dining chairs, a stoneware pitcher with a handful of "
                    "dried wildflowers on the table, a large woven wall "
                    "hanging, an open shelf with stacked ceramic plates, "
                    "and a natural jute rug underfoot."
                ),
                "fixtures": (
                    "a single large woven rattan pendant light centred "
                    "over the table."
                ),
            },
        },
    },
}


def build_room_prompt(room, palette_sentence, light_sentence=None):
    return (
        f"Interior photograph of {room['room']}, {room['style']}."
        f" The space is built from exactly this palette, which is the "
        f"defining feature of the room and must be clearly visible: "
        f"{palette_sentence}"
        + (light_sentence or ROOM_LIGHT)
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
    prompt = build_room_prompt(room, set_data["palette_sentence"], set_data.get("light_sentence"))

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
