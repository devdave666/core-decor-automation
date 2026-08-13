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
# d01's first room shot was rejected as "too bright for the mood." The cause was
# in the prompt, not in post: it asked for "high-contrast directional natural
# daylight through large windows" plus "crisp specular highlights," which is a
# recipe for exactly the hard diagonal sun shaft and blown highlights it produced.
#
# The second attempt removed direct sun entirely and asked for a stop and a half
# of underexposure. That killed the shaft (blown pixels 0.24% -> 0.05%) but
# crushed 34.1% of the frame to near-black, against 15-26% in the reference —
# the sofa and floor lost all detail. Dawn/dusk light plus brighter practicals is
# the correction: keep the sun soft and low, let the interior fixtures carry the
# exposure, and state explicitly that shadows keep their detail.
#
# Do not reintroduce hard directional daylight, sun shafts, or specular language
# to make a room "pop" — that exact change was rejected once already.
ROOM_LIGHT = (
    " Lit by soft low-angle dawn light through large windows — warm, gentle and "
    "heavily diffused, with no hard-edged sun shafts, no light beams and no "
    "blown-out highlights anywhere in the frame. The interior mood lighting is "
    "turned well up and does most of the work: table lamps under cream shades, "
    "brass wall sconces, picture lights above the artwork, and generous diffused "
    "ceiling light — concealed cove lighting washing the ceiling perimeter, soft "
    "recessed downlights and a warm diffused ceiling fixture — all glowing warmly "
    "at 2700K and layered so light comes from several heights at once, each source "
    "throwing its own soft pool. Shadows stay open and keep their detail rather "
    "than crushing to black. Warm, muted, gently desaturated colour grade. Calm, "
    "intimate, richly atmospheric."
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


def _generate(prompt, width, height, label):
    # Imported here, not at module scope, so that reading CONCEPTS and the prompt
    # constants — which QA tooling like check_legibility.py does — never requires
    # an HTTP library to be installed.
    import requests

    key = os.environ.get("BFL_API_KEY")
    if not key:
        raise SystemExit("BFL_API_KEY not set in environment")
    headers = {"x-key": key, "Content-Type": "application/json", "accept": "application/json"}

    r = requests.post(f"{API_BASE}/{MODEL}",
                       headers=headers,
                       json={"prompt": prompt, "width": width, "height": height,
                             "output_format": "png"},
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
            f"Interior photograph of {concept['room']}, {concept['style']}."
            + COMPOSITION
            + f" The space applies exactly these materials: {concept['materials_sentence']}"
            f" Furnished and dressed with: {concept['styling']}"
            + STYLING_RULE + ROOM_LIGHT + QUALITY_ROOM + NO_TEXT
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
}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "d01"
    out = sys.argv[2] if len(sys.argv) > 2 else f"concept_review/{which}"
    parts = sys.argv[3] if len(sys.argv) > 3 else "all"
    if which not in CONCEPTS:
        raise SystemExit(f"unknown concept {which}; known: {list(CONCEPTS)}")
    build_concept(CONCEPTS[which], out, parts)
