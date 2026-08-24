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

# e1-08's first real multi-variation batch hit a 429 RESOURCE_EXHAUSTED after
# just 2-3 calls -- the SDK's own short built-in retry (tenacity, ~24s) wasn't
# enough, and running two generate-eseries.yml instances concurrently against
# this trial project's shared per-minute quota made it worse. Same class of
# bug already hit and fixed once in transformation_reel/generate_concept_frames.py
# -- reusing that fix here rather than re-discovering it: patient exponential
# backoff for a transient rate limit, not a hard failure.
MAX_RETRIES = 5
RETRY_BASE_DELAY_S = 20

OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "application_eseries"

# Dev pasted one exact real photo (an "ANB Architecture Studio" kitchen render,
# same source studio as the e1-06/e1-07 reference reels -- not a new source)
# and asked for 10 images that vary mood/light/colour/material while staying
# "structurally consistent" with it. There is no true image-conditioning path
# available here (the pasted photo exists only as something Claude can SEE in
# the conversation, not as a file this generator can hand to the model as an
# input image), so structural consistency is achieved the same way every
# other multi-room set in this file achieves consistency across images: by
# repeating an identical, detailed description verbatim across every
# variation. This constant is that fixed description, transcribed directly
# from close inspection of Dev's actual pasted photo (island shape/position,
# stool count and style, pendant count and placement, cabinetry run,
# appliances, backsplash position) -- not invented or approximated from a
# generic "kitchen" idea. Every e1-08 room below unpacks this dict and then
# only overrides palette_sentence/light_sentence, so architecture/layout text
# never has to be retyped -- and can't drift out of sync -- across all 10.
KITCHEN_STRUCTURE = {
    "room": (
        "a residential kitchen, photographed from a fixed eye-level "
        "three-quarter angle across a long rectangular waterfall-edge "
        "island toward the range wall beyond it"
    ),
    "style": (
        "a modern kitchen with a floor-to-ceiling cabinetry run and a "
        "built-in beverage fridge along the back-left wall, and an "
        "extractor hood centred over the range against a tiled backsplash"
    ),
    "styling": (
        "the exact same architecture and layout in every image: a long "
        "rectangular island with a waterfall-edge countertop and a "
        "built-in sink with a gooseneck faucet at its near end, four "
        "backless round stools with ring footrests lined along the "
        "island's front side, a run of full-height cabinetry and a "
        "built-in glass-front beverage fridge at the far end of the back "
        "wall, a range and hood centred against the tiled backsplash, "
        "open shelving beside the range holding a few small objects and "
        "a potted plant, and a low bowl of fruit on the island counter."
    ),
    "fixtures": (
        "three pendant lights hung at staggered heights over the "
        "island, suspended on thin rods from the ceiling."
    ),
}

