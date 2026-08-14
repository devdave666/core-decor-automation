"""
Generates ONE three-band concept pair (band-swatch card + matching room shot)
via the BFL FLUX API, then labels the card and commits nothing — the calling
workflow handles git.

RUNS INSIDE GITHUB ACTIONS BY DESIGN. BFL_API_KEY lives in GitHub Actions
secrets, and that API is write-only — a value can be set but never read back,
and there is no local copy. Rather than move the secret out of the secret store
just so it could be used locally, generation runs where the secret already is
and commits the finished images back to the repo for review. Trigger via
workflow_dispatch on generate-concept.yml.

BFL API specifics worth not rediscovering:
- Auth header is `x-key`, NOT `Authorization: Bearer`.
- POST returns {id, polling_url}; you must poll the RETURNED polling_url, not a
  URL you construct yourself — the global endpoint load-balances across clusters.
- Poll status values are Pending / Ready / Error.
- The result URL EXPIRES IN 10 MINUTES. Download bytes immediately on Ready;
  never store or reuse the URL.
- Dimensions should be multiples of 32.
"""

import os
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from band_swatch import compose_band_swatch  # noqa: E402
from ocr_verify import find_text  # noqa: E402

API_BASE = "https://api.bfl.ai/v1"
MODEL = "flux-2-pro"
FINAL_W, FINAL_H = 1080, 1920
BAND_W, BAND_H = 1024, 608      # ~1080x640 band aspect, multiples of 32
ROOM_W, ROOM_H = 1088, 1920     # ~9:16, multiples of 32

# How many times one image may be re-rolled when the no-text check trips before
# the whole concept is failed. Per-image, not per-concept — see _generate_clean.
MAX_TEXT_RETRIES = 3

NO_TEXT = (
    " Absolutely no text, no labels, no lettering, no words, no writing, no captions, "
    "no watermarks, no logos, no signage, no numbers anywhere in the image."
)

# Two separate camera/finish directions, deliberately NOT one shared string.
# The band textures want maximum micro-contrast to make grain, veining and pile
# legible at macro distance. A room wants the opposite: the same phrasing on a
# room shot is what produced d01's blown-out interior (see ROOM_LIGHT below).
QUALITY_TEXTURE = (
    " Shot on Hasselblad H6D-100c, f/8, ISO 50, maximum depth of field, tack-sharp "
    "focus across the entire frame, high micro-contrast, crisp surface detail, no "
    "lens noise, no motion blur, no CGI smoothness."
)

QUALITY_ROOM = (
    " Shot on Hasselblad H6D-100c, 50mm lens, f/5.6, tripod-mounted long exposure, "
    "photorealistic, fine natural film grain, no lens flare, no motion blur, no CGI "
    "smoothness."
)

# BAND TEXTURES MUST BE EVENLY LIT — this is a legibility requirement, not taste.
#
# The band prompt used to ask for "subtle low-angle raking light revealing the
# surface relief" plus a "deep, rich, saturated, moody dark colour grade". Both
# fought the format. Raking light bakes vignettes and hot stripes into a tile that
# is then used as a TYPOGRAPHIC BACKGROUND, and the labels are what suffer: d04's
# chalk limestone came back blotched near-black in places, which swallowed the end
# of its own label whole (see label_swatch.py's CONTRAST HALO block). The moody
# grade also darkened tiles well below the colour of the same material in the room
# shot, loosening the 1:1 swatch-to-room match the format is built on — d02's
# walnut and travertine drifted 71 and 79 in RGB distance where its evenly-lit
# limewash drifted 14.
#
# The reference reel's own cards are flat, even and calm. This matches them.
BAND_LIGHT = (
    " Perfectly even, flat, shadowless studio illumination across the entire frame, "
    "identical brightness corner to corner, no vignetting, no hot spots, no bright "
    "stripes, no dark blotches, no strong directional or raking light, no cast "
    "shadows. The material's own colour is true and consistent across the whole "
    "surface. Natural, accurate, neutral colour — neither darkened nor artificially "
    "saturated. Fine surface relief stays visible through texture detail alone "
    "rather than through dramatic lighting."
)

