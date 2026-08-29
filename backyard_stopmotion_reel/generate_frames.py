"""
Backyard landscape stop-motion reel -- frame generation.

A NEW, standalone content type (see llms.txt): one derelict suburban backyard
rebuilt into a styled outdoor living space by a two-person landscaping crew,
shown as a TRUE stop-motion sequence of photoreal stills (assembled by
assemble_reel.py), not a Veo video. "Stop motion" here means exactly what it
says -- a locked-off camera and ~16 photographs that each advance the build by
one visible step, played back "on twos". This deliberately plays to the image
model's strengths and sidesteps the frame-to-frame object-permanence failures
that Veo has hit on every transformation format in this repo (furniture_build_
reel, loft_reveal_reel, transformation_reel).

Image model: the "nano banana" high-quality path Dev asked for -- the Gemini 3
image family (gemini-3-pro-image / gemini-3.1-flash-image) at image_size="4K",
via the recipe Dev supplied on 2026-08-29 (API-key auth). Falls back to the
WIF/ADC path and to gemini-2.5-flash-image if the Gemini 3 family or the API
key isn't available -- backyard-stopmotion-probe.yml resolves which combination
actually works for this project before the first real run.

Generation is a CHAIN, not 16 independent prompts: frame 1 ("before") is
text-only; every later frame is generated from the PREVIOUS frame plus a
one-step delta instruction, with frame 1 also passed as a second reference
whose ONLY job is to hold the camera framing, fence line, house position and
the big background tree fixed (the split-reference trick from loft_reveal_reel
-- its overgrown/unfinished state must be ignored). Small per-frame drift is
acceptable and even on-aesthetic for stop-motion; gross architectural drift is
what the anchoring prevents.

Usage: python backyard_stopmotion_reel/generate_frames.py <out_dir> [--model ID]
Writes <out_dir>/frame_01.png ... frame_16.png at the model's native 4K output.
"""
import argparse
import os
import sys
import time
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image, ImageFilter

PROJECT = "project-58f4f689-36b9-406b-bfa"
# The Gemini 3 image family is served ONLY in the "global" Vertex location for
# this project -- confirmed by a region sweep (us-central1/us-east4/europe-west4
# all 404). gemini-2.5-flash-image works in any region including global, so a
# single global client covers every candidate.
LOCATION = "global"

DEFAULT_MODELS = [
    "gemini-3.1-flash-image",  # confirmed: wif:global, ~17 MP native output
    "gemini-3-pro-image",      # higher tier; rejects thinking_config
    "gemini-2.5-flash-image",  # ~1 MP fallback, upscaled
]

MAX_RETRIES = 5
RETRY_BASE_DELAY_S = 20

_SAFETY_OFF = [
    types.SafetySetting(category=c, threshold="OFF")
    for c in (
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_HARASSMENT",
    )
]


def _config_for_model(model):
    """
    Per-model, learned from real probe runs against this project:
      - gemini-3.1-flash-image: honours image_size="4K" AND thinking_config
        (probe: 3072x5504 native via wif:global).
      - gemini-3-pro-image: honours image_size but REJECTS thinking_config
        (real 400: "thinking_level MINIMAL is not supported by this model").
      - gemini-2.5-flash-image: rejects thinking_config, silently ignores
        image_size (~1 MP cap) -- minimal proven config, same as
        transformation_reel/loft_reveal_reel.
    output_mime_type is omitted everywhere: Vertex-only and PNG is the default.
    """
    if model.startswith("gemini-3"):
        cfg = dict(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="9:16", image_size="4K"),
            safety_settings=_SAFETY_OFF,
        )
        if "flash" in model:
            cfg["thinking_config"] = types.ThinkingConfig(thinking_level="MINIMAL")
        return types.GenerateContentConfig(**cfg)
    return types.GenerateContentConfig(
        image_config=types.ImageConfig(aspect_ratio="9:16"),
        safety_settings=_SAFETY_OFF,
    )