# Fixed room catalog for the "Type 2 - Grandeur" architecture-type houses
# (see the e2-01 entry far below for the full rationale). Dev wants the
# SAME set of room types across every future architecture type, so a reel
# can be cut either as "one house, all its rooms" or "one room type across
# every architecture style" -- defined once here, at module level like
# KITCHEN_STRUCTURE above, so every e2-* house references the identical
# room keys/labels rather than each house silently drifting.
GRAND_HOUSE_ROOMS = {
    "ext":  "the front exterior facade of a grand luxury residence",
    "ent":  "a grand entry foyer with a sweeping staircase, just inside the front door",
    "liv":  "a grand double-height living room",
    "din":  "a formal dining room",
    "kit":  "a grand luxury kitchen",
    "bed":  "a primary bedroom suite",
    "bath": "a primary spa bathroom",
    "off":  "a home library and office",
    "thr":  "a home theatre and wellness lounge",
    "pool": "an outdoor pool terrace at the rear of the residence",
}

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

    # Dev's feedback after e1-02/e1-03: both read as "bright" despite e1-02
    # being warm rather than sunny -- wanted genuinely dark/moody sets too,
    # and pointed back at the reference reels for it. Re-reviewing reel (4)'s
    # OTHER frames (only its bright kitchen was sampled the first time) found
    # exactly that: the same reel also shows a dramatically dark kitchen --
    # near-black cabinetry, brass hardware, marble, dark wood beams, captioned
    # "This is why cabinet color matters" (a bright-vs-dark cabinet-color
    # comparison, not a single mood). That dark frame is this set's real
    # grounding, not an invented mood. Cross-checked against real current
    # trend data (WebSearch, not assumed) -- "moody organic modern" (dark
    # wood, earthy deep tones, warm dramatic lighting) is confirmed as a real
    # live 2026 trend, not a guess at what might work.
    "e1-04": {
        "source_type": "Type 1 - firstchair (reel 4, dark cabinet frame)",
        "style_slug": "darkmoody",
        "palette_sentence": (
            "a dramatic dark palette carried through every room: deep "
            "near-black painted cabinetry and millwork, white and grey "
            "veined marble surfaces, aged warm brass fixtures and "
            "hardware, dark stained oak ceiling beams and flooring, and "
            "deep bottle-green and espresso-brown textiles."
        ),
        "light_sentence": (
            " Photographed at night with only the room's own warm brass "
            "fixtures lit: the dark cabinetry and beams recede into "
            "near-black shadow while the marble surfaces, brass hardware "
            "and any glazed cabinet interiors catch and hold the warm "
            "lamplight, creating strong, deliberate pools of warm light "
            "against deep darkness. Contrast is high and dramatic, "
            "shadows are rich near-black rather than grey, and the few "
            "lit surfaces glow. Moody, dramatic, editorial and confident "
            "rather than cozy."
        ),
        "rooms": {
            "kit": {
                "stem": "e1-04_kit_darkmoody",
                "room": "a residential kitchen",
                "style": "dramatic dark modern interior with traditional "
                          "millwork profiles",
                "styling": (
                    "a large island with a marble countertop and dark "
                    "cabinetry, a glass-front upper cabinet with lit "
                    "interior shelving showing white ceramics, a copper "
                    "pan hung near the range, a potted olive branch on "
                    "the island, and a patterned wool runner rug on the "
                    "floor."
                ),
                "fixtures": (
                    "two brass dome pendant lights with white glass "
                    "diffusers over the island, and a brass wall sconce "
                    "beside the range hood."
                ),
            },
            "bed": {
                "stem": "e1-04_bed_darkmoody",
                "room": "a residential primary bedroom",
                "style": "dramatic dark modern interior with traditional "
                          "millwork profiles",
                "styling": (
                    "a dark upholstered bed with deep bottle-green velvet "
                    "bedding and layered cushions, a pair of marble-top "
                    "nightstands, a single large abstract artwork above "
                    "the headboard, a small potted plant, and a dark wool "
                    "rug underfoot."
                ),
                "fixtures": (
                    "a pair of brass swing-arm wall sconces flanking the "
                    "bed in place of table lamps, and a single small "
                    "brass flush ceiling fixture."
                ),
            },
        },
    },

    # The "special" reel Dev asked for: opens on the EXTERIOR of the home,
    # then moves inside -- a real, recognized house-tour structure (real
    # estate / "come inside my home" content), confirmed via WebSearch as a
    # live current format, not assumed. Structurally different enough
    # (exterior shot has no interior three-quarter/walkway rules to obey)
    # that it needs its own composition handling -- see build_exterior_prompt
    # and the "is_exterior" flag below. Palette leans into the warm-neutral
    # "quiet luxury" trend confirmed in the same research pass (Pantone's
    # Mocha Mousse-adjacent warm neutrals), distinct from both e1-01/e1-02's
    # earthy/vintage tones and e1-04's dark drama.
    "e1-05": {
        "source_type": "Type 1 - firstchair (general house-tour structure, not one specific reel)",
        "style_slug": "quietluxury",
        "palette_sentence": (
            "a warm quiet-luxury neutral palette carried through every "
            "space, indoors and out: warm greige limestone and render, "
            "natural walnut millwork and doors, soft warm white walls, "
            "aged brass fixtures and hardware, and natural linen and "
            "boucle textiles."
        ),
        "light_sentence": (
            " Photographed at golden hour, sun low in the sky: warm "
            "directional late-day light rakes across every surface, "
            "throwing long soft shadows and catching texture in the "
            "limestone, render and brass. Colours are warm and rich "
            "without being dark -- warm highlights, soft warm shadow, "
            "never flat midday light and never night-time lamplight. "
            "Inviting, elevated and unmistakably golden hour throughout."
        ),
        "rooms": {
            "ext": {
                "stem": "e1-05_ext_quietluxury",
                "room": "the front exterior facade of a residential home",
                "style": "warm modern architectural exterior with quiet "
                          "luxury detailing",
                "styling": (
                    "a wide walnut front door with brass hardware, "
                    "black-framed windows, low manicured boxwood hedges "
                    "either side of the entry path, a pair of large "
                    "stone planters with olive trees flanking the door, "
                    "and a honed stone front walkway."
                ),
                "fixtures": (
                    "a pair of brass lantern wall sconces flanking the "
                    "front door."
                ),
                "is_exterior": True,
            },
            "ent": {
                "stem": "e1-05_ent_quietluxury",
                "room": "a residential entry foyer, just inside the front door",
                "style": "warm quiet-luxury interior with natural materials",
                "styling": (
                    "a narrow walnut console table with a stone bowl for "
                    "keys, a large round mirror in a brass frame above "
                    "it, a tall potted olive tree in the corner, a woven "
                    "jute runner rug, and a single piece of framed line-"
                    "art on the wall."
                ),
                "fixtures": (
                    "a single sculptural brass pendant light hung in the "
                    "entry, and concealed cove lighting along the ceiling "
                    "perimeter."
                ),
            },
            "liv": {
                "stem": "e1-05_liv_quietluxury",
                "room": "a residential living room adjoining the entry",
                "style": "warm quiet-luxury interior with natural materials",
                "styling": (
                    "a deep linen-upholstered sofa with boucle cushions, "
                    "a honed limestone coffee table, a single large "
                    "abstract canvas in warm neutral tones, a sculptural "
                    "ceramic vessel, a stack of art books, and a thick "
                    "wool rug in warm ivory."
                ),
                "fixtures": (
                    "a pair of brass floor lamps flanking the sofa, and "
                    "concealed cove lighting along the ceiling perimeter."
                ),
            },
        },
    },

    # Dev's feedback after approving e1-04/e1-05: everything so far reads as
    # "dull and boring," wants genuine "old money" wow factor, "not too
    # bright," and sent two real reference reels ("ANB Architecture Studio"
    # branded) to define it -- not a vague mood word this time, an actual
    # visual target. Reel 1: a "MATERIAL PALETTE" branding montage (charcoal
    # plaster/black marble/walnut/aged brass; warm ivory/cream marble/walnut/
    # brass; slate/walnut/cream marble/brass; deep maroon/olive/walnut/cream
    # quartz swatch cards) intercut with the finished kitchens those
    # palettes describe: every one built around a dramatic waterfall-edge
    # stone island, 2-3 slim cylindrical aged-brass pendants in a row, dark
    # walnut cabinetry, glass-front upper cabinets with their own interior
    # lighting, warm layered ambient light (never sun-bright, never night-
    # dark). Reel 2: a heritage/English-country-manor kitchen -- antique
    # double-dome brass pendant, dramatic veined-marble waterfall island on
    # a dark oak base, woven rush counter stools, brass bridge faucet, hung
    # copper pans, a gilt-framed oil landscape painting, a stoneware jug
    # with foraged olive branches, linen café curtains, soft diffused
    # daylight. Both genuinely restrained on STYLING -- 2-3 objects per
    # shot, not the 5-6-item lists this file had been writing -- which is
    # itself a big part of why the earlier sets read as "trying hard" by
    # comparison: density was reading as effort, not luxury. `light_sentence`
    # here is written from what both references actually show (warm layered
    # ambient -- pendant glow, under-cabinet light, soft daylight -- kept
    # moderate throughout), not from ROOM_LIGHT's blue-hour treatment, since
    # neither reference shows blue dusk at the windows. New
    # `styling_restraint_sentence` mechanism added specifically to enforce
    # the 2-3-object cap despite STYLING_RULE alone reading looser than that.
    # Dev said this direction holds "for next few generations," not just
    # this one set -- treat as the new default look until told otherwise,
    # not a one-off.
    "e1-06": {
        "source_type": "Dev-provided reference (ANB Architecture Studio kitchen reels, not Type 1/2)",
        "style_slug": "oldmoney",
        "palette_sentence": (
            "a rich, restrained old-money palette carried through every "
            "room, and ONLY this palette -- no other cabinet or wall "
            "colour appears anywhere in the room: dark walnut cabinetry "
            "and millwork, dramatically veined cream-and-grey marble with "
            "waterfall-edge surfaces, aged unlacquered brass fixtures and "
            "hardware, and warm soft-plaster walls in warm neutral tones."
        ),
        "light_sentence": (
            " Photographed under warm, layered ambient interior lighting: "
            "glowing brass pendant fixtures, warm under-cabinet lighting "
            "and soft cove light combine with gentle, diffused daylight "
            "through the windows. Exposure stays moderate and warm "
            "throughout the whole frame -- rich and inviting rather than "
            "sun-bright, and never dim or night-dark. Every material's "
            "true warm tone and texture -- marble veining, brass patina, "
            "walnut grain -- reads clearly and accurately. Elegant, "
            "editorial and quietly confident, like a shoot for an "
            "interiors magazine rather than a real-estate listing."
        ),
        "styling_restraint_sentence": (
            " Styling is deliberately spare -- at most two or three objects "
            "in the whole frame, chosen for quality over quantity, with "
            "large areas of clear counter, floor and wall left open. The "
            "architecture and materials themselves, not dense decor, are "
            "what create the impression of quiet wealth."
        ),
        "rooms": {
            "kit": {
                "stem": "e1-06_kit_oldmoney",
                "room": "a residential kitchen",
                "style": "old-money modern interior with heritage detailing",
                "styling": (
                    "a dramatic waterfall-edge island in richly veined "
                    "cream marble -- the sole piece of furniture standing "
                    "in the room, filling the near and middle ground with "
                    "cabinetry and appliances forming the background -- a "
                    "glass-front upper cabinet with lit interior shelving "
                    "showing glassware, and a low wooden bowl of citrus "
                    "fruit on the island."
                ),
                "fixtures": (
                    "three slim cylindrical aged-brass pendant lights hung "
                    "in a row over the island."
                ),
            },
            "din": {
                "stem": "e1-06_din_oldmoney",
                "room": "a residential dining room adjoining the kitchen",
                "style": "old-money modern interior with heritage detailing",
                "styling": (
                    "a long dark walnut dining table, a single large "
                    "gilt-framed oil landscape painting on the wall, and a "
                    "stoneware jug with a few foraged olive branches on "
                    "the table."
                ),
                "fixtures": (
                    "a slim brass picture light above the painting, and an "
                    "aged-brass chandelier with clean cylindrical arms "
                    "hung low over the table."
                ),
            },
        },
    },

    # e1-06 SUPERSEDED after one round of real feedback, not left standing as
    # a parallel option: Dev's reaction was "still very bright and no
    # furniture, feels empty!!" The `styling_restraint_sentence` mechanism
    # (2-3 objects, added for e1-06) overcorrected -- restraint read as
    # emptiness once there was only ever one piece of furniture (the island)
    # in frame. e1-07 drops that mechanism entirely and writes genuinely
    # furnished styling lists again (seating, rugs, layered textiles), same
    # density as e1-01, but keeps e1-06's real material/hardware language
    # (walnut, marble, aged brass) rather than throwing that part out too --
    # only brightness and furniture density were the actual complaints.
    #
    # Also a full lighting reversal: Dev explicitly asked for NIGHT-ONLY
    # application photos with "mood interior lights" and "darker shades and
    # darker materials" for "next few generations" -- not a per-set choice
    # this time, a standing instruction the same way e1-06's restraint was.
    # Reuses e1-04's real night-photography language (only the room's own
    # warm fixtures lit, near-black shadow, dramatic brass pools) as the
    # proven base for "genuinely dark, not just moodier," rather than
    # reinventing night lighting from scratch. New material instruction --
    # "stone and tiles alongside wood and colors and fabrics" -- means this
    # palette deliberately mixes MORE material categories per room than any
    # earlier set: dark stone AND patterned tile AND wood AND jewel-tone
    # fabric together, not one or two dominant materials.
    #
    # "Old money aesthetics that meet modern decor" is read as: keep the
    # heritage MATERIALS and hardware language (marble, brass, walnut, oil
    # painting) but give furniture clean modern silhouettes rather than
    # reel 2's literal antique country pieces (turned legs, rush seats) --
    # a fusion, not a reversion to e1-02's Spanish-colonial antique styling.
    "e1-07": {
        "source_type": "Dev-provided reference (ANB Architecture Studio reels) + Dev's night/furnished-density feedback (2026-08-23)",
        "style_slug": "nightluxe",
        "palette_sentence": (
            "a dark, richly layered old-money-meets-modern palette carried "
            "through every room: deep ebonized and dark walnut wood, "
            "dramatic dark stone waterfall surfaces (soapstone or dark "
            "emperador marble) alongside warm cream marble accents, "
            "patterned olive zellige tile, aged brass fixtures and "
            "hardware, and deep jewel-toned velvet and leather upholstery "
            "in bottle-green, oxblood and ink-navy."
        ),
        "light_sentence": (
            " Photographed at night, well after dark, with only the "
            "room's own warm brass fixtures and lamps lit: darkness fills "
            "the room outside each fixture's reach, and the dark wood, "
            "dark stone and deep-toned fabric recede into rich near-black "
            "shadow. Warm brass pools of light fall across the lit "
            "surfaces -- marble veining, tile glaze, leather, brass "
            "hardware -- catching their real texture and colour clearly. "
            "Contrast is high and dramatic, shadows keep real near-black "
            "depth rather than going flat or grey, and windows are dark "
            "with only the room's own light spilling into the glass. "
            "Intimate, moody and confidently dark rather than dim or "
            "underlit -- no daylight and no blue dusk anywhere in frame."
        ),
        "rooms": {
            "kit": {
                "stem": "e1-07_kit_nightluxe",
                "room": "a residential kitchen",
                "style": "dark old-money-meets-modern interior with clean "
                          "contemporary cabinetry lines",
                "styling": (
                    "a dramatic waterfall-edge island in dark soapstone-"
                    "look stone, a patterned olive zellige tile backsplash, "
                    "a built-in banquette in the corner with bottle-green "
                    "velvet cushions beside a small round dark-wood table, "
                    "a glass-front upper cabinet with lit interior "
                    "shelving showing glassware, a stack of leather-bound "
                    "cookbooks and a small potted olive branch on the "
                    "island, and a woven wool runner rug on the floor."
                ),
                "fixtures": (
                    "three slim cylindrical aged-brass pendant lights hung "
                    "at staggered heights over the island, and a single "
                    "brass wall sconce above the banquette."
                ),
            },
            "liv": {
                "stem": "e1-07_liv_nightluxe",
                "room": "a residential living room",
                "style": "dark old-money-meets-modern interior with clean "
                          "contemporary furniture silhouettes",
                "styling": (
                    "a deep bottle-green velvet sofa with oxblood leather "
                    "and cream boucle cushions, a dark stone coffee table "
                    "with slim brass legs, a pair of leather-and-brass "
                    "armchairs, a single large abstract painting in dark "
                    "rich tones, a thick patterned wool rug layered over "
                    "dark oak flooring, and a brass floor lamp beside the "
                    "sofa."
                ),
                "fixtures": (
                    "a low-hung aged-brass and smoked-glass chandelier "
                    "over the seating area, and a pair of brass wall "
                    "sconces flanking the artwork."
                ),
            },
        },
    },

    # Dev pasted one exact real ANB Architecture Studio kitchen photo and
    # asked for 10 variations -- "different moods, lights, colors and
    # materials... structurally it must stay consistent." All 10 share
    # KITCHEN_STRUCTURE verbatim (see that constant's own comment for why:
    # no real image-conditioning path exists here, so repeated identical
    # description is how structure stays locked). Kept every variation
    # within the still-active "night only, mood interior lights" standing
    # instruction from the e1-07 entry above -- this request adds variety
    # on top of that rule, it doesn't cancel it, so none of the 10 revert to
    # daylight. Diversity instead comes from varying WHICH warm source reads
    # as the mood-setter (brass pendant only, pendant + candlelight, pendant
    # + a warm counter lamp) and a genuinely wide material/colour spread --
    # near-black, oxblood, bottle-green, navy, taupe, pewter, plum -- so the
    # 10 read as real alternatives, not ten shades of the same room.
    "e1-08": {
        "source_type": "Dev-pasted exact photo (ANB Architecture Studio kitchen, same source as e1-06/e1-07) + 'generate 10 variations' request (2026-08-23)",
        "style_slug": "variations",
        "rooms": {
            "var01": {
                **KITCHEN_STRUCTURE,
                "stem": "e1-08_var01_ebonyblack",
                "palette_sentence": (
                    "near-black ebonized cabinetry, a dramatic black "
                    "marble waterfall island with fine white veining, "
                    "aged brass fixtures and hardware, and a black-and-"
                    "cream patterned tile backsplash."
                ),
                "light_sentence": (
                    " Photographed at night, well after dark, lit only "
                    "by the three warm brass pendants over the island: "
                    "the near-black cabinetry and island recede into "
                    "rich shadow, while the marble veining and brass "
                    "hardware catch the warm pooled light. High, "
                    "dramatic contrast, real near-black shadow depth, "
                    "no daylight anywhere in frame."
                ),
            },
            "var02": {
                **KITCHEN_STRUCTURE,
                "stem": "e1-08_var02_walnutblue",
                "palette_sentence": (
                    "deep walnut cabinetry, a honed warm travertine "
                    "waterfall island, aged brass fixtures, and a warm "
                    "cream zellige tile backsplash."
                ),
                "light_sentence": (
                    " Photographed at blue hour just after sunset: "
                    "through the window the sky is deep cool blue "
                    "twilight, while the three warm brass pendants light "
                    "the island in warm golden pools. The contrast "
                    "between warm interior light and cool blue dusk is "
                    "the defining quality of the image; shadows are deep "
                    "and softly blue-tinted."
                ),
            },
            "var03": {
                **KITCHEN_STRUCTURE,
                "stem": "e1-08_var03_oxbloodmarble",
                "palette_sentence": (
                    "oxblood-lacquered cabinetry, a dark emperador "
                    "marble waterfall island with warm brown veining, "
                    "aged brass fixtures, and a dark red-brown tile "
                    "backsplash."
                ),
                "light_sentence": (
                    " Photographed at night: the three brass pendants "
                    "over the island glow warm gold, joined by the "
                    "flicker of a small cluster of candles on the "
                    "island counter. Rich, jewel-toned and intimate, "
                    "deep near-black shadow beyond the lit pools, no "
                    "daylight in frame."
                ),
            },
            "var04": {
                **KITCHEN_STRUCTURE,
                "stem": "e1-08_var04_bottlegreen",
                "palette_sentence": (
                    "bottle-green painted cabinetry, a black soapstone "
                    "waterfall island, aged brass fixtures, and a dark "
                    "green zellige tile backsplash."
                ),
                "light_sentence": (
                    " Photographed at night, lit only by the three warm "
                    "brass pendants over the island and a warm glow "
                    "spilling in from an unseen fireplace off to one "
                    "side: rich, deep green cabinetry holds real colour "
                    "even in shadow, brass and soapstone catch the "
                    "pooled warm light. Moody and dramatic, no daylight "
                    "anywhere in frame."
                ),
            },
            "var05": {
                **KITCHEN_STRUCTURE,
                "stem": "e1-08_var05_charcoalcalacatta",
                "palette_sentence": (
                    "charcoal-blue cabinetry, a dramatic white Calacatta "
                    "marble waterfall island with bold grey veining, "
                    "aged brass fixtures, and a white marble-slab "
                    "backsplash."
                ),
                "light_sentence": (
                    " Photographed at night, lit only by the three warm "
                    "brass pendants over the island: the pale marble "
                    "island glows warmly under the pendant light while "
                    "the charcoal-blue cabinetry recedes into near-black "
                    "shadow around it, a strong light-island-in-dark-"
                    "room contrast. No daylight anywhere in frame."
                ),
            },
            "var06": {
                **KITCHEN_STRUCTURE,
                "stem": "e1-08_var06_espressolimestone",
                "palette_sentence": (
                    "espresso-stained oak cabinetry, a warm taupe "
                    "honed-limestone waterfall island, aged brass "
                    "fixtures, and a warm taupe tile backsplash."
                ),
                "light_sentence": (
                    " Photographed at night: the three brass pendants "
                    "over the island are joined by a small warm table "
                    "lamp glowing on the counter near the range, giving "
                    "a softer, more domestic lamp-lit mood than a "
                    "pendant-only room. Warm and intimate, real shadow "
                    "depth away from the lit sources, no daylight in "
                    "frame."
                ),
            },
            "var07": {
                **KITCHEN_STRUCTURE,
                "stem": "e1-08_var07_inknavy",
                "palette_sentence": (
                    "ink-navy cabinetry, a dark green marble waterfall "
                    "island with fine gold-white veining, aged brass "
                    "fixtures, and a navy zellige tile backsplash."
                ),
                "light_sentence": (
                    " Photographed at night, lit by the three warm "
                    "brass pendants over the island plus a thin warm "
                    "glow of under-cabinet lighting along the back "
                    "counter: the navy cabinetry holds a deep, rich "
                    "colour rather than reading as black, marble veining "
                    "catches the light. Moody and dramatic, no daylight "
                    "anywhere in frame."
                ),
            },
            "var08": {
                **KITCHEN_STRUCTURE,
                "stem": "e1-08_var08_mahoganybasalt",
                "palette_sentence": (
                    "dark mahogany cabinetry, a honed grey basalt "
                    "waterfall island, aged brass fixtures, and a dark "
                    "grey tile backsplash."
                ),
                "light_sentence": (
                    " Photographed at night, lit only by the three warm "
                    "brass pendants over the island: warm light pools "
                    "on the basalt and brass while the mahogany "
                    "cabinetry deepens into rich near-black shadow. "
                    "Confidently dark and dramatic, no daylight anywhere "
                    "in frame."
                ),
            },
            "var09": {
                **KITCHEN_STRUCTURE,
                "stem": "e1-08_var09_nero_marquina",
                "palette_sentence": (
                    "aged pewter-grey cabinetry, a dramatic Nero "
                    "Marquina black marble waterfall island with bold "
                    "white veining, aged brass fixtures, and a black "
                    "marble-slab backsplash."
                ),
                "light_sentence": (
                    " Photographed at night, lit by the three warm "
                    "brass pendants over the island plus a small cluster "
                    "of lit candles grouped on the island counter beside "
                    "the fruit bowl: the bold white marble veining "
                    "catches every point of light against deep near-"
                    "black shadow elsewhere in the room. Dramatic and "
                    "editorial, no daylight anywhere in frame."
                ),
            },
            "var10": {
                **KITCHEN_STRUCTURE,
                "stem": "e1-08_var10_plumtaupe",
                "palette_sentence": (
                    "deep plum-brown cabinetry, a warm rose-taupe honed "
                    "stone waterfall island, aged brass fixtures, and a "
                    "warm taupe tile backsplash, with a woven wool "
                    "runner rug tucked beneath the stools for a soft "
                    "fabric note."
                ),
                "light_sentence": (
                    " Photographed at night, lit only by the three warm "
                    "brass pendants over the island: warm plum and rose-"
                    "taupe tones glow softly under the pooled pendant "
                    "light, shadows keep real depth and colour rather "
                    "than going flat black. Warm, rich and intimate, no "
                    "daylight anywhere in frame."
                ),
            },
        },
    },

    # True reference-image editing, not description-only regeneration -- see
    # build_reference_edit_prompt's comment above for why this exists. Uses
    # e1-08_var01 (already committed to this repo) as the locked pixel
    # reference for every variation, rather than describing the room from
    # scratch each time. var02 was generated FIRST as a single test (reusing
    # e1-08 var02's exact palette/light content, for a direct apples-to-
    # apples comparison against the description-only version) and confirmed
    # visibly tighter -- island position, stool layout, pendant placement
    # and even the incidental console-table object all matched the var01
    # reference almost exactly, vs. e1-08's looser per-generation drift. The
    # rest (var03-var10) reuse the remaining e1-08 palette/light content
    # verbatim -- same 9 moods/materials, this time genuinely reimagining
    # the same photo instead of redrawing it from description each time.
    # (var01 itself has no entry here -- it IS the base reference image.)
    "e1-09": {
        "source_type": "True image-edit of e1-08_var01 (Dev asked for tighter structural consistency for a fast-cut reel)",
        "style_slug": "referenceedit",
        "base_image": "e1-08_var01_ebonyblack_app.png",
        "rooms": {
            "var02": {
                "stem": "e1-09_var02_walnutblue",
                "palette_sentence": (
                    "deep walnut cabinetry, a honed warm travertine "
                    "waterfall island, aged brass fixtures, and a warm "
                    "cream zellige tile backsplash."
                ),
                "light_sentence": (
                    " Photographed at blue hour just after sunset: "
                    "through the window the sky is deep cool blue "
                    "twilight, while the three warm brass pendants light "
                    "the island in warm golden pools. The contrast "
                    "between warm interior light and cool blue dusk is "
                    "the defining quality of the image; shadows are deep "
                    "and softly blue-tinted."
                ),
            },
            "var03": {
                "stem": "e1-09_var03_oxbloodmarble",
                "palette_sentence": (
                    "oxblood-lacquered cabinetry, a dark emperador "
                    "marble waterfall island with warm brown veining, "
                    "aged brass fixtures, and a dark red-brown tile "
                    "backsplash."
                ),
                "light_sentence": (
                    " Photographed at night: the three brass pendants "
                    "over the island glow warm gold, joined by the "
                    "flicker of a small cluster of candles on the "
                    "island counter. Rich, jewel-toned and intimate, "
                    "deep near-black shadow beyond the lit pools, no "
                    "daylight in frame."
                ),
            },
            "var04": {
                "stem": "e1-09_var04_bottlegreen",
                "palette_sentence": (
                    "bottle-green painted cabinetry, a black soapstone "
                    "waterfall island, aged brass fixtures, and a dark "
                    "green zellige tile backsplash."
                ),
                "light_sentence": (
                    " Photographed at night, lit only by the three warm "
                    "brass pendants over the island and a warm glow "
                    "spilling in from an unseen fireplace off to one "
                    "side: rich, deep green cabinetry holds real colour "
                    "even in shadow, brass and soapstone catch the "
                    "pooled warm light. Moody and dramatic, no daylight "
                    "anywhere in frame."
                ),
            },
            "var05": {
                "stem": "e1-09_var05_charcoalcalacatta",
                "palette_sentence": (
                    "charcoal-blue cabinetry, a dramatic white Calacatta "
                    "marble waterfall island with bold grey veining, "
                    "aged brass fixtures, and a white marble-slab "
                    "backsplash."
                ),
                "light_sentence": (
                    " Photographed at night, lit only by the three warm "
                    "brass pendants over the island: the pale marble "
                    "island glows warmly under the pendant light while "
                    "the charcoal-blue cabinetry recedes into near-black "
                    "shadow around it, a strong light-island-in-dark-"
                    "room contrast. No daylight anywhere in frame."
                ),
            },
            "var06": {
                "stem": "e1-09_var06_espressolimestone",
                "palette_sentence": (
                    "espresso-stained oak cabinetry, a warm taupe "
                    "honed-limestone waterfall island, aged brass "
                    "fixtures, and a warm taupe tile backsplash."
                ),
                "light_sentence": (
                    " Photographed at night: the three brass pendants "
                    "over the island are joined by a small warm table "
                    "lamp glowing on the counter near the range, giving "
                    "a softer, more domestic lamp-lit mood than a "
                    "pendant-only room. Warm and intimate, real shadow "
                    "depth away from the lit sources, no daylight in "
                    "frame."
                ),
            },
            "var07": {
                "stem": "e1-09_var07_inknavy",
                "palette_sentence": (
                    "ink-navy cabinetry, a dark green marble waterfall "
                    "island with fine gold-white veining, aged brass "
                    "fixtures, and a navy zellige tile backsplash."
                ),
                "light_sentence": (
                    " Photographed at night, lit by the three warm "
                    "brass pendants over the island plus a thin warm "
                    "glow of under-cabinet lighting along the back "
                    "counter: the navy cabinetry holds a deep, rich "
                    "colour rather than reading as black, marble veining "
                    "catches the light. Moody and dramatic, no daylight "
                    "anywhere in frame."
                ),
            },
            "var08": {
                "stem": "e1-09_var08_mahoganybasalt",
                "palette_sentence": (
                    "dark mahogany cabinetry, a honed grey basalt "
                    "waterfall island, aged brass fixtures, and a dark "
                    "grey tile backsplash."
                ),
                "light_sentence": (
                    " Photographed at night, lit only by the three warm "
                    "brass pendants over the island: warm light pools "
                    "on the basalt and brass while the mahogany "
                    "cabinetry deepens into rich near-black shadow. "
                    "Confidently dark and dramatic, no daylight anywhere "
                    "in frame."
                ),
            },
            "var09": {
                "stem": "e1-09_var09_nero_marquina",
                "palette_sentence": (
                    "aged pewter-grey cabinetry, a dramatic Nero "
                    "Marquina black marble waterfall island with bold "
                    "white veining, aged brass fixtures, and a black "
                    "marble-slab backsplash."
                ),
                "light_sentence": (
                    " Photographed at night, lit by the three warm "
                    "brass pendants over the island plus a small cluster "
                    "of lit candles grouped on the island counter beside "
                    "the fruit bowl: the bold white marble veining "
                    "catches every point of light against deep near-"
                    "black shadow elsewhere in the room. Dramatic and "
                    "editorial, no daylight anywhere in frame."
                ),
            },
            "var10": {
                "stem": "e1-09_var10_plumtaupe",
                "palette_sentence": (
                    "deep plum-brown cabinetry, a warm rose-taupe honed "
                    "stone waterfall island, aged brass fixtures, and a "
                    "warm taupe tile backsplash, with a woven wool "
                    "runner rug tucked beneath the stools for a soft "
                    "fabric note."
                ),
                "light_sentence": (
                    " Photographed at night, lit only by the three warm "
                    "brass pendants over the island: warm plum and rose-"
                    "taupe tones glow softly under the pooled pendant "
                    "light, shadows keep real depth and colour rather "
                    "than going flat black. Warm, rich and intimate, no "
                    "daylight anywhere in frame."
                ),
            },

            # Second batch (var11-var20). Dev's reaction to var02-var10:
            # "love it, add more themes (even lighter), more materials, and "
            # more lighting variations... research all materials that can be "
            # used in a kitchen, different stones, different tiles, colors "
            # textures wallpapers" -- and confirmed mid-turn these are more
            # edits of the SAME base photo, not a new concept. Grounded in
            # two real WebSearches (2026 kitchen countertop/backsplash trend
            # reporting, not invented) rather than reusing the same
            # brainstormed material list: quartzite (esp. Taj Mahal veining)
            # is the standout 2026 stone trend; terrazzo is back (resin
            # variants); granite is trending toward leathered/honed flowing
            # veining rather than small speckle; backsplashes are moving
            # toward blue tones, dusky pink, buttery yellow, sage/olive,
            # full-slab-matching-the-counter, and wallpaper-style treatments;
            # herringbone (white marble OR matte black/charcoal) is a major
            # pattern. "(even lighter)" read as genuinely brighter/paler
            # material palettes and a brighter interior-lit key -- var11-16
            # skew light, var17/19/20 keep the dramatic dark end going
            # ("more themes" is additive, not a replacement), var18 uses
            # actual wallpaper per Dev's explicit word. Every one still
            # stays within the standing "night only, mood interior lights"
            # rule (interior artificial light throughout, no daylight) since
            # Dev didn't rescind that -- "lighter" is read as brightness/
            # material tone within that rule, not a reversion to daylight.
            # Lighting itself is varied deliberately across the whole set,
            # from var11 (brightest, almost every fixture blazing) down to
            # var19 (darkest, single dramatic pendant-only pool) -- the
            # "more lighting variations" part of the ask.
            "var11": {
                "stem": "e1-09_var11_whitequartzite",
                "palette_sentence": (
                    "warm white shaker cabinetry, a dramatic Taj Mahal "
                    "quartzite waterfall island with soft golden-beige "
                    "veining, a white marble herringbone tile backsplash, "
                    "and aged brass fixtures and hardware."
                ),
                "light_sentence": (
                    " Photographed at night with every light in the room "
                    "switched on and bright: the three brass pendants over "
                    "the island blaze warm and bright, joined by strong "
                    "warm under-cabinet lighting and ceiling downlights, "
                    "so the room reads bright, fresh and airy rather than "
                    "moody -- minimal shadow, soft even illumination "
                    "throughout, the white cabinetry and pale quartzite "
                    "glowing warmly. Crisp, clean and inviting, the "
                    "lightest and brightest room in the collection so "
                    "far, though still lit entirely by the room's own "
                    "warm fixtures rather than daylight."
                ),
            },
            "var12": {
                "stem": "e1-09_var12_sagecarrara",
                "palette_sentence": (
                    "soft sage-green shaker cabinetry, a honed white "
                    "Carrara marble waterfall island with fine grey "
                    "veining, a white marble herringbone tile backsplash, "
                    "and aged brass fixtures."
                ),
                "light_sentence": (
                    " Photographed at night, warmly and brightly lit: the "
                    "three brass pendants over the island plus warm "
                    "under-cabinet lighting keep the room bright and "
                    "even, sage green and white marble both reading true "
                    "and fresh rather than shadowed. Airy, calm and "
                    "clean, no daylight in frame."
                ),
            },
            "var13": {
                "stem": "e1-09_var13_terrazzo",
                "palette_sentence": (
                    "warm white shaker cabinetry, a pale resin terrazzo "
                    "waterfall island flecked with soft rust, ochre and "
                    "grey chips, a colourful mosaic tile backsplash "
                    "echoing the terrazzo flecks, and aged brass fixtures."
                ),
                "light_sentence": (
                    " Photographed at night, brightly and evenly lit: the "
                    "three brass pendants over the island plus warm "
                    "ceiling downlights keep the whole room bright, the "
                    "terrazzo flecks and mosaic colours reading clearly "
                    "and cheerfully rather than muted by shadow. Playful, "
                    "fresh and lively, no daylight in frame."
                ),
            },
            "var14": {
                "stem": "e1-09_var14_skyblue",
                "palette_sentence": (
                    "warm white shaker cabinetry, a honed white quartzite "
                    "waterfall island with soft grey veining, a sky-blue "
                    "zellige tile backsplash, and aged brass fixtures."
                ),
                "light_sentence": (
                    " Photographed at night, warmly and evenly lit: the "
                    "three brass pendants over the island keep the room "
                    "bright, the sky-blue zellige holding its true colour "
                    "clearly rather than reading dark or muddy. Crisp, "
                    "fresh and inviting, no daylight in frame."
                ),
            },
            "var15": {
                "stem": "e1-09_var15_duskypink",
                "palette_sentence": (
                    "dusky pink shaker cabinetry, a honed white marble "
                    "waterfall island with soft pink-toned veining, a "
                    "pink-veined marble slab backsplash, and aged brass "
                    "fixtures."
                ),
                "light_sentence": (
                    " Photographed at night, softly and warmly lit: the "
                    "three brass pendants over the island cast a gentle "
                    "even warm glow, the dusky pink tones reading soft "
                    "and true rather than shadowed or muddy. Warm, "
                    "romantic and inviting, no daylight in frame."
                ),
            },
            "var16": {
                "stem": "e1-09_var16_butteryyellow",
                "palette_sentence": (
                    "buttery yellow shaker cabinetry, a honed warm "
                    "travertine waterfall island, a cream fluted tile "
                    "backsplash, and aged brass fixtures."
                ),
                "light_sentence": (
                    " Photographed at night, warmly and brightly lit: the "
                    "three brass pendants over the island plus warm "
                    "under-cabinet lighting keep the room bright and "
                    "cheerful, the buttery yellow cabinetry glowing warm "
                    "and true. Sunny, welcoming and fresh despite being "
                    "lit entirely by the room's own fixtures, no daylight "
                    "in frame."
                ),
            },
            "var17": {
                "stem": "e1-09_var17_leatherednavy",
                "palette_sentence": (
                    "deep navy shaker cabinetry, a leathered dark granite "
                    "waterfall island with flowing pale grey veining, a "
                    "geometric encaustic cement tile backsplash in navy "
                    "and cream, and aged brass fixtures."
                ),
                "light_sentence": (
                    " Photographed at night, lit only by the three warm "
                    "brass pendants over the island: the navy cabinetry "
                    "and leathered granite hold deep, rich colour in "
                    "shadow while the pendant light pools on the island "
                    "and cement tile pattern. Moody and dramatic, no "
                    "daylight anywhere in frame."
                ),
            },
            "var18": {
                "stem": "e1-09_var18_wallpaper",
                "palette_sentence": (
                    "soft sage-green shaker cabinetry, a honed soapstone "
                    "waterfall island in soft blue-grey, a botanical-print "
                    "wallpaper panel on the wall above the counter in "
                    "place of tile, and aged brass fixtures."
                ),
                "light_sentence": (
                    " Photographed at night, warmly and softly lit: the "
                    "three brass pendants over the island cast an even "
                    "warm glow across the room, the wallpaper's botanical "
                    "print and soapstone's soft colour both reading "
                    "clearly. Cosy, characterful and calm, no daylight in "
                    "frame."
                ),
            },
            "var19": {
                "stem": "e1-09_var19_mattecharcoal",
                "palette_sentence": (
                    "matte black shaker cabinetry, a leathered dark "
                    "granite waterfall island, a matte charcoal ceramic "
                    "herringbone tile backsplash, and aged brass fixtures."
                ),
                "light_sentence": (
                    " Photographed at night, lit only by the three warm "
                    "brass pendants over the island: the matte black "
                    "cabinetry and charcoal herringbone recede into deep "
                    "near-black shadow while the pendant light pools "
                    "sharply on the island and brass hardware. The "
                    "darkest and most dramatic room in the collection, no "
                    "daylight anywhere in frame."
                ),
            },
            "var20": {
                "stem": "e1-09_var20_emeraldcalacatta",
                "palette_sentence": (
                    "deep emerald-green shaker cabinetry, a dramatic "
                    "white Calacatta marble waterfall island with bold "
                    "grey veining, a full-slab white Calacatta marble "
                    "backsplash matching the island, and aged brass "
                    "fixtures."
                ),
                "light_sentence": (
                    " Photographed at night, lit by the three warm brass "
                    "pendants over the island: the emerald cabinetry "
                    "holds deep, rich colour while the pale marble "
                    "glows warmly under the pendant light, a strong "
                    "light-marble-against-dark-cabinetry contrast. Rich, "
                    "jewel-toned and dramatic, no daylight anywhere in "
                    "frame."
                ),
            },
        },
    },

    # Dev uploaded 21 real reference photos to a Drive folder literally named
    # "Type 2 - Grandeur" -- this IS the "Type 2" reference material flagged as
    # "not yet uploaded" back in the e1-01 entries, now arrived. Confirms `e2-*`
    # is the correct id prefix per this file's own naming rule (source viral-
    # reel/reference "type" legible directly from the concept id).
    #
    # The 21 photos are real luxury-real-estate/interior photography, not a
    # single consistent architectural style -- reviewed all of them rather than
    # guessing the mood from a folder name. Consistent threads across nearly
    # all 21: double-height ceilings, monumental sculptural lighting (crystal
    # chandeliers, wrought-iron-and-crystal fixtures, sculptural ring pendants),
    # book-matched marble feature walls and waterfall islands, rich velvet
    # upholstery in deep jewel tones, warm cove/under-shelf LED lighting
    # integrated into stone, floor-to-ceiling glass with skyline or garden
    # views, indoor-outdoor pool connection, linear gas fireplaces, and dramatic
    # warm night photography throughout (not one daylight shot in the set).
    # Full room catalog visible across the 21: exterior facade + pool/backyard,
    # grand entry with a sweeping staircase, living/great room (several
    # variants), formal dining room, kitchen, primary bedroom, primary
    # bathroom, outdoor terrace/balcony, and a home theatre/wellness lounge
    # with a plunge pool. This is the real basis for GRAND_HOUSE_ROOMS below,
    # not an invented list.
    #
    # Dev's own words: "these photos I want to be of grandeur, lavish luxury,
    # rich color palette, premium materials" -- read as: apply the SCALE,
    # DRAMA and MATERIAL RICHNESS the reference photos actually show (not
    # their specific contemporary architectural vocabulary) to a chosen
    # ARCHITECTURAL STYLE, starting with Gothic per Dev's own example. This is
    # the same "borrow the format, apply Core Decor's own twist" principle the
    # whole e-series was built on from the start, just at house scale now.
    #
    # STRUCTURAL REQUIREMENT, distinct from every set above: Dev explicitly
    # wants the SAME set of room types to exist for EVERY future architecture
    # type, specifically so a reel can be cut either as "one house, all its
    # rooms" (interior+exterior of a single style) OR "one room type across
    # every architecture style" (e.g. every style's living room back to back).
    # That only works if room keys and their basic identity stay fixed across
    # styles. GRAND_HOUSE_ROOMS (defined near the top of this file, above
    # ESERIES_SETS) is that fixed catalog -- the SAME 10 keys will be reused
    # for every future architecture type (e2-02, e2-03, ...), each time
    # re-styled for that style's own architectural language but keeping the
    # same room, in the same position in the sequence.

    # Dev's example architecture type: Gothic. Fuses real Gothic Revival
    # architectural vocabulary (pointed arches, ribbed vaults, stone tracery,
    # wrought iron, stained glass, buttresses) with the reference photos'
    # actual scale/drama language (monumental sculptural chandeliers, warm cove
    # lighting worked into the stone itself, book-matched dark marble, deep
    # jewel-toned velvet, dramatic warm night photography, modern-luxury
    # amenities like a waterfall kitchen island and a plunge-pool wellness
    # lounge) -- a real, recognizable "Gothic Revival billionaire mansion"
    # aesthetic, not either extreme alone. Every room reuses the SAME
    # palette_sentence/light_sentence for cross-room cohesion, exactly like