# THE LIGHTING DIRECTION IS THE WHOLE POINT OF THIS CONSTANT — read before editing.
#
# V4, AND THE REASON IS MEASURED, NOT A MOOD SWING. v3 (dawn light, practicals up)
# was approved on d01 and then quietly drifted the whole series bright. Measured
# across every concept's room shot, mean luminance / crushed %:
#     d01 84.5 / 16.8   d02 111.6 / 2.6   d03 81.7 / 2.2   d04 102.3 / 2.8
#     d05 94.5 / 7.2    d06 133.2 / 3.4   d07 112.8 / 2.4
# against a reference-reel target of mean L 63-71 and crushed 15-26%. Only d01 was
# ever close. The crushed figure is the telling one: it collapsed from 16.8% to
# 2-3%, meaning the later rooms contain almost no deep shadow at all, which is
# exactly why they read flat and lit rather than atmospheric. Dev's note was that
# he prefers it "a little darker... morning, late evening or night, so the
# lighting is soft and the room looks more aesthetically" — a standing preference,
# not a one-off on d07.
#
# THE LEVER IS TIME OF DAY AND SHADOW FALLOFF, NOT EXPOSURE. This is the whole
# lesson of the rejected versions below and must not be relearned:
#   v1 — "high-contrast directional daylight" + "crisp specular highlights":
#        hard diagonal sun shaft, blown highlights. Rejected "too bright for the
#        mood" — despite being the DARKEST image of that set by mean luminance
#        (57.8). A hard shaft reads bright even when the frame average is low.
#   v2 — direct sun removed, "underexposed roughly one and a half stops":
#        killed the shaft but crushed 34.1% of the frame to near-black; sofa and
#        floor lost all detail. Rejected as too dark. GLOBAL UNDEREXPOSURE IS NOT
#        THE LEVER — it was never an exposure problem.
#   v3 — soft low-angle dawn, practicals up, shadows explicitly detailed.
#        Approved on d01, then drifted bright across d02-d07 as above.
#   v4 — this one. Moves the hour from dawn to late dusk so the ambient daylight
#        contribution is genuinely small, makes the practicals the main source
#        rather than merely "turned up", and asks for real falloff into deep
#        shadow WHILE explicitly keeping detail in it — the one thing v2 got
#        wrong. Aim: mean L back toward 70-85 with crushed back up to 15-25%,
#        without reintroducing v1's blown highlights.
#
# Do not reintroduce hard directional daylight, sun shafts, or specular language
# to make a room "pop". That exact change has already been rejected once.
#
# SECOND RULE, LEARNED SEPARATELY:
# ROOM_LIGHT DESCRIBES LIGHT QUALITY ONLY — NO SPECIFIC FIXTURES. Each concept
# names its own in a "fixtures" field, the same way it names its own styling.
# This constant used to hardcode "table lamps under cream shades" and "picture
# lights above the artwork" for every room in the series, and d05 (a BATHROOM)
# duly came back with two table lamps and a framed picture. Keep fixture nouns
# out of here.
# V5 — v4 was directionally right and far too timid. Measured on d07: mean L moved
# only 112.8 -> 108.0 and crushed only 2.4% -> 6.9%, against targets of 70-85 and
# 15-25%. It also came back COOL and overcast-looking rather than warm, because it
# still asked for lingering window daylight in a room full of cream boucle and pale
# marble. Two fixes, applied together:
#   1. WORDING: stop hedging. "Late dusk with dim daylight still at the windows"
#      leaves the model an ambient-daylight excuse, and with a high-reflectance
#      palette it takes it. v5 says night, windows dark, no daylight at all, lamps
#      are the ONLY source, most of the frame in deep shadow. The detail-in-shadow
#      clause stays and is load-bearing — it is the one thing that stops this
#      becoming v2, which crushed 34.1% of the frame to black and was rejected.
#   2. POSITION: this constant is now emitted near the FRONT of the room prompt,
#      right after the room and style, instead of ~400 words in. BFL's guide is
#      explicit that FLUX.2 weights earlier prompt elements more heavily, and at
#      571 words this prompt has plenty of room to bury an instruction. Lighting
#      is currently the failing axis, so it gets the early slot.
# V6 — v5 WAS WRONG ABOUT WHAT IT WAS ASKING FOR, not merely too weak.
#
# v3/v4/v5 chased DARKNESS: dawn, then dusk, then "night, windows dark, no
# daylight anywhere, most of the frame in deep shadow." Dev's verdict on the
# result was blunt and correct — "very dark and has no lighting at all."
#
# The mistake: aesthetic interior lighting is about CONTRAST BETWEEN WARM LIT
# POOLS AND COOL SHADOW, not about how little light there is. Every source on
# moody interior work says the same thing and v5 violated the central one:
#   - The defining move is WARM 2700K INTERIOR LIGHT AGAINST COOL BLUE TWILIGHT
#     AT THE WINDOWS. v5 said the windows were dark with no daylight at all,
#     which deleted the exact contrast that creates the effect.
#   - Lamps go at three or four DIFFERENT HEIGHTS so the room reads as warm
#     pools, with overhead light dimmed or out of frame.
#   - Shadows should be tinted COOL BLUE against warm golden highlights; that
#     colour opposition is what reads as "aesthetic" rather than merely dim.
#   - Texture — bouclé, brass, plaster, stone — catching raking lamplight is
#     much of the richness.
#
# A room can be BRIGHT in average luminance and still look beautifully lit, and
# a dark room with no visible sources looks like a photograph of a switched-off
# room. Chase visible warm sources and falloff, never a target darkness. See the
# exposure section in llms.txt for why grading in post cannot substitute for this.
ROOM_LIGHT = (
    " Photographed at blue hour just after sunset, with every light in the room "
    "switched on: through the windows the sky is deep cool blue twilight, while "
    "the room's own warm 2700K practical lamps light the interior. The lamps are "
    "layered at three or four different heights and each one glows visibly and "
    "throws its own soft golden pool of light across the surfaces nearest it, "
    "falling away gradually into shadow, so the room is lit in warm pools rather "
    "than flatly from overhead. The contrast between that warm golden interior "
    "light and the cool blue twilight at the windows is the defining quality of "
    "the photograph. Shadows are deep and softly tinted cool blue, and keep their "
    "detail and texture rather than going flat black. Bouclé, brass, plaster and "
    "stone catch the low raking lamplight and show their texture. The warm "
    "lamplight reveals the room's own materials and their true colours clearly "
    "and accurately, rather than washing everything to a uniform amber. Rich warm "
    "highlights against cool blue shadow, gently desaturated, in soft gradual "
    "gradients, with no hard-edged sun shafts, no light beams and no blown-out "
    "highlights. Cosy, intimate, glowing and richly atmospheric."
)

