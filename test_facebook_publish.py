"""
Isolated test: publish the already-committed test reel to Facebook via the fixed
publish_to_facebook(), and let the built-in duration verification prove or disprove
whether the upload actually delivers complete. Deliberately does NOT run the full
creative pipeline (audio extraction, beat detection, compositing) — this test exists
to answer one question only: does the resume-loop upload + duration check work when
run from real GitHub Actions infrastructure, not the proxied sandbox it was built in.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core_decor_reel_pipeline import publish_to_facebook  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

VIDEO_PATH = os.path.join(os.path.dirname(__file__), "media", "test", "final_post_reel_faststart.mp4")
EXPECTED_DURATION_S = 19.85
CAPTION = (
    "TEST POST — verifying GitHub Actions upload pipeline, please ignore.\n"
    "If you see this and the video plays fully, the fix worked."
)

if __name__ == "__main__":
    video_id = publish_to_facebook(
        VIDEO_PATH, CAPTION,
        app_id=os.environ["META_APP_ID"],
        expected_duration_s=EXPECTED_DURATION_S,
    )
    print(f"SUCCESS — Facebook video id: {video_id}")
