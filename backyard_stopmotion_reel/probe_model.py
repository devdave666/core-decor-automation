"""
One-off probe: does the "nano banana" high-quality path (Gemini 3 image family
at image_size="4K") actually work for this project, and under which auth?

Background (llms.txt): as of 2026-08-23, gemini-2.5-flash-image was the only
image model this GCP project could reach via Workload Identity Federation, it
was hard-capped ~1MP, and image_size="4K" was silently ignored. gemini-3-pro-
image / gemini-3.1-flash-image both 404'd under WIF. On 2026-08-29 Dev supplied
a working recipe that reaches the Gemini 3 family via API-KEY auth
(genai.Client(vertexai=True, api_key=os.environ["GOOGLE_CLOUD_API_KEY"])) with
image_size="4K" honored.

This probe tries, in order, whatever auth is available this run:
  1. API key  (GOOGLE_CLOUD_API_KEY set)  -> the recipe's path
  2. WIF/ADC  (PROJECT/LOCATION)          -> the path every current script uses
For each working client it tries the Gemini 3 image models then the known-good
gemini-2.5-flash-image, generates one 9:16 frame at image_size="4K", and prints
the REAL decoded pixel dimensions so we know whether 4K is actually honored.

Writes probe_<auth>_<model>.png for any success. Pure diagnostic, no pipeline.
"""
import os
import sys
from io import BytesIO

from google import genai
from google.genai import types
from PIL import Image

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "us-central1"

CANDIDATE_MODELS = [
    "gemini-3-pro-image",
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
]

PROMPT = (
    "Photorealistic architectural exterior photograph of a neglected, overgrown "
    "suburban backyard on an overcast morning: knee-high dry weeds, patchy dead "
    "lawn, a sagging chain-link fence, a large bare mature tree in the far right "
    "corner, a weathered timber deck in the foreground. Eye-level three-quarter "
    "view from the deck looking out across the yard, natural flat daylight, sharp "
    "focus, no people, no text, no watermark."
)

_SAFETY_OFF = [
    types.SafetySetting(category=c, threshold="OFF")
    for c in (
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_HARASSMENT",
    )
]


def config_for_model(model):
    # gemini-2.5-flash-image rejects thinking_config (real 400) and ignores
    # image_size; the Gemini 3 image family takes both.
    if model.startswith("gemini-3"):
        return types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio="9:16", image_size="4K", output_mime_type="image/png",
            ),
            thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
            safety_settings=_SAFETY_OFF,
        )
    return types.GenerateContentConfig(
        image_config=types.ImageConfig(aspect_ratio="9:16"),
        safety_settings=_SAFETY_OFF,
    )


def _clients():
    api_key = os.environ.get("GOOGLE_CLOUD_API_KEY")
    if api_key:
        try:
            yield "apikey", genai.Client(vertexai=True, api_key=api_key)
        except Exception as e:  # noqa: BLE001
            print(f"[apikey] client construction failed: {e}")
    try:
        yield "wif", genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    except Exception as e:  # noqa: BLE001
        print(f"[wif] client construction failed: {e}")


def _first_image_bytes(response):
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                return inline.data
    return None


def main():
    any_success = False
    for auth, client in _clients():
        for model in CANDIDATE_MODELS:
            tag = f"{auth}/{model}"
            print(f"--- trying {tag} ---")
            try:
                response = client.models.generate_content(
                    model=model, contents=PROMPT, config=config_for_model(model)
                )
            except Exception as e:  # noqa: BLE001
                print(f"  FAILED: {str(e)[:400]}")
                continue
            data = _first_image_bytes(response)
            if not data:
                print(f"  responded but no image bytes: {response!r}"[:400])
                continue
            img = Image.open(BytesIO(data))
            out = f"probe_{auth}_{model.replace('.', '_')}.png"
            with open(out, "wb") as f:
                f.write(data)
            mp = (img.width * img.height) / 1_000_000
            print(f"  SUCCESS {tag}: {img.width}x{img.height} ({mp:.2f} MP) -> {out}")
            any_success = True

    if not any_success:
        print("No (auth, model) combination produced an image.")
        sys.exit(1)


if __name__ == "__main__":
    main()