# every earlier e-series set.
    "e2-01": {
        "source_type": "Type 2 - Grandeur (Dev's own real reference photos, architecture type: Gothic)",
        "style_slug": "gothic",
        "drive_folder_name": "Gothic",
        "palette_sentence": (
            "a rich Gothic Revival palette carried through every room: deep "
            "charcoal and honey-toned limestone, dark rift-cut oak millwork "
            "and beams, wrought iron detailing, aged brass and bronze "
            "fixtures, richly veined dark emperador marble, and deep "
            "jewel-toned velvet upholstery in oxblood, emerald and sapphire, "
            "with jewel-coloured stained glass introducing accents of "
            "colour throughout."
        ),
        "light_sentence": (
            " Photographed at night, lit by monumental wrought-iron-and-"
            "crystal chandeliers, warm uplighting that traces the stone "
            "ribbing and tracery, and the warm glow of candlelight: every "
            "space reads soaring, dramatic and richly warm, with deep "
            "shadow climbing into the vaulted heights above the lit zones. "
            "Stained glass and jewel-toned velvet catch and hold the warm "
            "light vividly. Grand, cathedral-like and opulent, never flat "
            "or evenly lit -- light falls in deliberate dramatic pools "
            "exactly as it would in a real Gothic hall, no daylight "
            "anywhere in frame."
        ),
        "rooms": {
            "ext": {
                "stem": "e2-01_ext_gothic",
                "room": GRAND_HOUSE_ROOMS["ext"],
                "style": "Gothic Revival architecture: pointed-arch windows "
                          "with stone tracery, a steep slate roof, "
                          "buttresses and dark stone walls",
                "styling": (
                    "a massive pointed-arch entry door with wrought-iron "
                    "strap hinges, tall leaded and stained-glass windows "
                    "with carved stone tracery, dark stone cladding, "
                    "clipped yew hedges and climbing ivy flanking the "
                    "entry, and a stone path leading to the door."
                ),
                "fixtures": (
                    "a pair of monumental wrought-iron lantern sconces "
                    "flanking the entry door, and uplighting tracing the "
                    "stone facade and window tracery."
                ),
                "is_exterior": True,
            },
            "ent": {
                "stem": "e2-01_ent_gothic",
                "room": GRAND_HOUSE_ROOMS["ent"],
                "style": "Gothic Revival interior with soaring ribbed "
                          "vaults and pointed arches",
                "styling": (
                    "a sweeping stone staircase with a wrought-iron "
                    "balustrade curving up to a gallery landing, a soaring "
                    "ribbed-vault ceiling overhead, a towering stained-"
                    "glass window on the landing, a large woven tapestry "
                    "wall hanging, a grand console table with a large urn "
                    "of fresh flowers, and a dark stone floor with a "
                    "richly patterned runner rug."
                ),
                "fixtures": (
                    "a monumental wrought-iron-and-crystal chandelier hung "
                    "from the vaulted ceiling, and wrought-iron wall "
                    "sconces lining the staircase."
                ),
            },
            "liv": {
                "stem": "e2-01_liv_gothic",
                "room": GRAND_HOUSE_ROOMS["liv"],
                "style": "Gothic Revival interior with soaring ribbed "
                          "vaults and pointed arches",
                "styling": (
                    "a deep oxblood velvet sectional and a pair of emerald "
                    "velvet armchairs arranged around a monumental carved "
                    "stone fireplace, a huge pointed-arch window with "
                    "stone tracery overlooking the grounds, dark rift-oak "
                    "wall panelling, a large dark abstract painting in an "
                    "ornate frame, and a thick jewel-toned patterned rug "
                    "over dark stone flooring."
                ),
                "fixtures": (
                    "a monumental wrought-iron-and-crystal chandelier hung "
                    "from the ribbed-vault ceiling, and wrought-iron wall "
                    "sconces flanking the fireplace."
                ),
            },
            "din": {
                "stem": "e2-01_din_gothic",
                "room": GRAND_HOUSE_ROOMS["din"],
                "style": "Gothic Revival interior with soaring ribbed "
                          "vaults and pointed arches",
                "styling": (
                    "a long dark rift-oak dining table set for a formal "
                    "dinner with fine glassware and candlesticks, richly "
                    "upholstered emerald velvet dining chairs with dark "
                    "wood frames, a tall arched leaded-glass window, dark "
                    "wood wall panelling hung with one large tapestry, and "
                    "a carved stone sideboard."
                ),
                "fixtures": (
                    "a wrought-iron chandelier with candle-style bulbs hung "
                    "low over the table, and wrought-iron wall sconces "
                    "along the panelled walls."
                ),
            },
            "kit": {
                "stem": "e2-01_kit_gothic",
                "room": GRAND_HOUSE_ROOMS["kit"],
                "style": "Gothic Revival architecture fused with a modern "
                          "luxury kitchen",
                "styling": (
                    "a massive waterfall-edge island in richly veined dark "
                    "emperador marble beneath an exposed dark oak beam "
                    "ceiling, integrated dark cabinetry with wrought-iron "
                    "hardware, a large arched leaded-glass window over the "
                    "sink, a glass-front cabinet with lit interior "
                    "shelving, and a low bowl of fruit on the island."
                ),
                "fixtures": (
                    "three wrought-iron-and-glass pendant lights hung over "
                    "the island, and warm under-cabinet lighting."
                ),
            },
            "bed": {
                "stem": "e2-01_bed_gothic",
                "room": GRAND_HOUSE_ROOMS["bed"],
                "style": "Gothic Revival interior with soaring ribbed "
                          "vaults and pointed arches",
                "styling": (
                    "a dark wood four-poster bed with wrought-iron "
                    "detailing and deep sapphire velvet bedding, a tall "
                    "arched window dressed with heavy velvet drapery, a "
                    "carved stone fireplace, a pair of dark wood "
                    "nightstands, and a richly patterned rug over dark "
                    "wood flooring."
                ),
                "fixtures": (
                    "a wrought-iron-and-crystal chandelier hung from the "
                    "vaulted ceiling, and a pair of wrought-iron wall "
                    "sconces flanking the bed."
                ),
            },
            "bath": {
                "stem": "e2-01_bath_gothic",
                "room": GRAND_HOUSE_ROOMS["bath"],
                "style": "Gothic Revival architecture fused with a modern "
                          "spa bathroom",
                "styling": (
                    "a freestanding dark stone soaking tub beneath a tall "
                    "arched leaded-glass window, a rainfall shower set "
                    "into a vaulted stone alcove, dark stone walls and "
                    "flooring, a dark stone vanity with a carved stone "
                    "vessel sink, and a wrought-iron towel rail."
                ),
                "fixtures": (
                    "a wrought-iron-and-glass pendant light over the tub, "
                    "and warm recessed lighting tracing the vaulted stone "
                    "ceiling."
                ),
            },
            "off": {
                "stem": "e2-01_off_gothic",
                "room": GRAND_HOUSE_ROOMS["off"],
                "style": "Gothic Revival interior with soaring ribbed "
                          "vaults and pointed arches",
                "styling": (
                    "floor-to-ceiling dark oak bookshelves lining the "
                    "walls, a carved dark wood writing desk with a leather "
                    "chair, a pair of oxblood leather armchairs beside a "
                    "carved stone fireplace, a tall arched window, and a "
                    "richly patterned rug over dark wood flooring."
                ),
                "fixtures": (
                    "a wrought-iron chandelier hung from the ribbed-vault "
                    "ceiling, and a pair of wrought-iron reading lamps "
                    "beside the armchairs."
                ),
            },
            "thr": {
                "stem": "e2-01_thr_gothic",
                "room": GRAND_HOUSE_ROOMS["thr"],
                "style": "Gothic Revival architecture fused with a modern "
                          "sunken media lounge",
                "styling": (
                    "a sunken lounge area with deep jewel-toned velvet "
                    "seating arranged around a large discreetly-framed "
                    "screen, dark stone vaulted walls, a stone-set plunge "
                    "pool along one side of the room, potted greenery, and "
                    "a low stone table with candles."
                ),
                "fixtures": (
                    "a dimmed wrought-iron chandelier, and warm recessed "
                    "lighting tracing the vaulted stone ceiling."
                ),
            },
            "pool": {
                "stem": "e2-01_pool_gothic",
                "room": GRAND_HOUSE_ROOMS["pool"],
                "style": "Gothic Revival architecture: a stone arcade of "
                          "pointed arches framing the terrace",
                "styling": (
                    "a lit pool bordered by dark stone paving, a stone "
                    "arcade of pointed Gothic arches running along one "
                    "side, manicured clipped hedges and climbing ivy, a "
                    "stone loggia with outdoor seating, and wrought-iron "
                    "lanterns along the pool edge."
                ),
                "fixtures": (
                    "wrought-iron lanterns lining the pool edge and "
                    "arcade, and underwater pool lighting."
                ),
                "is_exterior": True,
            },
        },
    },

    # Dev approved e2-01 (Gothic) but asked for a "modern twist" on every
    # house from here on: TVs and LED light-strip mood lighting worked in
    # deliberately, not left out the way a period-accurate restoration
    # would. e2-02 picks Art Deco specifically because it pairs naturally
    # with that ask rather than fighting it -- Deco's own real historical
    # vocabulary already leans on dramatic indirect/cove lighting and bold
    # geometric light fixtures, so LED strip lighting reads as a genuine
    # continuation of the style, not a bolted-on modern intrusion the way
    # it might in, say, a strict Gothic restoration. TVs are integrated
    # into feature walls (lacquer panelling, a sunburst-motif surround)
    # rather than just placed, for the same reason.
    #
    # Per Dev's efficiency note ("you are using up the limits way too
    # fast"), this house was generated in ONE batch of all 10 rooms rather
    # than the exterior-alone-then-continue test round Gothic used --
    # the underlying technique (plain text-to-image room prompts, same
    # COMPOSITION/SPATIAL_RULE/STYLING_RULE machinery) has now proven
    # reliable across e2-01's 10 rooms with zero defects needing a retry,
    # so a second single-room validation pass wasn't a good use of a full
    # extra round trip. Still reviewed every image by eye before
    # committing/uploading -- that discipline doesn't change, only the
    # number of tool round trips to get there.
    "e2-02": {
        "source_type": "Type 2 - Grandeur (Dev's real reference photos, architecture type: Art Deco, 'modern twist' -- TVs + LED mood lighting)",
        "style_slug": "artdeco",
        "drive_folder_name": "Art Deco",
        "palette_sentence": (
            "a rich Art Deco palette carried through every room: black "
            "lacquer and dark walnut millwork with bold geometric inlay, "
            "polished brass and chrome fixtures and trim, richly veined "
            "black-and-gold marble and bold terrazzo, and deep jewel-"
            "toned velvet upholstery in emerald, sapphire and gold, with "
            "mirrored and lacquered surfaces catching the light."
        ),
        "light_sentence": (
            " Photographed at night, lit by geometric brass-and-glass "
            "fixtures, warm LED light strips traced along coves, "
            "stepped ceiling profiles, shelf edges and stair treads, "
            "and the warm glow of table lamps: every space reads sleek, "
            "glamorous and dramatically lit, with crisp warm light "
            "tracing every geometric line of the architecture itself. "
            "Mirrored and lacquered surfaces catch and multiply the "
            "light. Sleek, confident and theatrical, never flat or "
            "evenly lit -- light is used architecturally, tracing every "
            "stepped or fluted edge, no daylight anywhere in frame."
        ),
        "rooms": {
            "ext": {
                "stem": "e2-02_ext_artdeco",
                "room": GRAND_HOUSE_ROOMS["ext"],
                "style": "Art Deco architecture: a stepped, symmetrical "
                          "facade with fluted stone piers and bold "
                          "geometric relief ornament",
                "styling": (
                    "a pair of black lacquer entry doors with a "
                    "geometric sunburst motif in brass, fluted stone "
                    "piers flanking the entry, tall banded steel-framed "
                    "windows, clipped geometric hedging in a symmetrical "
                    "pattern, and a black-and-white terrazzo entry path."
                ),
                "fixtures": (
                    "a pair of geometric brass-and-glass lantern "
                    "sconces flanking the entry, and warm LED strip "
                    "lighting tracing the stepped facade's relief "
                    "ornament."
                ),
                "is_exterior": True,
            },
            "ent": {
                "stem": "e2-02_ent_artdeco",
                "room": GRAND_HOUSE_ROOMS["ent"],
                "style": "Art Deco interior with bold geometric "
                          "millwork and stepped profiles",
                "styling": (
                    "a curved black lacquer staircase with a polished "
                    "brass and glass balustrade, a black-and-gold "
                    "terrazzo floor laid in a radiating geometric "
                    "pattern, a large sunburst-motif mirrored wall "
                    "panel, a pair of tall potted palms, and a console "
                    "table in lacquered walnut with brass legs."
                ),
                "fixtures": (
                    "a monumental geometric brass-and-glass chandelier "
                    "hung from the stepped ceiling, and warm LED strip "
                    "lighting tracing the ceiling's stepped profile and "
                    "every stair tread."
                ),
            },
            "liv": {
                "stem": "e2-02_liv_artdeco",
                "room": GRAND_HOUSE_ROOMS["liv"],
                "style": "Art Deco interior with bold geometric "
                          "millwork and stepped profiles",
                "styling": (
                    "a curved emerald velvet sectional and a pair of "
                    "sapphire velvet armchairs arranged around a black "
                    "marble fireplace with a bold geometric surround, a "
                    "large flat-screen TV mounted flush into a black "
                    "lacquer feature wall with a brass sunburst inlay "
                    "surround, a black-and-gold terrazzo coffee table, "
                    "and a bold geometric-patterned rug over dark "
                    "walnut flooring."
                ),
                "fixtures": (
                    "a sculptural brass-and-glass chandelier with a "
                    "stepped geometric silhouette, and warm LED strip "
                    "lighting tracing the stepped cove ceiling and the "
                    "TV feature wall's brass inlay."
                ),
            },
            "din": {
                "stem": "e2-02_din_artdeco",
                "room": GRAND_HOUSE_ROOMS["din"],
                "style": "Art Deco interior with bold geometric "
                          "millwork and stepped profiles",
                "styling": (
                    "a long black lacquer dining table with a bold "
                    "brass inlay border, richly upholstered emerald "
                    "velvet dining chairs with brass frames, a "
                    "mirrored and lacquered sideboard, a large "
                    "geometric mirrored wall panel, and a "
                    "black-and-gold rug in a radiating sunburst pattern."
                ),
                "fixtures": (
                    "a stepped geometric brass-and-glass chandelier "
                    "hung low over the table, and warm LED strip "
                    "lighting tracing the stepped ceiling cove."
                ),
            },
            "kit": {
                "stem": "e2-02_kit_artdeco",
                "room": GRAND_HOUSE_ROOMS["kit"],
                "style": "Art Deco architecture fused with a modern "
                          "luxury kitchen",
                "styling": (
                    "a massive waterfall-edge island in bold "
                    "black-and-gold veined marble, glossy black lacquer "
                    "cabinetry with brass geometric hardware, a "
                    "mirrored glass-front cabinet with lit interior "
                    "shelving, and a low bowl of fruit on the island."
                ),
                "fixtures": (
                    "three geometric brass-and-glass pendant lights "
                    "hung over the island, and warm LED strip lighting "
                    "tracing the underside of the upper cabinetry."
                ),
            },
            "bed": {
                "stem": "e2-02_bed_artdeco",
                "room": GRAND_HOUSE_ROOMS["bed"],
                "style": "Art Deco interior with bold geometric "
                          "millwork and stepped profiles",
                "styling": (
                    "a black lacquer bed with a tall stepped and "
                    "channel-tufted sapphire velvet headboard, a large "
                    "flat-screen TV mounted flush into a lacquered "
                    "feature wall opposite the bed, a pair of mirrored "
                    "nightstands with brass legs, and a bold geometric "
                    "rug over dark walnut flooring."
                ),
                "fixtures": (
                    "a pair of geometric brass wall sconces flanking "
                    "the bed, and warm LED strip lighting tracing the "
                    "stepped cove ceiling and the underside of the "
                    "floating nightstands."
                ),
            },
            "bath": {
                "stem": "e2-02_bath_artdeco",
                "room": GRAND_HOUSE_ROOMS["bath"],
                "style": "Art Deco architecture fused with a modern "
                          "spa bathroom",
                "styling": (
                    "a freestanding black lacquer soaking tub on a "
                    "stepped black-and-gold marble platform, a "
                    "rainfall shower behind fluted glass, a mirrored "
                    "vanity wall with a brass-framed vessel sink, and "
                    "black-and-white geometric floor tile."
                ),
                "fixtures": (
                    "a geometric brass-and-glass pendant light over "
                    "the tub, and warm LED strip lighting tracing the "
                    "tub platform's steps and the vanity mirror's edge."
                ),
            },
            "off": {
                "stem": "e2-02_off_artdeco",
                "room": GRAND_HOUSE_ROOMS["off"],
                "style": "Art Deco interior with bold geometric "
                          "millwork and stepped profiles",
                "styling": (
                    "floor-to-ceiling black lacquer bookshelves with "
                    "brass trim lining the walls, a black lacquer "
                    "writing desk with a brass-framed leather chair, a "
                    "pair of emerald velvet armchairs, a large "
                    "flat-screen TV mounted flush into a lacquer panel "
                    "beside the shelving, and a bold geometric rug over "
                    "dark walnut flooring."
                ),
                "fixtures": (
                    "a stepped geometric brass chandelier, and warm "
                    "LED strip lighting tracing every shelf edge."
                ),
            },
            "thr": {
                "stem": "e2-02_thr_artdeco",
                "room": GRAND_HOUSE_ROOMS["thr"],
                "style": "Art Deco architecture fused with a modern "
                          "sunken media lounge",
                "styling": (
                    "a sunken lounge area with curved emerald velvet "
                    "seating arranged around a large flat-screen TV set "
                    "flush into a black lacquer and brass sunburst "
                    "feature wall, a black-and-gold terrazzo-edged "
                    "plunge pool along one side of the room, and a low "
                    "black lacquer table with a brass tray of glasses."
                ),
                "fixtures": (
                    "a dimmed geometric brass-and-glass chandelier, "
                    "and warm LED strip lighting tracing the sunken "
                    "lounge's steps and the pool's terrazzo edge."
                ),
            },
            "pool": {
                "stem": "e2-02_pool_artdeco",
                "room": GRAND_HOUSE_ROOMS["pool"],
                "style": "Art Deco architecture: a stepped colonnade "
                          "of fluted piers framing the terrace",
                "styling": (
                    "a lit pool bordered by black-and-white geometric "
                    "terrazzo paving, a stepped colonnade of fluted "
                    "stone piers running along one side, clipped "
                    "geometric hedging, and brass-and-glass lanterns "
                    "along the pool edge."
                ),
                "fixtures": (
                    "geometric brass-and-glass lanterns lining the "
                    "pool edge and colonnade, warm LED strip lighting "
                    "tracing the colonnade's stepped profile, and "
                    "underwater pool lighting."
                ),
                "is_exterior": True,
            },
        },
    },

    # Dev's reaction to e2-02 (Art Deco): "too much shine" -- a real
    # critique of the lacquer/mirror/polished-brass/glossy-terrazzo
    # material language, not a rejection of the whole grand-house
    # direction. e2-02 was therefore NOT committed/uploaded to Drive --
    # left in code as a design reference only, in case a toned-down pass
    # is ever wanted, but not published as a finished house. Dev's
    # instruction for the next house was explicit and specific: "earthy
    # tones, high-end wood, stone and leather." Named this style "Modern
    # Organic" -- warm minimalist architecture built from raw-sawn wood,
    # honed natural stone and leather, deliberately the material opposite
    # of e2-02: every reflective/glossy surface (lacquer, mirror, polished
    # brass/chrome, glossy terrazzo) is explicitly excluded from both the
    # palette and the light_sentence this time, not just omitted by
    # omission, since "too much shine" was a specific, correctable defect
    # rather than a vague dislike.
    "e2-03": {
        "source_type": "Type 2 - Grandeur (Dev's real reference photos, architecture type: Modern Organic, per Dev's explicit 'earthy tones, high-end wood, stone and leather' + no-shine correction after e2-02)",
        "style_slug": "modernorganic",
        "drive_folder_name": "Modern Organic",
        "palette_sentence": (
            "a warm earthy palette carried through every room: raw-sawn "
            "white oak and walnut millwork and beams, honed grey "
            "limestone and split-face natural stone, saddle-tan and "
            "chocolate leather upholstery, warm hand-troweled plaster "
            "walls, and blackened bronze fixtures and hardware, with "
            "woven wool, linen and jute textiles adding texture -- no "
            "polished marble, no lacquer, no mirrored surfaces and no "
            "glossy or polished metal anywhere."
        ),
        "light_sentence": (
            " Photographed at night, lit by warm, soft, indirect light: "
            "linen-shaded lamps, a lit fireplace, and recessed warm-"
            "dimmed downlights, with no glossy or reflective surface "
            "anywhere to catch or scatter the light -- every material "
            "reads matte and textural, absorbing the warm light rather "
            "than throwing it back. Shadows are soft and deep rather "
            "than sparkling, and the whole space feels grounded, "
            "tactile and quietly warm rather than glamorous or shiny. "
            "No daylight, no crystal, no polished brass and no mirror "
            "anywhere in frame."
        ),
        "rooms": {
            "ext": {
                "stem": "e2-03_ext_modernorganic",
                "room": GRAND_HOUSE_ROOMS["ext"],
                "style": "modern organic architecture: a board-formed "
                          "concrete and split-face stone base, deep "
                          "timber roof overhangs, and expansive glass",
                "styling": (
                    "a wide pivoting walnut front door with blackened "
                    "bronze hardware, a stacked natural stone facade, "
                    "deep overhanging eaves supported by exposed timber "
                    "beams, native grasses and boulders landscaping the "
                    "entry, and a honed stone path."
                ),
                "fixtures": (
                    "a pair of blackened-bronze lantern sconces "
                    "flanking the door, and warm uplighting on the "
                    "stone facade and timber beams."
                ),
                "is_exterior": True,
            },
            "ent": {
                "stem": "e2-03_ent_modernorganic",
                "room": GRAND_HOUSE_ROOMS["ent"],
                "style": "modern organic interior with exposed timber "
                          "beams and natural stone",
                "styling": (
                    "a floating walnut staircase with a blackened steel "
                    "and rope balustrade, a two-storey split-face stone "
                    "feature wall, a large woven wall hanging, a "
                    "console table in raw walnut with a stone-and-"
                    "bronze bowl, and a wide-plank white oak floor with "
                    "a natural wool runner."
                ),
                "fixtures": (
                    "a sculptural woven-rattan-and-bronze pendant light "
                    "hung from the beamed ceiling, and blackened bronze "
                    "wall sconces."
                ),
            },
            "liv": {
                "stem": "e2-03_liv_modernorganic",
                "room": GRAND_HOUSE_ROOMS["liv"],
                "style": "modern organic interior with exposed timber "
                          "beams and natural stone",
                "styling": (
                    "a deep saddle-tan leather sectional and a pair of "
                    "chocolate leather armchairs arranged around a raw "
                    "stone fireplace, a large flat-screen TV mounted "
                    "flush into a walnut-and-stone feature wall, "
                    "exposed timber ceiling beams, a huge expanse of "
                    "glass looking onto the grounds, and a thick wool "
                    "rug over wide-plank white oak flooring."
                ),
                "fixtures": (
                    "a sculptural blackened-bronze and woven-rattan "
                    "chandelier, and warm dimmed recessed lighting "
                    "tracing the exposed beams."
                ),
            },
            "din": {
                "stem": "e2-03_din_modernorganic",
                "room": GRAND_HOUSE_ROOMS["din"],
                "style": "modern organic interior with exposed timber "
                          "beams and natural stone",
                "styling": (
                    "a long live-edge walnut dining table with saddle-"
                    "tan leather-and-oak dining chairs, a split-face "
                    "stone feature wall, a large woven wall hanging, "
                    "and a wide-plank white oak floor with a natural "
                    "jute rug."
                ),
                "fixtures": (
                    "a row of blackened-bronze pendant lights with "
                    "linen shades hung low over the table, and warm "
                    "recessed lighting tracing the beamed ceiling."
                ),
            },
            "kit": {
                "stem": "e2-03_kit_modernorganic",
                "room": GRAND_HOUSE_ROOMS["kit"],
                "style": "modern organic architecture fused with a "
                          "modern luxury kitchen",
                "styling": (
                    "a massive waterfall-edge island in honed grey "
                    "limestone, raw white oak cabinetry with blackened "
                    "bronze hardware, open walnut shelving with stacked "
                    "ceramics, and a low stone bowl of fruit on the "
                    "island."
                ),
                "fixtures": (
                    "three blackened-bronze pendant lights with linen "
                    "shades hung over the island, and warm under-"
                    "cabinet lighting."
                ),
            },
            "bed": {
                "stem": "e2-03_bed_modernorganic",
                "room": GRAND_HOUSE_ROOMS["bed"],
                "style": "modern organic interior with exposed timber "
                          "beams and natural stone",
                "styling": (
                    "a low walnut platform bed with saddle-tan leather "
                    "headboard panelling, a large flat-screen TV "
                    "mounted flush into a stone feature wall opposite "
                    "the bed, a pair of raw walnut nightstands, a "
                    "stacked-stone fireplace, and a thick wool rug over "
                    "wide-plank white oak flooring."
                ),
                "fixtures": (
                    "a pair of blackened-bronze wall sconces flanking "
                    "the bed, and warm recessed lighting tracing the "
                    "beamed ceiling."
                ),
            },
            "bath": {
                "stem": "e2-03_bath_modernorganic",
                "room": GRAND_HOUSE_ROOMS["bath"],
                "style": "modern organic architecture fused with a "
                          "modern spa bathroom",
                "styling": (
                    "a freestanding honed-stone soaking tub beneath a "
                    "large window, a rainfall shower behind a wide "
                    "sheet of textured glass, a raw walnut vanity with "
                    "a hand-carved stone vessel sink, and split-face "
                    "stone walls."
                ),
                "fixtures": (
                    "a woven-rattan-and-bronze pendant light over the "
                    "tub, and warm recessed lighting tracing the stone "
                    "ceiling."
                ),
            },
            "off": {
                "stem": "e2-03_off_modernorganic",
                "room": GRAND_HOUSE_ROOMS["off"],
                "style": "modern organic interior with exposed timber "
                          "beams and natural stone",
                "styling": (
                    "floor-to-ceiling raw walnut bookshelves lining the "
                    "walls, a live-edge walnut writing desk with a "
                    "saddle-tan leather chair, a pair of chocolate "
                    "leather armchairs beside a stacked-stone fireplace, "
                    "a large flat-screen TV mounted flush into a walnut "
                    "panel beside the shelving, and a wool rug over "
                    "wide-plank white oak flooring."
                ),
                "fixtures": (
                    "a sculptural blackened-bronze chandelier, and warm "
                    "recessed lighting tracing every shelf edge."
                ),
            },
            "thr": {
                "stem": "e2-03_thr_modernorganic",
                "room": GRAND_HOUSE_ROOMS["thr"],
                "style": "modern organic architecture fused with a "
                          "modern sunken media lounge",
                "styling": (
                    "a sunken lounge area with deep saddle-tan leather "
                    "seating arranged around a large flat-screen TV set "
                    "flush into a stacked-stone feature wall, a honed-"
                    "stone-edged plunge pool along one side of the "
                    "room, exposed timber ceiling beams, and a low raw "
                    "walnut table."
                ),
                "fixtures": (
                    "a dimmed sculptural blackened-bronze chandelier, "
                    "and warm recessed lighting tracing the sunken "
                    "lounge's steps and the pool's stone edge."
                ),
            },
            "pool": {
                "stem": "e2-03_pool_modernorganic",
                "room": GRAND_HOUSE_ROOMS["pool"],
                "style": "modern organic architecture: a timber-and-"
                          "stone loggia with deep overhanging eaves",
                "styling": (
                    "a lit pool bordered by honed natural stone paving, "
                    "a timber-and-stone loggia with deep overhanging "
                    "eaves running along one side, native grasses and "
                    "boulder landscaping, and blackened-bronze lanterns "
                    "along the pool edge."
                ),
                "fixtures": (
                    "blackened-bronze lanterns lining the pool edge and "
                    "loggia, warm uplighting on the timber beams, and "
                    "underwater pool lighting."
                ),
                "is_exterior": True,
            },
        },
    },

    # House #4. Dev approved e2-03 and confirmed e2-02 (Art Deco) is worth
    # keeping despite its material critique, so both are now published.
    # Picked French Chateau for genuine contrast against all three houses
    # so far: Gothic (dark stone/wrought iron), Art Deco (glossy black
    # lacquer/geometric), Modern Organic (raw matte wood/stone/leather) --
    # French Chateau brings a warm pale limestone and gilt material
    # language none of the first three touched, while staying genuinely
    # grand per the "Type 2 - Grandeur" mandate. Kept the "modern twist"
    # rule (TVs, LED mood lighting) and the no-shine lesson from e2-02 in
    # mind even though gilt/brass are period-authentic here -- kept gilt
    # and brass DELIBERATELY MATTE/AGED rather than mirror-polished, so
    # the room reads opulent through colour and detail, not through glare.
    "e2-04": {
        "source_type": "Type 2 - Grandeur (Dev's real reference photos, architecture type: French Chateau)",
        "style_slug": "frenchchateau",
        "drive_folder_name": "French Chateau",
        "palette_sentence": (
            "a warm French Chateau palette carried through every room: "
            "pale honed Burgundy limestone and warm plaster walls, "
            "richly grained French oak millwork and herringbone "
            "parquet flooring, aged (not mirror-polished) gilt and "
            "brass detailing, and silk damask and velvet upholstery in "
            "dove grey, dusty rose and antique gold."
        ),
        "light_sentence": (
            " Photographed at night, lit by warm crystal-and-gilt "
            "chandeliers, warm LED strip lighting tracing cove and "
            "picture-rail mouldings for a modern layer of glow, and the "
            "soft flicker of candlelight: the gilt and brass read aged "
            "and softly warm rather than mirror-bright, and every "
            "surface glows gently rather than glaring. Elegant, "
            "refined and softly opulent, with deep warm shadow in the "
            "corners of each room. No daylight anywhere in frame."
        ),
        "rooms": {
            "ext": {
                "stem": "e2-04_ext_frenchchateau",
                "room": GRAND_HOUSE_ROOMS["ext"],
                "style": "French Chateau architecture: a symmetrical "
                          "pale limestone facade with a steep slate "
                          "mansard roof and tall French windows",
                "styling": (
                    "a pair of tall arched French doors with aged "
                    "bronze hardware, symmetrical rows of tall shuttered "
                    "windows in pale limestone surrounds, a steep grey "
                    "slate mansard roof with copper-topped dormers, "
                    "clipped topiary in stone urns flanking the entry, "
                    "and a graveled forecourt with a central fountain."
                ),
                "fixtures": (
                    "a pair of aged-bronze lantern sconces flanking the "
                    "entry doors, and warm uplighting on the limestone "
                    "facade."
                ),
                "is_exterior": True,
            },
            "ent": {
                "stem": "e2-04_ent_frenchchateau",
                "room": GRAND_HOUSE_ROOMS["ent"],
                "style": "French Chateau interior with tall panelled "
                          "walls and ornate plaster mouldings",
                "styling": (
                    "a sweeping curved limestone staircase with an "
                    "aged wrought-iron and brass balustrade, herringbone "
                    "parquet flooring, tall boiserie wall panelling "
                    "painted in soft dove grey, a large gilt-framed "
                    "mirror, and a round marble-topped console table "
                    "with a large urn of fresh flowers."
                ),
                "fixtures": (
                    "a grand crystal-and-gilt chandelier hung from the "
                    "ornate plaster ceiling medallion, and aged-brass "
                    "wall sconces lining the staircase."
                ),
            },
            "liv": {
                "stem": "e2-04_liv_frenchchateau",
                "room": GRAND_HOUSE_ROOMS["liv"],
                "style": "French Chateau interior with tall panelled "
                          "walls and ornate plaster mouldings",
                "styling": (
                    "a pair of dove-grey silk damask sofas and a dusty-"
                    "rose velvet armchair arranged around a carved "
                    "limestone fireplace, a large flat-screen TV "
                    "mounted flush into a boiserie panel above a "
                    "media console, tall French windows dressed with "
                    "silk drapery, an antique gilt mirror over the "
                    "mantel, and herringbone parquet flooring with a "
                    "silk rug."
                ),
                "fixtures": (
                    "a grand crystal-and-gilt chandelier, and aged-"
                    "brass wall sconces flanking the fireplace."
                ),
            },
            "din": {
                "stem": "e2-04_din_frenchchateau",
                "room": GRAND_HOUSE_ROOMS["din"],
                "style": "French Chateau interior with tall panelled "
                          "walls and ornate plaster mouldings",
                "styling": (
                    "a long French oak dining table set for a formal "
                    "dinner with fine crystal and candlesticks, dove-"
                    "grey silk-upholstered dining chairs with gilt "
                    "frames, tall boiserie panelling, a large gilt-"
                    "framed painting, and herringbone parquet flooring."
                ),
                "fixtures": (
                    "a grand crystal-and-gilt chandelier hung low over "
                    "the table, and aged-brass wall sconces along the "
                    "panelled walls."
                ),
            },
            "kit": {
                "stem": "e2-04_kit_frenchchateau",
                "room": GRAND_HOUSE_ROOMS["kit"],
                "style": "French Chateau architecture fused with a "
                          "modern luxury kitchen",
                "styling": (
                    "a massive waterfall-edge island in pale honed "
                    "limestone, French oak cabinetry with aged-brass "
                    "hardware, a glass-front cabinet with lit interior "
                    "shelving, and a low bowl of fruit on the island."
                ),
                "fixtures": (
                    "three aged-brass pendant lights with fluted glass "
                    "shades hung over the island, and warm under-"
                    "cabinet lighting."
                ),
            },
            "bed": {
                "stem": "e2-04_bed_frenchchateau",
                "room": GRAND_HOUSE_ROOMS["bed"],
                "style": "French Chateau interior with tall panelled "
                          "walls and ornate plaster mouldings",
                "styling": (
                    "a tall upholstered dove-grey silk headboard with "
                    "an ornate gilt frame, a large flat-screen TV "
                    "mounted flush into a boiserie panel opposite the "
                    "bed, a pair of French oak nightstands, tall silk-"
                    "draped windows, and herringbone parquet flooring "
                    "with a silk rug."
                ),
                "fixtures": (
                    "a pair of aged-brass wall sconces flanking the "
                    "bed, and a small crystal-and-gilt chandelier."
                ),
            },
            "bath": {
                "stem": "e2-04_bath_frenchchateau",
                "room": GRAND_HOUSE_ROOMS["bath"],
                "style": "French Chateau architecture fused with a "
                          "modern spa bathroom",
                "styling": (
                    "a freestanding pale limestone soaking tub beneath "
                    "a tall shuttered window, a rainfall shower behind "
                    "fluted glass, a marble-topped vanity with an aged-"
                    "brass framed mirror, and pale limestone walls and "
                    "flooring."
                ),
                "fixtures": (
                    "an aged-brass and fluted-glass pendant light over "
                    "the tub, and warm recessed lighting."
                ),
            },
            "off": {
                "stem": "e2-04_off_frenchchateau",
                "room": GRAND_HOUSE_ROOMS["off"],
                "style": "French Chateau interior with tall panelled "
                          "walls and ornate plaster mouldings",
                "styling": (
                    "floor-to-ceiling French oak bookshelves with gilt "
                    "trim lining the walls, a carved French oak writing "
                    "desk with a dove-grey silk chair, a pair of dusty-"
                    "rose velvet armchairs beside a carved limestone "
                    "fireplace, a large flat-screen TV mounted flush "
                    "into a boiserie panel beside the shelving, and "
                    "herringbone parquet flooring with a silk rug."
                ),
                "fixtures": (
                    "a small crystal-and-gilt chandelier, and a pair of "
                    "aged-brass reading lamps beside the armchairs."
                ),
            },
            "thr": {
                "stem": "e2-04_thr_frenchchateau",
                "room": GRAND_HOUSE_ROOMS["thr"],
                "style": "French Chateau architecture fused with a "
                          "modern sunken media lounge",
                "styling": (
                    "a sunken lounge area with dove-grey silk velvet "
                    "seating arranged around a large flat-screen TV set "
                    "flush into a boiserie feature wall, a limestone-"
                    "edged plunge pool along one side of the room, and "
                    "a low marble-topped table with candles."
                ),
                "fixtures": (
                    "a dimmed crystal-and-gilt chandelier, and warm LED "
                    "strip lighting tracing the sunken lounge's steps "
                    "and the pool's limestone edge."
                ),
            },
            "pool": {
                "stem": "e2-04_pool_frenchchateau",
                "room": GRAND_HOUSE_ROOMS["pool"],
                "style": "French Chateau architecture: a limestone "
                          "loggia with arched openings framing the "
                          "terrace",
                "styling": (
                    "a lit pool bordered by pale limestone paving, a "
                    "limestone loggia with arched openings running "
                    "along one side, clipped topiary in stone urns, "
                    "and aged-brass lanterns along the pool edge."
                ),
                "fixtures": (
                    "aged-brass lanterns lining the pool edge and "
                    "loggia, warm uplighting on the limestone arches, "
                    "and underwater pool lighting."
                ),
                "is_exterior": True,
            },
        },
    },

    # House #5. Dev approved e2-04 but flagged the grand-house palette had
    # drifted too pale/beige overall (esp. e2-03's oat/cream leaning) and
    # sent 6 real reference photos of what "rich earth tones" actually
    # means: saturated sage-green cabinetry against terracotta plaster,
    # deep chocolate-brown painted paneling, charcoal-navy walls, warm
    # cedar/oak wood, and live plants throughout -- SATURATED and PAINTED
    # wall colour, not just natural wood/stone tone. Named "English
    # Country" since that's the closest recognizable architecture-type
    # match for deep painted panelling + antique-leaning furniture +
    # herringbone floors + terracotta + abundant greenery shown in the
    # references, keeping this house inside the same "architecture type"
    # framing as the others rather than treating it as a bare palette swap.
    "e2-05": {
        "source_type": "Dev-provided reference photos (rich earth tones: sage/terracotta/chocolate/charcoal), architecture type: English Country",
        "style_slug": "englishcountry",
        "drive_folder_name": "English Country",
        "palette_sentence": (
            "a rich, saturated earth-tone palette carried through every "
            "room: deep sage-green and chocolate-brown painted "
            "millwork and wall panelling, warm terracotta plaster and "
            "tile, warm cedar and oak wood, aged brass fixtures, and "
            "cream boucle and linen upholstery for contrast against the "
            "deep painted walls, with abundant live potted greenery "
            "throughout."
        ),
        "light_sentence": (
            " Photographed at night, lit by warm brass fixtures and "
            "woven-shade pendant lights: the deep sage, chocolate and "
            "terracotta walls hold real saturated colour even in low "
            "light rather than reading as neutral or grey, while cream "
            "upholstery and warm wood catch the light and glow. Rich, "
            "warm and layered, with real colour depth in every shadow. "
            "No daylight, and no pale, washed-out or beige-neutral wall "
            "anywhere in frame."
        ),
        "rooms": {
            "ext": {
                "stem": "e2-05_ext_englishcountry",
                "room": GRAND_HOUSE_ROOMS["ext"],
                "style": "English Country architecture: a warm brick "
                          "and render facade with a steep tiled roof "
                          "and deep-set mullioned windows",
                "styling": (
                    "a chocolate-brown front door with aged-brass "
                    "hardware, warm terracotta brick and render "
                    "cladding, deep-set mullioned windows, climbing "
                    "greenery and potted topiary flanking the entry, "
                    "and a warm stone path."
                ),
                "fixtures": (
                    "a pair of aged-brass lantern sconces flanking the "
                    "door, and warm uplighting on the brick facade."
                ),
                "is_exterior": True,
            },
            "ent": {
                "stem": "e2-05_ent_englishcountry",
                "room": GRAND_HOUSE_ROOMS["ent"],
                "style": "English Country interior with deep painted "
                          "panelling and herringbone floors",
                "styling": (
                    "a chocolate-brown painted staircase with a warm "
                    "wood handrail, herringbone oak flooring, deep "
                    "sage-green wainscoting, an antique console table "
                    "with a large urn of foraged branches, and abundant "
                    "potted greenery."
                ),
                "fixtures": (
                    "a woven-shade brass pendant light, and aged-brass "
                    "wall sconces."
                ),
            },
            "liv": {
                "stem": "e2-05_liv_englishcountry",
                "room": GRAND_HOUSE_ROOMS["liv"],
                "style": "English Country interior with deep painted "
                          "panelling and herringbone floors",
                "styling": (
                    "a deep chocolate-brown painted wall behind a cream "
                    "boucle sectional with rust and clay-toned cushions, "
                    "a round warm-wood coffee table, a large flat-"
                    "screen TV mounted flush into a cedar wood panel, "
                    "abundant potted greenery, and herringbone oak "
                    "flooring with a warm jute rug."
                ),
                "fixtures": (
                    "a sculptural woven-and-brass chandelier, and warm "
                    "recessed lighting."
                ),
            },
            "din": {
                "stem": "e2-05_din_englishcountry",
                "room": GRAND_HOUSE_ROOMS["din"],
                "style": "English Country interior with deep painted "
                          "panelling and herringbone floors",
                "styling": (
                    "a round warm-wood dining table with cream "
                    "upholstered dining chairs, deep chocolate-brown "
                    "painted wall panelling, a pair of aged-brass wall "
                    "sconces either side of a large ceramic vessel, and "
                    "a warm patterned rug over herringbone flooring."
                ),
                "fixtures": (
                    "an aged-brass chandelier hung low over the table, "
                    "and aged-brass wall sconces along the panelled "
                    "walls."
                ),
            },
            "kit": {
                "stem": "e2-05_kit_englishcountry",
                "room": GRAND_HOUSE_ROOMS["kit"],
                "style": "English Country architecture fused with a "
                          "modern luxury kitchen",
                "styling": (
                    "deep sage-green cabinetry against a warm "
                    "terracotta plaster backsplash, a honed warm-stone "
                    "waterfall island, open wood shelving lined with "
                    "ceramics and abundant potted herbs and trailing "
                    "greenery, exposed cedar ceiling beams, and a low "
                    "bowl of fruit on the island."
                ),
                "fixtures": (
                    "a pair of woven-shade brass pendant lights hung "
                    "over the island, and warm under-shelf lighting."
                ),
            },
            "bed": {
                "stem": "e2-05_bed_englishcountry",
                "room": GRAND_HOUSE_ROOMS["bed"],
                "style": "English Country interior with deep painted "
                          "panelling and herringbone floors",
                "styling": (
                    "a warm-wood bed with a cream linen headboard "
                    "against a deep charcoal-navy painted wall, a large "
                    "flat-screen TV mounted flush into a wood panel "
                    "opposite the bed, a pair of warm-wood nightstands, "
                    "abundant potted greenery, and herringbone oak "
                    "flooring with a warm patterned rug."
                ),
                "fixtures": (
                    "a pair of aged-brass wall sconces flanking the "
                    "bed, and a woven-shade pendant light."
                ),
            },
            "bath": {
                "stem": "e2-05_bath_englishcountry",
                "room": GRAND_HOUSE_ROOMS["bath"],
                "style": "English Country architecture fused with a "
                          "modern spa bathroom",
                "styling": (
                    "a freestanding stone soaking tub against a deep "
                    "sage-green painted wall, a rainfall shower behind "
                    "fluted glass, a warm-wood vanity with a stone "
                    "vessel sink, terracotta floor tile, and potted "
                    "greenery."
                ),
                "fixtures": (
                    "a woven-shade brass pendant light over the tub, "
                    "and warm recessed lighting."
                ),
            },
            "off": {
                "stem": "e2-05_off_englishcountry",
                "room": GRAND_HOUSE_ROOMS["off"],
                "style": "English Country interior with deep painted "
                          "panelling and herringbone floors",
                "styling": (
                    "floor-to-ceiling warm-wood bookshelves against a "
                    "deep chocolate-brown painted wall, a warm-wood "
                    "writing desk with a cream upholstered chair, a "
                    "large flat-screen TV mounted flush into the "
                    "shelving, abundant potted greenery, and "
                    "herringbone flooring with a warm patterned rug."
                ),
                "fixtures": (
                    "a woven-shade brass pendant light, and a pair of "
                    "aged-brass reading lamps."
                ),
            },
            "thr": {
                "stem": "e2-05_thr_englishcountry",
                "room": GRAND_HOUSE_ROOMS["thr"],
                "style": "English Country architecture fused with a "
                          "modern sunken media lounge",
                "styling": (
                    "a sunken lounge area with cream boucle seating "
                    "against a deep charcoal-navy painted wall, a large "
                    "flat-screen TV mounted flush into a cedar wood "
                    "panel, a terracotta-tiled plunge pool along one "
                    "side of the room, and abundant potted greenery."
                ),
                "fixtures": (
                    "a dimmed sculptural woven-and-brass chandelier, "
                    "and warm recessed lighting tracing the sunken "
                    "lounge's steps."
                ),
            },
            "pool": {
                "stem": "e2-05_pool_englishcountry",
                "room": GRAND_HOUSE_ROOMS["pool"],
                "style": "English Country architecture: a warm brick "
                          "loggia with deep-set arched openings",
                "styling": (
                    "a lit pool bordered by warm terracotta paving, a "
                    "brick loggia with arched openings running along "
                    "one side, potted topiary and abundant climbing "
                    "greenery, and aged-brass lanterns along the pool "
                    "edge."
                ),
                "fixtures": (
                    "aged-brass lanterns lining the pool edge and "
                    "loggia, warm uplighting on the brick arches, and "
                    "underwater pool lighting."
                ),
                "is_exterior": True,
            },
        },
    },
}