# Repeated verbatim in every delta prompt. The camera never moves and these
# landmarks never change -- they're what keeps 16 chained edits reading as one
# physical place.
LOCKED_SCENE = (
    "The camera does not move at all between frames: identical eye-level "
    "three-quarter framing from the timber deck looking out across the yard, "
    "same focal length, same horizon line. The weathered timber deck in the "
    "foreground, the single-storey house wall with its back door on the left, "
    "the property's fence line, and the one large mature tree in the far "
    "right corner all stay in exactly the same position and scale in every "
    "frame. The yard keeps the same rectangular shape and dimensions."
)

QUALITY = (
    "Photorealistic architectural exterior photography, natural daylight, "
    "believable materials and shadows, sharp focus, high dynamic range, no "
    "text, no watermark, no captions, no logos."
)

CREW = (
    "the same two landscapers throughout: one tall with a short dark beard in "
    "a grey hi-vis t-shirt, the other shorter with a sandy buzz cut in an "
    "orange hi-vis t-shirt, both in tan work trousers and boots"
)

# Frame 1: text-only establishing shot.
FRAME_01 = (
    f"{QUALITY} A neglected, overgrown suburban backyard on a flat overcast "
    f"morning. Knee-high dry brown weeds and patchy dead lawn cover the whole "
    f"yard, bare cracked-dirt patches showing through. A sagging chain-link "
    f"fence runs along the property line. One large bare-limbed mature tree "
    f"stands in the far right corner. In the foreground is a weathered grey "
    f"timber deck; on the left, the back wall of a single-storey house with a "
    f"closed back door. Eye-level three-quarter view from the deck looking out "
    f"across the yard. No people. Nothing built yet."
)

