"""
One-off diagnostic for test-vertex-veo.yml -- the video-generation equivalent of
discover_and_test_image_model.py. Same lesson applies: two guessed image model
names 404'd before the real one (gemini-2.5-flash-image, no "-preview") was found
by querying the project's own publisher-model catalog instead of guessing. Do the
same here rather than hardcoding a Veo model ID string off a blog post.

Lists Vertex's base/publisher models for this project/region, filters for
anything Veo-related, then tries each candidate with the CHEAPEST possible real
call: a short (4s), audio-off, text-only generation. This is a connectivity/
model-ID check, not a content generation -- keep it minimal so discovery itself
doesn't burn real money finding out what should be a one-line config change once
the right model ID is known.

Video bytes come back inline (operation.response.generated_videos[0].video.
video_bytes) when no output_gcs_uri is set in the config -- confirmed via
Google's own docs, same "if not provided, bytes are returned in the response"
pattern the image model already uses via inline_data. No GCS bucket needed for
this project; don't add one unless a real reason shows up.
"""
import time

from google import genai
from google.genai import types

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "us-central1"
# Tried in this order -- newest/cheapest-audio-capable first, falling back to
# older generations if this project's catalog doesn't have them yet.
KNOWN_CANDIDATES = [
    "veo-3.1-generate-001",
    "veo-3.1-fast-generate-001",
    "veo-3.0-generate-001",
    "veo-3.0-fast-generate-001",
    "veo-2.0-generate-001",
]
POLL_INTERVAL_S = 15
POLL_TIMEOUT_S = 300


def try_generate(client, model_id):
    print(f"--- trying {model_id} ---")
    try:
        operation = client.models.generate_videos(
            model=model_id,
            prompt="A single houseplant on a windowsill, gentle breeze moving its leaves, static camera",
            config=types.GenerateVideosConfig(
                aspect_ratio="9:16",
                duration_seconds=4,
                generate_audio=False,
                number_of_videos=1,
            ),
        )
    except Exception as e:
        print(f"  failed to start: {e}")
        return False

    waited = 0
    while not operation.done:
        if waited >= POLL_TIMEOUT_S:
            print(f"  timed out after {waited}s waiting for operation to finish")
            return False
        time.sleep(POLL_INTERVAL_S)
        waited += POLL_INTERVAL_S
        try:
            operation = client.operations.get(operation)
        except Exception as e:
            print(f"  poll failed: {e}")
            return False
        print(f"  ...polling, {waited}s elapsed, done={operation.done}")

    if getattr(operation, "error", None):
        print(f"  operation completed with error: {operation.error}")
        return False

    videos = getattr(operation.response, "generated_videos", None) or []
    if not videos:
        print(f"  no generated_videos in response: {operation.response!r}"[:1000])
        return False

    video_bytes = videos[0].video.video_bytes
    if not video_bytes:
        print("  generated_videos present but video_bytes empty -- check output_gcs_uri handling")
        return False

    with open("test_output_video.mp4", "wb") as f:
        f.write(video_bytes)
    print(f"  SUCCESS -- saved test_output_video.mp4 ({len(video_bytes)} bytes) using model {model_id}")
    return True


def main():
    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)

    print("Listing base/publisher models via client.models.list(query_base=True)...")
    candidates = []
    for m in client.models.list(config={"query_base": True}):
        name = getattr(m, "name", "") or ""
        if "veo" in name.lower():
            candidates.append(name)

    print(f"Found {len(candidates)} veo-related base models in this project's catalog:")
    for c in candidates:
        print(f"  {c}")

    model_ids = [c.split("/")[-1] for c in candidates]
    # Try catalog-confirmed IDs first (ground truth for this project), then fall
    # back to the known-name guesses in case the catalog listing missed them.
    ordered = model_ids + [c for c in KNOWN_CANDIDATES if c not in model_ids]

    if not ordered:
        print("No candidates at all -- stopping here rather than guessing blind.")
        raise SystemExit(1)

    for model_id in ordered:
        if try_generate(client, model_id):
            return
    print("No candidate model produced a video.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
