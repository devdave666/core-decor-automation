"""
Publish an already-hosted video to ALL four channels at once -- Instagram Reels
+ the Facebook Reels API + TikTok and YouTube via Buffer -- mirroring
core.run_pipeline's fan-out exactly.

Sibling to the per-platform publish-existing-to-{instagram,facebook,tiktok,
youtube}.yml workflows: same "video_url that already exists" model (e.g. a
media/reels/ raw URL committed by core.upload_video_to_public_host), but one
dispatch instead of four. Does NOT generate content, does NOT touch any
rotation counter (caption/template/concept), does NOT advance caption_index --
the caption is passed in verbatim.

Usage: python publish_existing_all.py --url <public_video_url> --caption <text>
Env: the same META_* / BUFFER_* secrets core.run_pipeline uses.
"""
import argparse
import os

import core_decor_reel_pipeline as core


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="public URL of an already-hosted video")
    ap.add_argument("--caption", required=True, help="exact caption for every channel")
    args = ap.parse_args()

    duration = None
    try:
        # ffprobe is on the runner (installed for ffmpeg); used only to give
        # Facebook an expected-duration check, non-fatal if it can't run.
        import subprocess
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", args.url],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode == 0 and r.stdout.strip():
            duration = float(r.stdout.strip())
    except Exception as e:  # noqa: BLE001
        print(f"(could not probe duration: {e})")

    ig_id = core.publish_to_instagram(args.url, args.caption)
    fb_id = core.publish_to_facebook(args.url, args.caption, expected_duration_s=duration)
    tiktok_id = core.publish_to_buffer(
        args.url, args.caption, os.environ["BUFFER_TIKTOK_CHANNEL_ID"], "tiktok")
    yt_id = core.publish_to_buffer(
        args.url, args.caption, os.environ["BUFFER_YOUTUBE_CHANNEL_ID"], "youtube",
        youtube_title=args.caption.split("\n")[0][:100])

    print(f"Done. IG={ig_id} FB={fb_id} TikTok={tiktok_id} YouTube={yt_id}")


if __name__ == "__main__":
    main()