# COMPOSITION and SPATIAL_RULE (imported above) are written specifically for
# interior three-quarter room views -- "no wide-angle distortion," "clear
# walkways," interior depth-layering language that doesn't map onto a
# building facade. e1-05's "ext" room is the first exterior shot this
# generator has ever needed, so it gets its own composition/spatial language
# rather than forcing the interior rules onto a house front.
EXTERIOR_COMPOSITION = (
    " Shot from the front walkway at a slight three-quarter angle to the "
    "facade, eye-level, as if a person had just arrived at the front door. "
    "Full building facade in frame with some sky and surrounding "
    "landscaping visible. Natural lens perspective, no fisheye or "
    "wide-angle distortion, no drone or elevated angle."
)
EXTERIOR_SPATIAL_RULE = (
    " The architecture must be geometrically coherent: walls, rooflines, "
    "windows and the front door align and read as a single real "
    "buildable structure, with no floating or interpenetrating elements. "
    "Landscaping stays clear of the front door and walkway."
)


def build_room_prompt(room, palette_sentence, light_sentence=None, styling_restraint_sentence=None):
    is_exterior = room.get("is_exterior", False)
    shot_label = "Exterior photograph" if is_exterior else "Interior photograph"
    composition = EXTERIOR_COMPOSITION if is_exterior else COMPOSITION
    spatial_rule = EXTERIOR_SPATIAL_RULE if is_exterior else SPATIAL_RULE
    return (
        f"{shot_label} of {room['room']}, {room['style']}."
        f" The space is built from exactly this palette, which is the "
        f"defining feature of the room and must be clearly visible: "
        f"{palette_sentence}"
        + (light_sentence or ROOM_LIGHT)
        + composition
        + spatial_rule
        + f" Furnished and dressed with: {room['styling']}"
        + STYLING_RULE
        + (styling_restraint_sentence or "")
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


def _response_has_image(response):
    for candidate in response.candidates:
        for part in candidate.content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                return True
    return False


def _generate_with_retry(client, model, prompt):
    import time
    from google.genai import errors as genai_errors
    from google.genai import types

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    image_config=types.ImageConfig(aspect_ratio="9:16"),
                ),
            )
        except genai_errors.ClientError as e:
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            if not is_rate_limit or attempt == MAX_RETRIES - 1:
                raise
            delay = RETRY_BASE_DELAY_S * (2 ** attempt)
            print(f"  429 rate-limited, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})...")
            time.sleep(delay)
            continue

        if _response_has_image(response):
            return response
        # Real observed quirk under retry/quota pressure (image-edit calls
        # specifically, see llms.txt): the model sometimes replies with only
        # acknowledgment text ("Here is the updated image:") and no actual
        # image part, finish_reason STOP, no error raised. Not a hard
        # failure -- retrying the identical call has produced a real image
        # on the next attempt every time this has been observed so far.
        if attempt == MAX_RETRIES - 1:
            return response
        print(f"  no image in response (model replied with text only), retrying (attempt {attempt + 1}/{MAX_RETRIES})...")
        time.sleep(5)


