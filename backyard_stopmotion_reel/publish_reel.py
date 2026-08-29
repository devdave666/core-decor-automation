"""
Backyard landscape stop-motion reel -- publish an already-assembled reel.

Mirrors core.run_pipeline's publish fan-out exactly: hosts the mp4 via
core.upload_video_to_public_host (commits into media/reels/ on the current
branch, served from raw.githubusercontent.com), then publishes to Instagram
Reels + the Facebook Reels API + TikTok and YouTube via Buffer.

Uses a bespoke caption -- the interior-materials caption_bank doesn't fit a
backyard build -- so the shared caption_index counter is left untouched.

Usage: python backyard_stopmotion_reel/publish_reel.py <reel_mp4>
Env: GITHUB_WORKSPACE + the same META_* / BUFFER_* secrets core.run_pipeline uses.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core_decor_reel_pipeline as core  # noqa: E402

CAPTION = (
    "bought the house for the inside and completely ignored the back until now\n\n"
    "same camera, a couple hundred photos, one very long weekend with the crew. "
    "weeds to this.\n\n"
    "the pergola went up faster than i expected, the sod was the part that "
    "actually felt like magic\n\n"
    "#backyardmakeover #landscaping #beforeandafter #outdoorliving #patio"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reel_mp4", type=Path)
    args = ap.parse_args()

    repo_root = os.environ.get("GITHUB_WORKSPACE") or os.environ.get("REPO_ROOT", ".")
    duration = core.get_audio_duration_seconds(args.reel_mp4)
    core.validate_reel_for_meta(args.reel_mp4, duration)

    public_url = core.upload_video_to_public_host(args.reel_mp4, repo_root)
    print(f"hosted at {public_url}")

    ig_id = core.publish_to_instagram(public_url, CAPTION)
    fb_id = core.publish_to_facebook(public_url, CAPTION, expected_duration_s=duration)
    tiktok_id = core.publish_to_buffer(
        public_url, CAPTION, os.environ["BUFFER_TIKTOK_CHANNEL_ID"], "tiktok")
    yt_id = core.publish_to_buffer(
        public_url, CAPTION, os.environ["BUFFER_YOUTUBE_CHANNEL_ID"], "youtube",
        youtube_title=CAPTION.split("\n")[0][:100])

    print(f"Done. IG={ig_id} FB={fb_id} TikTok={tiktok_id} YouTube={yt_id}")


if __name__ == "__main__":
    main()