# WHY THIS EXISTS: the room prompt once listed only architecture — millwork,
# ceiling coves, shadow-line baseboards — and nothing else, so the model returned
# a beautifully built but completely empty showroom. Dev's note was "no photos, no
# furniture, no decorations." Naming the objects explicitly is what gets them into
# the frame; the model will not infer them from "luxury interior."
#
# DENSITY IS A SEPARATE AXIS FROM CONTENT, and this constant governs density only.
# d01's approved room went slightly the other way — busy shelves, several seats and
# a lot of small objects. The reference frame Dev singled out as the target is
# calmer: fewer, larger, well-spaced pieces with real breathing room. His words
# were "not too cramped and not too empty."
#
# The specific objects live per-concept in CONCEPTS[...]["styling"], NOT here, so
# that every room does not end up with the same olive tree and landscape painting.
# Dev asked to keep switching decor styles between concepts; a single global object
# list would quietly defeat that.
STYLING_RULE = (
    " Styled and lived-in, but never cluttered: a small number of larger, "
    "well-spaced pieces with clear breathing room between them, and generous areas "
    "of floor and wall left deliberately open. Neither sparse nor crowded — the "
    "restraint of an architectural magazine shoot."
)

# Composed in depth rather than as a flat elevation. The reference reel's rooms
# are three-quarter views with objects in the near field, which is a large part of
# why they feel inhabited; d01's dead-centre symmetrical framing read as a
# catalogue elevation by comparison. Vertical lines stay true — that part of the
# original direction was right and is kept.
COMPOSITION = (
    " Eye-level three-quarter interior view composed in layers for depth: styled "
    "objects and a piece of furniture in the near foreground, the main furniture "
    "grouping in the middle ground, and the architecture behind it. Natural true "
    "vertical lines, no wide-angle lens distortion, no fisheye."
)

# PHYSICAL COHERENCE — added after d06, whose room shot looked good enough that it
# was committed and presented for approval before Dev spotted two geometry
# failures in it that a careful look would have caught:
#   1. The console table's rear leg passed straight THROUGH the frame of the
#      rattan bench standing in front of it — two solid objects interpenetrating.
#   2. Two large urns sat squarely on the bottom stair tread, blocking the only
#      route up the staircase.
# This is the classic generative failure mode: the model composes a convincing
# flat picture without maintaining a consistent 3D scene underneath it, so solids
# pass through each other and circulation routes get furnished over. Neither
# defect is a lighting or styling problem, so no existing constant covered it.
#
# WRITTEN AFFIRMATIVELY, AND THAT IS LOAD-BEARING, NOT A STYLE CHOICE.
# BFL's own FLUX.2 prompting guide states the model does NOT support negative
# prompts — "focus on describing what you want, not what you don't want." So
# "no overlapping furniture" is the wrong shape of instruction entirely: it names
# the defect and can summon it. Every clause below states the desired end state
# (separated, resting, visible, clear, walkable) instead. If this rule ever needs
# strengthening, add more affirmative description — do not add "no ..." clauses.
#
# The negative phrasing elsewhere in this file (NO_TEXT, and the "no hot spots"
# language in BAND_LIGHT and ROOM_LIGHT) predates that finding and is left alone
# on purpose: it has five approved concepts behind it, and rewriting prompts that
# currently work would be an unvalidated change chasing a docs quote.
#
# Placed immediately after COMPOSITION so all geometry instruction sits together
# near the front of the prompt — the same guide notes FLUX.2 weights earlier
# prompt elements more heavily than later ones.
SPATIAL_RULE = (
    " The room is a physically coherent three-dimensional space. Every piece of "
    "furniture stands squarely on the floor in its own clear area of open floor, "
    "fully separate from every other piece, with a visible gap of empty floor "
    "between neighbouring pieces so each one reads as a solid, distinct object. "
    "Legs, frames and edges stay complete and clearly visible where they meet the "
    "floor, each piece passing in front of or behind its neighbours with obvious "
    "depth between them. Large objects and furniture sit back against the walls "
    "and into the corners, so that doorways, thresholds, stair treads and the main "
    "walking route through the room stay open, level and clear underfoot — a "
    "person could walk the full path and climb any stairs unobstructed."
)


def _generate(prompt, width, height, label, input_image=None):
    """
    `input_image` (base64 PNG/JPEG bytes, no data: prefix) switches this from
    text-to-image to EDITING that image — same endpoint, same auth, same polling,
    per BFL's docs. Width/height are omitted when editing so the source image's
    own dimensions carry through rather than being reinterpreted.
    """
    # Imported here, not at module scope, so that reading CONCEPTS and the prompt
    # constants — which QA tooling like check_legibility.py does — never requires
    # an HTTP library to be installed.
    import requests

    key = os.environ.get("BFL_API_KEY")
    if not key:
        raise SystemExit("BFL_API_KEY not set in environment")
    headers = {"x-key": key, "Content-Type": "application/json", "accept": "application/json"}

    payload = {"prompt": prompt, "output_format": "png"}
    if input_image is None:
        payload["width"] = width
        payload["height"] = height
    else:
        payload["input_image"] = input_image

    r = requests.post(f"{API_BASE}/{MODEL}",
                       headers=headers,
                       json=payload,
                       timeout=60)
    if r.status_code >= 400:
        raise SystemExit(f"[{label}] submit failed {r.status_code}: {r.text[:500]}")
    body = r.json()
    polling_url = body.get("polling_url")
    if not polling_url:
        raise SystemExit(f"[{label}] no polling_url in response: {body}")
    print(f"[{label}] submitted id={body.get('id')}", flush=True)

    for attempt in range(120):
        time.sleep(3)
        p = requests.get(polling_url, headers=headers, timeout=30)
        if p.status_code >= 400:
            print(f"[{label}] poll {p.status_code}: {p.text[:200]}", flush=True)
            continue
        pb = p.json()
        status = pb.get("status")
        if status == "Ready":
            result = pb.get("result") or {}
            url = result.get("sample")
            if not url:
                raise SystemExit(f"[{label}] Ready but no sample url: {pb}")
            # URL expires in 10 minutes — fetch bytes now, never cache the URL.
            img = requests.get(url, timeout=180).content
            print(f"[{label}] ready after {attempt + 1} polls, {len(img)} bytes", flush=True)
            return img
        if status in ("Error", "Failed"):
            raise SystemExit(f"[{label}] generation failed: {pb}")
    raise SystemExit(f"[{label}] timed out waiting for Ready")