# e1-08 achieved structural consistency across 10 variations purely through
# repeated identical DESCRIPTION (KITCHEN_STRUCTURE) -- the only option
# available at the time, since Dev's pasted reference photo existed only as
# something visible in the conversation, not a file this script could use.
# Dev's follow-up made clear that wasn't tight enough for the actual goal (a
# fast-cut reel where the SAME structure needs to read as literally the same
# photo, not a close re-draw) and asked for true reference-image editing
# instead. That IS available now with zero new input needed from Dev: Gemini
# accepts a real image directly in `contents=[prompt, image]` (the exact
# mechanism transformation_reel/generate_concept_frames.py already uses for
# its before/mid/after chain), and e1-08's own generated images are already
# committed to this repo -- so one of THEM can be the locked pixel reference,
# with the model asked to re-render it in new materials rather than redraw
# the room from a text description each time. This is a strictly tighter
# consistency guarantee: the model is editing real pixels, not resampling
# from prose.
def build_reference_edit_prompt(palette_sentence, light_sentence):
    return (
        "Re-render this exact reference photograph with new materials, "
        "colours and lighting, while keeping every structural element "
        "identical: the same camera angle and framing, the same island "
        "shape, size and position, the same sink and faucet placement, "
        "the same number and placement of stools, the same pendant light "
        "fixtures and their positions, the same cabinetry layout, "
        "appliances and their positions, the same windows and doors in "
        "their exact positions (add no new windows or doors and remove "
        "none), and the same overall room proportions and geometry. Only "
        "the materials, colours and lighting mood should change. The new "
        "materials and colours are: "
        f"{palette_sentence}"
        + (light_sentence or "")
        + QUALITY_ROOM + NO_TEXT
    )


def generate_room(client, set_id, room_key, model=MODEL):
    set_data = ESERIES_SETS[set_id]
    room = set_data["rooms"][room_key]

    if "base_image" in set_data:
        from PIL import Image as PILImage

        base_path = OUT_DIR / set_data["base_image"]
        base_image = PILImage.open(base_path)
        prompt = build_reference_edit_prompt(
            room["palette_sentence"], room.get("light_sentence"),
        )
        print(f"--- generating {room['stem']} (image-edited from {base_path.name}) with {model} ---")
        response = _generate_with_retry(client, model, [prompt, base_image])
    else:
        prompt = build_room_prompt(
            room,
            room.get("palette_sentence", set_data.get("palette_sentence")),
            room.get("light_sentence", set_data.get("light_sentence")),
            set_data.get("styling_restraint_sentence"),
        )
        print(f"--- generating {room['stem']} with {model} ---")
        response = _generate_with_retry(client, model, prompt)

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