# Frames 2..16: one-step deltas, each applied to the previous frame.
DELTAS = [
    # 02
    f"Introduce {CREW}. They have just come through a gate in the fence and "
    "stand near the middle of the weedy yard looking around, sizing up the "
    "job. One holds a mattock, the other pushes an empty orange wheelbarrow. "
    "A few hand tools lean against the deck. The yard is still completely "
    "overgrown and unlandscaped.",
    # 03
    "The two landscapers are now clearing the overgrowth: one swings a "
    "brush-cutter through the tall weeds, the other rakes cut vegetation into "
    "a pile. Roughly the near half of the yard is already cut down to rough "
    "bare soil; the far half is still tall weeds. The wheelbarrow is half "
    "full of cut brush.",
    # 04
    "The whole yard is now cleared to bare brown soil -- no weeds left "
    "anywhere. One landscaper walks a plate compactor across the soil, the "
    "other drags a landscape rake levelling it flat. The ground looks graded "
    "and even. Everything else unchanged.",
    # 05
    "The crew has marked out a rectangular patio area on the bare soil "
    "directly off the deck using timber stakes and taut string lines. They "
    "are rolling out black landscape fabric inside the marked rectangle and "
    "spreading a layer of pale crushed-gravel base over it with shovels. The "
    "rest of the yard is still bare graded soil.",
    # 06
    "The crew is laying grey rectangular concrete pavers onto the gravel bed "
    "in a running-bond pattern. About one third of the patio rectangle is "
    "paved in neat rows; the rest still shows the gravel base. One landscaper "
    "kneels tapping a paver level with a rubber mallet, the other carries two "
    "pavers from a stack.",
    # 07
    "The patio is now fully paved -- a complete, level grey paver rectangle "
    "off the deck. The two landscapers push stiff brooms across it, sweeping "
    "fine jointing sand into the gaps between pavers. The rest of the yard is "
    "still bare graded soil.",
    # 08
    "A cedar pergola is going up over the finished patio. Two upright cedar "
    "posts stand plumb and braced with temporary diagonal supports; a third "
    "post lies ready on the pavers next to a drill and a stack of cedar "
    "beams. One landscaper steadies a post, the other is on a step ladder.",
    # 09
    "The cedar pergola is now fully built over the patio: four posts, "
    "perimeter beams and evenly spaced cross rafters overhead, all cedar. The "
    "temporary braces and the ladder are gone. The two landscapers stand at "
    "the edge of the patio looking up at the finished frame. The rest of the "
    "yard is still bare soil.",
    # 10
    "The crew is planting a garden border along the full length of the fence: "
    "a row of dug holes, several round boxwood shrubs and two flowering "
    "hydrangeas being lowered in, and one slender ornamental tree half "
    "planted and staked. Bags of dark bark mulch are stacked nearby. The "
    "central yard is still bare soil.",
    # 11
    "The fence border is now fully planted and topped with dark bark mulch. "
    "The crew is laying fresh turf across the central yard: about half the "
    "bare soil is now covered with tightly-butted rolls of vivid green sod, "
    "the seam line clearly visible where laid meets unlaid.",
    # 12
    "The entire central yard is now a complete, lush, even green lawn of "
    "fresh sod. One landscaper waters it with a hose on a fine spray that "
    "catches the light; the other coils up the empty sod pallet wrapping. "
    "Patio, pergola and planted border all already in place.",
    # 13
    "The crew is installing landscaping details: a curved path of flat "
    "flagstone stepping stones set into the lawn from the patio toward the "
    "back of the yard, and low bronze path-lights being pushed into the "
    "ground along it. One landscaper kneels wiring a light fitting.",
    # 14
    "The crew is placing outdoor furniture on the patio under the pergola: a "
    "low-slung grey modular sofa and two matching lounge chairs arranged "
    "around a long rectangular gas fire-pit table, and a large woven outdoor "
    "rug being unrolled underneath. One landscaper carries a cushion, the "
    "other positions a chair.",
    # 15
    "The crew is finishing the styling: plump scatter cushions and a throw "
    "arranged on the sofa, three large planted terracotta pots along the "
    "patio edge, and a string of warm Edison-bulb festoon lights being clipped "
    "along the pergola rafters. One landscaper on the ladder clips the last "
    "light; the other is coiling a hose, clearly about to leave.",
    # 16
    "Same yard at dusk, now completely finished and empty of people. The "
    "festoon lights along the pergola glow warm, the bronze path-lights are "
    "lit along the flagstone path, and low flames flicker in the fire-pit "
    "table. The grey modular sofa and lounge chairs sit styled with cushions "
    "on the woven rug, the lawn is lush, the fence border is full and "
    "mulched, the planted pots frame the patio. Deep blue twilight sky, "
    "magazine-quality twilight exterior photograph. Every tool, ladder, "
    "wheelbarrow and material pile is gone.",
]

assert len(DELTAS) == 15, "expected 15 deltas for frames 02..16"


def build_clients(model_override):
    """
    WIF/ADC only -- bills to the GCP project's credits (same as Veo), no API key.
    The Gemini 3 image family needs location="global"; gemini-2.5-flash-image
    works there too, so one global client covers everything, with us-central1
    kept only as a fallback for the 2.5 model.
    """
    models = [model_override] if model_override else list(DEFAULT_MODELS)
    clients = []
    for loc in ("global", "us-central1"):
        try:
            clients.append((f"wif:{loc}", genai.Client(
                vertexai=True, project=PROJECT, location=loc)))
        except Exception as e:  # noqa: BLE001
            print(f"[wif:{loc}] client construction failed: {e}")
    if not clients:
        raise RuntimeError("No usable genai client could be constructed")
    return clients, models


TARGET_W, TARGET_H = 1080, 1920
MAX_STORE_W = 1600  # cap stored frame width -- 17 MP is wasteful as chain input