def _save(img_bytes, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(img_bytes)
    return path


def _fit_final(path):
    """Normalize to exactly 1080x1920 by center-crop-to-fill (never stretch)."""
    img = Image.open(path).convert("RGB")
    scale = max(FINAL_W / img.width, FINAL_H / img.height)
    img = img.resize((max(int(img.width * scale), FINAL_W),
                       max(int(img.height * scale), FINAL_H)), Image.LANCZOS)
    left = (img.width - FINAL_W) // 2
    top = (img.height - FINAL_H) // 2
    img.crop((left, top, left + FINAL_W, top + FINAL_H)).save(path)
    return path


def _generate_clean(prompt, width, height, label, path, max_attempts=MAX_TEXT_RETRIES):
    """
    Generate, then verify the result carries no model-rendered text — re-rolling
    the SAME prompt on a hit instead of failing the whole concept.

    Generation is stochastic and the prompt already excludes text explicitly, so
    a hit is usually about this particular sample rather than this prompt. The
    first real d01 run died on band 3 of 3 (a single hit, `('Yen.', 72.0)`, on an
    oxblood velvet macro) AFTER bands 1 and 2 had already passed — and threw both
    of them away, having paid for them, without ever reaching the room shot.
    Re-rolling one band is far cheaper than restarting a concept.

    The confidence threshold in ocr_verify.py is deliberately strict and is NOT
    relaxed here — see that module for why it earned its strictness. A prompt
    that genuinely produces text still fails; it just takes max_attempts samples
    to say so instead of one.

    Every rejected sample is kept next to `path` as `<path>.rejected-<n>.png`,
    and the workflow uploads those as an artifact when the run fails. Without
    that, a tripped guard reports only THAT it fired, never whether it should
    have — the runner's working files vanish with the container, which is
    exactly what happened on the first run.
    """
    last_hits = None
    for attempt in range(1, max_attempts + 1):
        _save(_generate(prompt, width, height, label), path)
        hits = find_text(path)
        if not hits:
            print(f"[{label}] OCR clean", flush=True)
            return path
        last_hits = hits
        rejected = Path(f"{path}.rejected-{attempt}.png")
        Path(path).replace(rejected)
        tail = "regenerating" if attempt < max_attempts else "no attempts left"
        print(f"[{label}] attempt {attempt}/{max_attempts}: OCR found "
              f"model-rendered text {hits} — sample kept at {rejected}, "
              f"{tail}", flush=True)
    raise SystemExit(
        f"[{label}] still tripping the no-text check after {max_attempts} "
        f"attempts (last hits: {last_hits}). The rejected samples are kept "
        f"beside {path} and uploaded as a workflow artifact — look at them "
        f"before assuming either the guard or the prompt is at fault."
    )


def build_concept(concept, out_dir, parts="all"):
    """
    `parts` selects which halves of a concept to generate:
        "all"   — three band textures, the composed swatch card, and the room shot
        "bands" — bands and the swatch card only
        "room"  — the room shot only

    "room" exists because the two halves get approved separately in practice.
    d01's swatch was approved on the first pass while its room shot was rejected
    for being too brightly lit; regenerating the whole concept to fix the room
    would have meant paying for — and risking a re-roll of — three band textures
    that were already signed off. The swatch card is already committed, so
    nothing needs the band textures to rebuild only the room.
    """
    if parts not in ("all", "bands", "room"):
        raise SystemExit(f"unknown parts {parts!r}; expected all, bands or room")

    stem = concept["stem"]
    out_dir = Path(out_dir)
    swatch_path = out_dir / f"{stem}_swatch.png"
    app_path = out_dir / f"{stem}_app.png"

    if parts in ("all", "bands"):
        tmp = out_dir / "_textures"
        tmp.mkdir(parents=True, exist_ok=True)

        band_paths = []
        for i, band in enumerate(concept["bands"], start=1):
            label = f"{stem} band{i}"
            prompt = (
                f"Extreme close-up flat straight-on macro photograph of {band['texture']}. "
                "The material fills the entire frame edge to edge as one flat even surface, "
                "perfectly parallel to the camera, zero perspective, zero objects or props, "
                "no visible edges, borders, corners or background."
                + BAND_LIGHT + QUALITY_TEXTURE + NO_TEXT
            )
            p = _generate_clean(prompt, BAND_W, BAND_H, label, tmp / f"{stem}_band{i}.png")
            band_paths.append(p)

        compose_band_swatch(band_paths, [b["label"] for b in concept["bands"]], swatch_path)
        _fit_final(swatch_path)
        print(f"[{stem}] band swatch composed -> {swatch_path}", flush=True)

    if parts in ("all", "room"):
        out_dir.mkdir(parents=True, exist_ok=True)
        room_label = f"{stem} room"
        room_prompt = (
            # ORDER IS DELIBERATE AND HAS BEEN WRONG TWICE. FLUX.2 weights earlier
            # prompt elements more heavily, so the two things that define a
            # concept — ITS MATERIALS and ITS LIGHT — both go up front, materials
            # first.
            #
            # Lighting buried ~400 words in was obeyed only weakly (v3/v4/v5).
            # Moving it to the very front fixed the light and then broke the
            # materials instead: d07 came back beautifully lit in warm plaster and
            # brass, with its petrol lacquer, burl walnut and silver travertine
            # essentially absent. A room that does not show the concept's own
            # three materials breaks the swatch-to-room 1:1 match the whole format
            # is built on, so materials lead and lighting follows immediately.
            f"Interior photograph of {concept['room']}, {concept['style']}."
            + f" The space is built from exactly these materials, which are the "
            f"defining feature of the room and must be clearly visible: "
            f"{concept['materials_sentence']}"
            + ROOM_LIGHT
            + COMPOSITION
            + SPATIAL_RULE
            + f" Furnished and dressed with: {concept['styling']}"
            + STYLING_RULE
            + f" The room's own light fittings are: {concept['fixtures']}"
            + QUALITY_ROOM + NO_TEXT
        )
        _generate_clean(room_prompt, ROOM_W, ROOM_H, room_label, app_path)
        _fit_final(app_path)
        print(f"[{stem}] room shot -> {app_path}", flush=True)

    return swatch_path, app_path


# Each concept carries its own decor style and its own object list, because Dev
# asked to keep switching interior decor styles between concepts. Two conventions
# worth keeping as this grows:
#
# 1. VARY THE STYLE. d01 is traditional/classical; d02 is warm organic modern.
#    Don't let a new concept default to the register of the one before it.
# 2. TWO RICH BANDS PLUS ONE LIGHT NEUTRAL. Every card in the reference reel is
#    built this way (navy/cognac/warm-white, olive/walnut/ivory, plum/brass/soft-
#    ivory...). d01 is all three dark, which is why its labels never exercised
#    label_swatch's adaptive ink — with no light band there is nothing to flip to.
#    d02 onward follows the reference formula; d01 stays as approved.
CONCEPTS = {
    # APPROVED — swatch and room shot both signed off by Dev. The style/styling
    # fields below record what the approved room shot actually contained; they
    # were previously a single global constant. Don't regenerate this concept to
    # "check" them.
    "d01": {
        "stem": "d01_lib_oxblood",
        "fixtures": (
            "aged unlacquered brass picture lights above the artwork, table lamps "
            "under cream shades on the side tables, slim brass wall sconces flanking "
            "the fireplace, and concealed cove lighting along the ceiling perimeter."
        ),
        "room": "a private residential library and reading room",
        "style": "traditional classical English panelled interior",
        "styling": (
            "a large framed landscape painting lit by a brass picture light, a "
            "mature potted olive tree in a wide stoneware planter, dried branches "
            "in a ceramic vase, stacked hardback books, a turned wooden bowl, "
            "pillar candles on a tray, layered velvet and boucle cushions, a "
            "draped throw, a textured jute rug and floor-length linen curtains."
        ),
        "bands": [
            {"label": "Nero Marquina",
             "texture": "honed matte deep black Nero Marquina marble with fine crisp "
                         "white mineral veining and visible stone pores"},
            {"label": "Fumed Oak",
             "texture": "fumed smoked oak timber in deep chocolate brown with pronounced "
                         "open grain, deep timber fibres and a satin hand-oiled finish"},
            {"label": "Oxblood Velvet",
             "texture": "heavyweight deep oxblood burgundy cotton velvet with dense short "
                         "pile, soft sheen and subtle directional nap"},
        ],
        "materials_sentence": (
            "honed black Nero Marquina marble on the fireplace surround and hearth, "
            "floor-to-ceiling fumed smoked oak panelling and bookshelves in deep chocolate "
            "brown, deep oxblood burgundy velvet upholstery on the seating, and aged "
            "unlacquered brass picture lights and hardware."
        ),
    },
    "d02": {
        "stem": "d02_dine_olive",
        "fixtures": (
            "a single large hand-formed plaster pendant hung low over the dining "
            "table, two discreet plaster wall sconces, tapered candles on the table, "
            "and concealed cove lighting along the ceiling perimeter."
        ),
        "room": "a residential dining room",
        "style": "warm organic modern Mediterranean interior, soft rounded forms "
                  "and hand-finished plaster rather than panelled joinery",
        "styling": (
            "a long solid walnut dining table with sculptural rounded-back chairs, "
            "a low ceramic bowl of fruit and two tall tapered candles on the table, "
            "an oversized handmade stoneware urn holding dried pampas on a walnut "
            "sideboard, one large abstract canvas in muted earth tones, a woven "
            "rush rug, and floor-length unbleached linen curtains beside a tall "
            "window."
        ),
        "bands": [
            {"label": "Olive Limewash",
             "texture": "deep olive green limewash plaster wall with soft cloudy "
                         "tonal mottling, fine chalky matte surface and subtle "
                         "trowel texture"},
            {"label": "European Walnut",
             "texture": "solid European walnut timber in warm mid brown with "
                         "flowing cathedral grain, fine open pores and a satin "
                         "hand-rubbed oil finish"},
            {"label": "Travertine",
             "texture": "honed pale cream travertine stone with soft horizontal "
                         "banding, natural open pitting and a warm matte surface"},
        ],
        "materials_sentence": (
            "deep olive green limewash plaster on the walls, a solid European walnut "
            "dining table and sideboard in warm mid brown, honed pale cream travertine "
            "on the floor and window sill, and aged bronze hardware and lighting."
        ),
    },
    "d03": {
        "stem": "d03_suite_plum",
        "fixtures": (
            "a pair of alabaster table lamps on the nightstands, fluted brass wall "
            "sconces flanking the bed, and concealed cove lighting washing the "
            "stepped ceiling perimeter."
        ),
        "room": "a primary bedroom suite",
        "style": "restrained Art Deco interior, fluted and stepped geometric "
                  "detailing, lacquered surfaces and symmetry, glamorous but not "
                  "ornate",
        "styling": (
            "a low bed with a tall fluted upholstered headboard and crisp silk "
            "bedding, a pair of alabaster table lamps on slim lacquered "
            "nightstands, one large geometric artwork above the bed, a single "
            "sculptural vase holding two stems, a deep-pile geometric rug, and "
            "full-height silk curtains at a tall window."
        ),
        "bands": [
            {"label": "Aubergine Lacquer",
             "texture": "deep aubergine purple high-gloss lacquered plaster with a "
                         "smooth mirror-flat surface, soft depth and gentle sheen"},
            {"label": "Antique Brass",
             "texture": "aged antique brass metal sheet with fine directional "
                         "brushed grain, warm golden patina and soft tarnish "
                         "mottling"},
            {"label": "Alabaster",
             "texture": "backlit translucent white alabaster stone with soft "
                         "cloudy internal veining and a honed matte surface"},
        ],
        "materials_sentence": (
            "deep aubergine lacquered plaster on the walls, antique brushed brass on "
            "the fluted detailing, lamp bases and hardware, honed white alabaster on "
            "the nightstand tops and sill, and deep aubergine silk on the bedding."
        ),
    },
    "d04": {
        "stem": "d04_kit_indigo",
        "fixtures": (
            "two simple shaded pendants hung over the island, warm concealed task "
            "lighting beneath the open shelving, and soft recessed ceiling "
            "downlights."
        ),
        "room": "a residential kitchen",
        "style": "Belgian minimalist wabi-sabi interior, hand-finished imperfect "
                  "surfaces, honest materials, quiet and unfussy with no ornament",
        "styling": (
            "a substantial stone island with two simple wooden stools, a single "
            "large earthenware bowl of lemons, one linen tea towel over the "
            "counter edge, a short row of pewter and stoneware vessels on an open "
            "shelf, a hand-thrown vase holding bare branches, and a tall window "
            "with an unlined linen curtain drawn back."
        ),
        "bands": [
            # Dev's steer for this direction: bluer tones, textured paint. The
            # texture description leans hard on trowel and brush relief because
            # that is the requested characteristic, not incidental surface detail.
            {"label": "Indigo Limewash",
             "texture": "deep indigo slate-blue limewash paint with heavy trowel "
                         "relief, visible brush drag and layered cloudy tonal "
                         "mottling, thick chalky matte surface"},
            {"label": "Aged Elm",
             "texture": "aged reclaimed elm timber in soft greyed honey brown with "
                         "raised weathered grain, fine surface checking and a dry "
                         "unfinished matte texture"},
            {"label": "Chalk Limestone",
             "texture": "pale chalk white limestone with a soft powdery matte "
                         "surface, faint fossil flecking and gentle tonal cloudiness"},
        ],
        "materials_sentence": (
            "deep indigo slate-blue textured limewash on the walls and cabinetry, "
            "aged reclaimed elm on the open shelving and stools, pale chalk white "
            "limestone on the island, counters and floor, and aged pewter hardware."
        ),
    },
    "d05": {
        "stem": "d05_bath_teal",
        "fixtures": (
            "a single paper lantern pendant, slim linen-shaded wall sconces, warm "
            "concealed cove lighting washing the ceiling perimeter, and discreet "
            "recessed downlights. No table lamps and no framed artwork — this is a "
            "wet room and its lighting is wall-mounted, ceiling-mounted or suspended."
        ),
        "room": "a residential primary bathroom",
        "style": "Japandi interior, Japanese-Scandinavian restraint, low "
                  "horizontal lines, precise slatted joinery and uncluttered calm",
        "styling": (
            "a low freestanding stone bath, a floor-to-ceiling slatted charred "
            "cedar screen filtering the light, one hand-thrown ceramic vessel "
            "holding a single bare branch, folded linen towels stacked on a low "
            "bench, a paper lantern pendant, and a small round wooden stool beside "
            "the bath."
        ),
        "bands": [
            {"label": "Teal Tadelakt",
             "texture": "deep teal blue polished tadelakt plaster with soft cloudy "
                         "tonal movement, a faint waxed sheen and gently undulating "
                         "hand-burnished surface"},
            {"label": "Charred Cedar",
             "texture": "shou sugi ban charred cedar timber in deep charcoal black "
                         "with a fine crackled alligator surface and soft silvery "
                         "carbon bloom"},
            {"label": "Pale Hinoki",
             "texture": "pale blonde hinoki cypress timber with fine straight even "
                         "grain, a smooth planed matte surface and warm cream tone"},
        ],
        "materials_sentence": (
            "deep teal blue polished tadelakt plaster on the walls and bath surround, "
            "charred black cedar on the slatted screen and vanity, pale blonde hinoki "
            "cypress on the bath decking and bench, and blackened steel fixtures."
        ),
    },
    "d06": {
        "stem": "d06_foyer_cobalt",
        "fixtures": (
            "a single oversized brass-and-glass lantern pendant hung down the "
            "stairwell, a pair of slim brass wall sconces flanking the console "
            "mirror, and warm concealed cove lighting along the ceiling perimeter. "
            "No table lamps and no floor lamps — this is a circulation space, not "
            "a seating room."
        ),
        "room": "a residential entry foyer with a staircase",
        "style": "Moroccan riad-inspired eclectic interior, warm hand-crafted "
                  "texture and layered pattern, arched openings and traditional "
                  "joinery, richly coloured but curated rather than cluttered",
        "styling": (
            "a slim console table beneath a large arched brass-framed mirror, a "
            "woven rattan bench along one wall with a single patterned cushion, a "
            "tall potted olive tree in a glazed cobalt ceramic planter, two or "
            "three vintage-pattern rugs layered underfoot on the stair landing, "
            "and one oversized ceramic urn standing beside the staircase."
        ),
        "bands": [
            {"label": "Cobalt Zellige",
             "texture": "hand-glazed cobalt blue zellige tile mosaic in small "
                        "square tiles with subtle glaze variation, a soft wet "
                        "sheen and fine irregular grout lines"},
            {"label": "Hammered Brass",
             "texture": "hand-hammered aged brass sheet with fine dimpled "
                        "texture, warm antique patina and soft directional sheen"},
            {"label": "Sand Limewash",
             "texture": "warm pale sand limewash plaster with soft cloudy "
                        "trowelled texture, fine chalky matte surface and gentle "
                        "tonal mottling"},
        ],
        "materials_sentence": (
            "hand-glazed cobalt blue zellige tile mosaic on the stair riser and "
            "console backsplash, hand-hammered aged brass on the mirror frame and "
            "stair hardware, and warm pale sand limewash plaster on the walls."
        ),
    },
    # d04, d05 and d06 ran indigo, teal and cobalt back to back — three matte
    # plasters in a row. This keeps Dev's bluer-tones steer but moves it into a
    # high-gloss lacquered register so the series reads as a new direction rather
    # than a fourth variation on textured blue paint. First concept written with
    # SPATIAL_RULE in place from the start.
    "d07": {
        "stem": "d07_liv_petrol",
        "fixtures": (
            "a pair of large frosted-glass globe table lamps on the flanking "
            "cabinets, one tall arced floor lamp with a polished chrome shade "
            "reaching over the seating, and warm concealed cove lighting along the "
            "ceiling perimeter."
        ),
        "room": "a residential living room",
        "style": "Italian postwar modernist interior in the Milanese manner, "
                  "sculptural rounded seating, glossy lacquered casework and "
                  "polished metal, glamorous and confident without ornament",
        "styling": (
            "a low curved modular sofa in cream boucle facing a thick oval "
            "travertine coffee table, a single sculptural lounge chair angled "
            "beside it, a long lacquered credenza against the back wall carrying "
            "two frosted-glass globe lamps and one large abstract canvas above it, "
            "a tall arced floor lamp reaching over the seating, and a low bowl of "
            "citrus on the coffee table."
        ),
        # Retuned against the APPROVED room shot, measured rather than eyeballed.
        # Hue was already right on all three (0-6 degrees off); saturation was not.
        # The walnut band came back at S=95, a fiery orange-red, against the room's
        # calmer S=63 mid-brown; the travertine band came back at S=1, dead neutral
        # grey, against the room's warm S=20 cream — and the room's stone is
        # genuinely warm, so "Silver Travertine" was the wrong name as well as the
        # wrong colour. Descriptions below aim at what the approved room actually
        # shows. See llms.txt on why hue/saturation is the right comparison here
        # and raw RGB distance is not.
        "bands": [
            {"label": "Petrol Lacquer",
             "texture": "deep dark petrol teal-blue high-gloss lacquered wood "
                        "panel with a flawless mirror-smooth surface, deep muted "
                        "blue-green colour and soft reflected sheen"},
            {"label": "Burl Walnut",
             "texture": "polished walnut burl veneer in warm mid brown with "
                        "swirling eyed figure, gentle honey and soft brown tones "
                        "rather than fiery orange, and a satin lacquered finish"},
            {"label": "Roman Travertine",
             "texture": "honed warm cream travertine stone in soft beige with fine "
                        "horizontal banding, natural open pitting and a soft matte "
                        "surface"},
        ],
        "materials_sentence": (
            "deep petrol teal-blue high-gloss lacquer on the credenza and built-in "
            "casework, polished warm brown burl walnut on the side tables and "
            "cabinet fronts, honed warm cream travertine on the coffee table and "
            "floor, and polished chrome on the lighting and furniture frames."
        ),
    },
    # BREAKS THE BLUE RUN DELIBERATELY. d04-d07 were indigo, teal, cobalt and
    # petrol - four consecutive blues off Dev's "bluer tones with textured paint"
    # steer from d04. The steer's other half is honoured instead: board-formed
    # concrete is about as textured a surface as this series has used. Flagged to
    # Dev rather than assumed; trivial to swap back to a blue if he wants it.
    #
    # Also the first concept designed entirely under ROOM_LIGHT v6, so its
    # materials are chosen knowing they will be seen under warm lamplight at blue
    # hour - raw concrete and patinated bronze both come alive under exactly that.
    "d08": {
        "stem": "d08_study_concrete",
        "fixtures": (
            "a low bronze desk lamp with a dark shade, a single tall floor lamp "
            "beside the reading chair, warm concealed lighting under the shelving, "
            "and a small picture light over the artwork."
        ),
        "room": "a private residential study and work room",
        "style": "Brutalist raw-material modernism, honest heavy materials and "
                  "strong horizontal planes, monastic and quiet rather than "
                  "aggressive, softened by textiles",
        "styling": (
            "a heavy solid desk facing into the room with a single leather chair "
            "behind it, a deep low reading armchair in oatmeal wool with a folded "
            "throw, a long built-in shelf carrying a short row of books and two "
            "dark ceramic vessels, one large dark abstract canvas, a thick wool "
            "rug, and a single sculptural stone bowl on the desk."
        ),
        "bands": [
            {"label": "Board-Formed Concrete",
             "texture": "board-formed cast concrete in warm mid grey with crisp "
                        "horizontal timber plank imprints, fine aggregate "
                        "speckling and a dry matte surface"},
            {"label": "Patinated Bronze",
             "texture": "solid patinated bronze metal with a deep warm brown "
                        "surface, soft mottled verdigris bloom and a low satin "
                        "lustre"},
            {"label": "Oatmeal Wool",
             "texture": "thick undyed oatmeal wool felt with a dense soft fibrous "
                        "nap, fine natural flecking and a warm pale cream tone"},
        ],
        "materials_sentence": (
            "board-formed cast concrete in warm mid grey on the walls and ceiling "
            "with the timber plank imprints clearly visible, patinated bronze on "
            "the shelving, desk frame and lamp bases, thick oatmeal wool on the "
            "reading chair and rug, and dark stained oak on the desk top."
        ),
    },
    # BUILT FROM A REFERENCE DEV SUPPLIED, and the first concept in the series
    # driven by real engagement data rather than taste alone: an Instagram post
    # (@styledandorganizedhome, "7 color combinations that always work") sitting at
    # 7.2k likes and 4.1k shares. Shares at that ratio matter more than likes for
    # reach, so this palette is worth treating as validated rather than guessed.
    #
    # It also puts BLUE BACK, which supersedes d08's deliberate break from the
    # indigo/teal/cobalt/petrol run — Dev picked a navy reference, so navy it is.
    #
    # Register is transitional American classic, which the series has not used.
    # Closest prior is d01, also panelled, but that is a dark oxblood-and-marble
    # LIBRARY; this is a relaxed navy-and-cognac living room. Keep them distinct:
    # d01 is formal and enclosed, this one is comfortable and layered.
    "d09": {
        "stem": "d09_liv_navy",
        "fixtures": (
            "a slim aged brass picture light over the artwork, a single brass wall "
            "sconce with a small fabric shade beside it, warm concealed strip "
            "lighting inside every bay of the built-in bookcases, and one large "
            "dark ceramic table lamp under a wide ivory shade."
        ),
        "room": "a residential living room with fitted joinery",
        "style": "transitional American classic interior, painted panelled walls "
                  "and glazed built-in bookcases, deep comfortable upholstery and "
                  "warm metals, layered and relaxed rather than formal",
        "styling": (
            "a deep ivory linen sectional sofa layered with navy velvet, cognac "
            "leather and striped cushions and a draped knitted throw, a cognac "
            "leather armchair turned into the room in the near foreground, a low "
            "black marble coffee table on a slim dark metal frame carrying a round "
            "wooden tray with a potted green plant, a stack of books and a dark "
            "bowl, a tall slender ficus tree in the corner by the window, one "
            "large soft abstract canvas in muted greys hung centrally, built-in "
            "shelves styled with books, small green plants and dark ceramics, and "
            "a thick cream textured rug over a dark herringbone wood floor."
        ),
        "bands": [
            {"label": "Navy Panelling",
             "texture": "deep navy blue painted timber panelling with a smooth "
                        "satin eggshell finish, fine flat brushwork and soft "
                        "even sheen"},
            {"label": "Cognac Leather",
             "texture": "warm cognac tan aniline leather with fine natural grain, "
                        "soft creasing and a gently burnished patina"},
            {"label": "Ivory Linen",
             # "fine visible slubbed texture" tripped the no-text guard 3/3 and
             # killed the whole concept. Slub is irregular thick flecks in the
             # yarn, which is exactly the letter-like blob pattern PSM 11 sparse
             # mode reads as sparse text. A smooth even weave is both less
             # trigger-prone AND closer to the reference sofa, which is a plain
             # cream upholstery rather than a coarse slubbed linen.
             "texture": "heavyweight ivory linen upholstery weave in warm off "
                        "white with a fine smooth even regular weave and a soft "
                        "matte surface"},
        ],
        "materials_sentence": (
            "deep navy blue painted panelling and fitted built-in bookcases, warm "
            "cognac tan leather on the armchair, ivory linen upholstery on the "
            "sectional sofa, honed black marble on the coffee table, aged brass "
            "on the picture light, sconce and hardware, and a dark stained "
            "herringbone wood floor."
        ),
    },
}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "d01"
    out = sys.argv[2] if len(sys.argv) > 2 else f"concept_review/{which}"
    parts = sys.argv[3] if len(sys.argv) > 3 else "all"
    if which not in CONCEPTS:
        raise SystemExit(f"unknown concept {which}; known: {list(CONCEPTS)}")
    build_concept(CONCEPTS[which], out, parts)
