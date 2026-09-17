"""
Photoreal synthesis step of the 3D-to-AI-video test pipeline.

Takes the Blender blockout's reference_frame.png (villa_3d_reel/scene_setup.py)
as the image-conditioning anchor and asks Veo 3.1 to render it out as a
photoreal 9:16 clip. Same google-genai / Vertex AI client pattern as
mansion_reel/generate_veo.py and daily_villa_reel/run_daily.py -- same
project, same 429-retry-with-backoff + operation-polling shape.

Usage: villa_3d_reel/.venv313/Scripts/python.exe villa_3d_reel/generate_veo.py
   (the venv is only needed for scene_setup.py's bpy import; this script has
   no bpy dependency and also runs fine under the repo's normal interpreter)
Auth: gcloud application-default credentials (already configured locally) or
   WIF/ADC in CI, same as every other *_reel generate_veo*.py in this repo.
"""
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

HERE = Path(__file__).resolve().parent
PROJECT = "core-decor-657616"
LOCATION = "us-central1"
MODEL = "veo-3.1-fast-generate-001"

REF_FRAME = HERE / "output" / "reference_frame.png"
OUT_PATH = HERE / "output" / "final_output.mp4"

DURATION_S = 6
ASPECT_RATIO = "9:16"

MAX_RETRIES = 5
RETRY_BASE_S = 20
POLL_INTERVAL_S = 15
POLL_TIMEOUT_S = 900

PROMPT = (
    "Cinematic drone shot of a luxury Mediterranean cliffside villa patio, "
    "textured travertine stone columns, teak dining table with bowl of "
    "lemons, infinity pool overlooking sparkling turquoise sea, gentle "
    "breeze, golden hour sunlight, hyperrealistic 4k architectural "
    "walkthrough, 9:16 vertical"
)

NEGATIVE_PROMPT = (
    "text, captions, watermark, logo, ui, timestamp, letterboxing, black "
    "bars, distorted architecture, warping, morphing buildings, people, "
    "blurry, low quality, low resolution, cartoon, illustration, night, dark"
)


def submit(client, image_bytes):
    cfg = types.GenerateVideosConfig(
        aspect_ratio=ASPECT_RATIO,
        duration_seconds=DURATION_S,
        generate_audio=True,
        number_of_videos=1,
        negative_prompt=NEGATIVE_PROMPT,
    )
    image = types.Image(image_bytes=image_bytes, mime_type="image/png")
    for attempt in range(MAX_RETRIES):
        try:
            return client.models.generate_videos(
                model=MODEL, prompt=PROMPT, image=image, config=cfg)
        except genai_errors.ClientError as e:
            msg = str(e)
            if ("429" in msg or "RESOURCE_EXHAUSTED" in msg) and attempt < MAX_RETRIES - 1:
                d = RETRY_BASE_S * (2 ** attempt)
                print(f"  429 on submit, retry in {d}s")
                time.sleep(d)
                continue
            raise


def main():
    if not REF_FRAME.exists():
        raise SystemExit(f"{REF_FRAME} not found -- run scene_setup.py first")

    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    image_bytes = REF_FRAME.read_bytes()

    print(f"--- veo 3.1 fast: {DURATION_S}s, {ASPECT_RATIO} ---\n  {PROMPT[:160]}...")
    op = submit(client, image_bytes)

    waited = 0
    while not op.done:
        if waited >= POLL_TIMEOUT_S:
            raise RuntimeError("veo generation timed out")
        time.sleep(POLL_INTERVAL_S)
        waited += POLL_INTERVAL_S
        op = client.operations.get(op)
        print(f"  ...{waited}s done={op.done}")

    if getattr(op, "error", None):
        raise RuntimeError(f"veo op failed: {op.error}")

    videos = getattr(op.response, "generated_videos", None) or []
    if not videos:
        raise RuntimeError(f"no video in response: {op.response!r}"[:400])

    data = videos[0].video.video_bytes
    OUT_PATH.write_bytes(data)
    print(f"saved {OUT_PATH} ({len(data)} bytes)")

    if OUT_PATH.stat().st_size == 0:
        raise SystemExit("final_output.mp4 is empty")


if __name__ == "__main__":
    main()