def _finish(img):
    """
    Normalise every frame toward the reel canvas:
      - sub-1080p (gemini-2.5-flash-image's ~1 MP cap): Lanczos-upscale to
        1080x1920 + mild unsharp, the e-series' adopted step (see llms.txt).
      - oversized (gemini-3's ~17 MP native): downscale to MAX_STORE_W wide,
        still well above the 1080p final, keeping the chained-edit input and
        the artifact a sane size.
    """
    if img.width < TARGET_W:
        up = img.resize((TARGET_W, TARGET_H), Image.LANCZOS)
        return up.filter(ImageFilter.UnsharpMask(radius=2, percent=110, threshold=3))
    if img.width > MAX_STORE_W:
        h = round(img.height * MAX_STORE_W / img.width)
        return img.resize((MAX_STORE_W, h), Image.LANCZOS)
    return img


def _first_image(response):
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                return Image.open(BytesIO(inline.data)).convert("RGB")
    raise RuntimeError(f"No inline image data in response: {response!r}"[:800])


class Generator:
    """Resolves a working (auth, model) pair on the first call and reuses it."""

    def __init__(self, model_override):
        self.clients, self.models = build_clients(model_override)
        self.resolved = None  # (label, client, model)

    def _call(self, client, model, contents):
        config = _config_for_model(model)
        for attempt in range(MAX_RETRIES):
            try:
                return client.models.generate_content(
                    model=model, contents=contents, config=config
                )
            except genai_errors.ClientError as e:
                msg = str(e)
                is_rate_limit = "429" in msg or "RESOURCE_EXHAUSTED" in msg
                if not is_rate_limit or attempt == MAX_RETRIES - 1:
                    raise
                delay = RETRY_BASE_DELAY_S * (2 ** attempt)
                print(f"  429 rate-limited, retrying in {delay}s "
                      f"(attempt {attempt + 1}/{MAX_RETRIES})...")
                time.sleep(delay)

    def generate(self, contents):
        if self.resolved is not None:
            label, client, model = self.resolved
            return _finish(_first_image(self._call(client, model, contents)))
        last_err = None
        for label, client in self.clients:
            for model in self.models:
                try:
                    resp = self._call(client, model, contents)
                    img = _first_image(resp)
                except Exception as e:  # noqa: BLE001
                    print(f"  [{label}/{model}] failed: {str(e)[:300]}")
                    last_err = e
                    continue
                out = _finish(img)
                print(f"  resolved image path: {label}/{model} "
                      f"(native {img.width}x{img.height} -> stored {out.width}x{out.height})")
                self.resolved = (label, client, model)
                return out
        raise RuntimeError(f"No (auth, model) combination worked. Last error: {last_err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--model", default=None, help="force a specific model id")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    gen = Generator(args.model)

    print("--- frame 01 (establishing, text-only) ---")
    frame1 = gen.generate(FRAME_01)
    frame1.save(args.out_dir / "frame_01.png")
    print(f"saved {args.out_dir / 'frame_01.png'} ({frame1.width}x{frame1.height})")

    anchor_note = (
        "The SECOND reference image is ONLY for locking the camera framing, the "
        "deck, the house wall and back door on the left, the fence line and the "
        "large tree in the far right corner -- ignore its overgrown, unbuilt, "
        "unlandscaped state entirely; the current state of the build is defined "
        "by the FIRST reference image."
    )

    prev = frame1
    for i, delta in enumerate(DELTAS, start=2):
        print(f"--- frame {i:02d} ---")
        prompt = (
            f"Edit the FIRST reference image. Keep it identical except for one "
            f"step of progress: {delta} {LOCKED_SCENE} {anchor_note} "
            f"Keep {CREW} consistent in appearance across frames. {QUALITY}"
        )
        img = gen.generate([prompt, prev, frame1])
        img.save(args.out_dir / f"frame_{i:02d}.png")
        print(f"saved {args.out_dir / f'frame_{i:02d}.png'} ({img.width}x{img.height})")
        prev = img

    print(f"\nDone -- 16 frames in {args.out_dir}")


if __name__ == "__main__":
    main()
