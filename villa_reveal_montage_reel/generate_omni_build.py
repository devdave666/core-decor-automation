"""
Image-to-video "gravity build" via Gemini omni, per Dev's direction: end-frame
only (no start frame), reusing omni_reel_edit/omni_edit.py's proven auth/
retry/model-candidate machinery (imported, not modified -- that file's own
edit() is video-to-video only; this adds an image-input path it doesn't have).

Usage: python villa_reveal_montage_reel/generate_omni_build.py <end_frame.png> <out.mp4>
"""
import base64
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "omni_reel_edit"))
from omni_edit import _client, _create, _collect, MODEL_CANDIDATES  # noqa: E402

PROMPT = """GRAVITY BUILD - 10-SECOND ONE-TAKE FPV
CONSTRUCTION SEQUENCE
USE THE UPLOADED REFERENCE IMAGE AS THE FINAL ARCHITECTURAL TARGET ONLY.
The uploaded reference image shows the completed final building, It is NOT the starting state.
At 00:00, the building does not exist at all. Begin with an empty construction site/background matching the Location, environment, camera perspective and surrounding context of the uploaded reference image."""


RESPONSE_FORMAT_VARIANTS = [
    {"type": "video", "aspect_ratio": "9:16"},
    {"type": "video", "delivery": "inline", "aspect_ratio": "9:16"},
    {"type": "video"},  # confirmed-working fallback shape (no aspect control)
]


def image_to_video(image_path, out_path, prompt=PROMPT):
    client = _client()
    b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    last_err = None
    for model in MODEL_CANDIDATES:
        for rf in RESPONSE_FORMAT_VARIANTS:
            print(f"--- omni image-to-video via {model} response_format={rf} ---")
            try:
                interaction, status = _create(
                    client, model,
                    input_=[
                        {"type": "text", "text": prompt},
                        {"type": "image", "data": b64, "mime_type": "image/png"},
                    ],
                    response_format=rf,
                    store=False,
                )
            except Exception as e:  # noqa: BLE001
                print(f"  FAILED: {str(e)[:500]}")
                last_err = e
                continue
            texts, videos = _collect(interaction)
            if texts:
                print(f"  model said: {' '.join(texts)[:500]}")
            if not videos:
                print(f"  status={status!r} but no video in output")
                last_err = RuntimeError("no video part in model_output")
                continue
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_bytes(videos[0])
            print(f"  wrote {out_path} ({len(videos[0])} bytes) via {model} rf={rf}")
            return
    raise RuntimeError(f"omni image-to-video produced no video. last error: {last_err}")


def main():
    if len(sys.argv) != 3:
        print("Usage: generate_omni_build.py <end_frame.png> <out.mp4>")
        raise SystemExit(1)
    image_to_video(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
