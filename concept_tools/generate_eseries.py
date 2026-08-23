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


def generate_room(client, set_id, room_key, model=MODEL):
    from google.genai import types

    set_data = ESERIES_SETS[set_id]
    room = set_data["rooms"][room_key]
    prompt = build_room_prompt(
        room, set_data["palette_sentence"], set_data.get("light_sentence"),
        set_data.get("styling_restraint_sentence"),
    )

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
