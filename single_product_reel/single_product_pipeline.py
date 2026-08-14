"""
Single Product Reel — the third Core Decor content type, alongside the rotating
swatch+application reveal format (core_decor_reel_pipeline.py) and Hot Takes
(hot_takes/). Format: ONE product, sourced from a one-off Drive folder rather
than the committed assets/ pool — exactly one swatch photo plus any number of
application photos of that same product. The reel opens on the swatch, then
every subsequent cut is a RANDOM application photo (with replacement — repeats
are expected and fine, this is a one-off drop, not a rotation that needs to
guarantee even coverage).

Deliberately reuses, not reimplements, everything that isn't specific to this
format: Drive fetching, audio mastering + template cut-timing extraction, Meta/
Buffer publishing, repo hosting, and the generic git-backed counter helper — all
imported from core_decor_reel_pipeline.py one level up, same pattern hot_takes/
already established. Own template_index.txt so this rotation is independent of
both other pipelines' positions in the same Drive Template Reels folder.

Caption split, per Dev's instruction: the short link-in-bio caption
(caption_bank.get_link_in_bio_caption) goes to Instagram/Facebook/TikTok/
YouTube; the long SEO caption (caption_bank.get_pinterest_seo_caption) goes to
Pinterest only, published via Buffer since Pinterest is a Buffer-connected
channel here, same mechanism as TikTok/YouTube. See llms.txt for the caveat on
Buffer's Pinterest metadata schema being unverified — plain text + video asset
only, no board/title metadata block, since guessing at an unverified GraphQL
input field risks failing the whole mutation.

New AI sessions: read llms.txt at the repo root first, same as the other two
pipelines — this file's own design notes live there too, not duplicated here.

Usage (see .github/workflows/single-product-reel.yml):
    DRIVE_FOLDER=<folder id or full Drive URL> [PRODUCT_NAME=<override>] \\
        python single_product_reel/single_product_pipeline.py
"""

import logging
import os
import random
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core_decor_reel_pipeline as core  # noqa: E402  (path insert must come first)

log = logging.getLogger("single_product_reel")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

TEMPLATE_INDEX_FILE = "single_product_reel/template_index.txt"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def parse_folder_id(folder_id_or_url):
    """Accepts either a bare Drive folder id or a full folder URL/share link."""
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", folder_id_or_url)
    return match.group(1) if match else folder_id_or_url.strip()


def fetch_product_assets(folder_id, dest_dir):
    """
    Downloads every image in the folder, splitting swatch from application shots.
    The swatch is whichever file has "swatch" in its name (case-insensitive) —
    the naming convention this project already uses elsewhere (c01_kit_modlux_
    swatch.png etc.). If no filename matches, falls back to the first file in
    sorted order and logs a warning rather than failing outright, since a one-off
    Drive drop may not follow the naming convention exactly.
    """
    from drive_upload import download_file, list_files_in_folder

    files = list_files_in_folder(folder_id)
    images = [f for f in files if Path(f["name"]).suffix.lower() in IMAGE_EXTS]
    if len(images) < 2:
        raise core.PipelineError(
            f"Expected at least one swatch and one application photo in folder "
            f"{folder_id}, found {len(images)} image file(s)."
        )

    swatch_matches = [f for f in images if "swatch" in f["name"].lower()]
    if len(swatch_matches) == 1:
        swatch_file = swatch_matches[0]
    else:
        if len(swatch_matches) > 1:
            log.warning(
                "%d files matched 'swatch' in name — using the first alphabetically: %s",
                len(swatch_matches), swatch_matches[0]["name"],
            )
            swatch_file = swatch_matches[0]
        else:
            log.warning(
                "No filename contained 'swatch' — falling back to the first file "
                "alphabetically (%s) as the swatch. Rename the swatch file to include "
                "'swatch' to avoid relying on this fallback.",
                images[0]["name"],
            )
            swatch_file = images[0]

    application_files = [f for f in images if f["id"] != swatch_file["id"]]

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    swatch_path = dest_dir / f"swatch_{swatch_file['name']}"
    download_file(swatch_file["id"], swatch_path)

    application_paths = []
    for f in application_files:
        p = dest_dir / f"app_{f['name']}"
        download_file(f["id"], p)
        application_paths.append(p)

    log.info("Fetched 1 swatch (%s) and %d application photo(s) from folder %s",
              swatch_file["name"], len(application_paths), folder_id)
    return swatch_path, application_paths


def build_single_product_reel(template_cut_timestamps, audio_wav_path, swatch_path,
                                application_paths, output_path):
    """
    Builds a beat-synced reel: segment 0 is always the swatch (the anticipation
    beat), every following segment is a RANDOMLY chosen application photo, chosen
    WITH replacement — repeats across segments are expected, this mirrors what
    Dev asked for ("cycle through all the applications randomly even they
    repeat"), not a no-repeat shuffle. Since the swatch only ever appears in
    segment 0, the reel is guaranteed to end on an application shot for any
    template with 2+ cuts, with no parity bookkeeping needed (unlike
    core.build_reel, which alternates a fixed swatch/application PAIR and so
    does need that bookkeeping).
    """
    from moviepy import AudioFileClip, ImageClip, concatenate_videoclips

    W, H = 1080, 1920
    FPS = 30

    def snap_to_frame(t):
        return round(t * FPS) / FPS

    audio = AudioFileClip(str(audio_wav_path))
    audio_duration = audio.duration

    boundaries = sorted(set(snap_to_frame(t) for t in template_cut_timestamps if 0 <= t <= audio_duration))
    if not boundaries or boundaries[0] > 0:
        boundaries = [0.0] + boundaries
    if boundaries[-1] < audio_duration:
        boundaries.append(audio_duration)

    n_segments = len(boundaries) - 1
    if n_segments < 2:
        raise core.PipelineError(
            f"Template produced only {n_segments} segment(s) — need at least 2 "
            f"(one for the swatch, one for an application shot)."
        )

    def make_clip(image_path, duration):
        img_clip = ImageClip(str(image_path))
        scale = max(W / img_clip.w, H / img_clip.h)
        img_clip = img_clip.resized(scale)
        return img_clip.cropped(
            x_center=img_clip.w / 2, y_center=img_clip.h / 2, width=W, height=H
        ).with_duration(max(duration, 1 / FPS))

    clips = []
    for i in range(n_segments):
        duration = boundaries[i + 1] - boundaries[i]
        image_path = swatch_path if i == 0 else random.choice(application_paths)
        clips.append(make_clip(image_path, duration))

    video = concatenate_videoclips(clips, method="compose")
    video = video.with_audio(audio).with_duration(audio_duration)

    output_path = Path(output_path)
    video.write_videofile(
        str(output_path),
        fps=FPS, codec="libx264", audio_codec="aac", pixel_format="yuv420p",
        ffmpeg_params=["-movflags", "+faststart"],
        logger=None,
    )
    log.info("Single-product reel written to %s (%.1fs, %d segments, 1 swatch + %d application photos in rotation)",
              output_path, audio_duration, n_segments, len(application_paths))
    return output_path, n_segments


def _fetch_template_for_reel(repo_root, output_dir):
    """Own equivalent of core.fetch_next_template — see module docstring for why
    this isn't shared with the other two pipelines' counters."""
    from drive_upload import TEMPLATE_REELS_FOLDER_ID, download_file, list_files_in_folder

    templates = list_files_in_folder(TEMPLATE_REELS_FOLDER_ID)
    if not templates:
        raise core.PipelineError("No template reels found in the Drive Template Reels folder")

    idx = core._read_counter(repo_root, TEMPLATE_INDEX_FILE, default=0) % len(templates)
    template = templates[idx]
    log.info("Using template %d/%d for audio + cut timing: %s", idx + 1, len(templates), template["name"])

    dest = Path(output_dir) / "template.mp4"
    download_file(template["id"], dest)
    return dest, idx, len(templates)


def run_pipeline():
    from caption_bank import get_link_in_bio_caption, get_pinterest_seo_caption
    from drive_upload import get_folder_name

    folder_id = parse_folder_id(os.environ["DRIVE_FOLDER"])
    repo_root = Path(__file__).resolve().parent.parent

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        product_name = os.environ.get("PRODUCT_NAME", "").strip() or get_folder_name(folder_id)
        log.info("Product: %s (folder %s)", product_name, folder_id)

        swatch_path, application_paths = fetch_product_assets(folder_id, tmp / "assets")

        template_path, t_idx, n_templates = _fetch_template_for_reel(repo_root, tmp)
        wav_path = core.extract_and_master_audio(template_path, tmp / "audio.wav")
        cuts = core.extract_template_cut_timestamps(template_path)

        reel_path, n_segments = build_single_product_reel(
            cuts, wav_path, swatch_path, application_paths, tmp / "single_product_reel.mp4",
        )
        duration = core.get_audio_duration_seconds(wav_path)
        core.validate_reel_for_meta(reel_path, duration)

        public_url = core.upload_video_to_public_host(reel_path, repo_root, media_subdir="media/product_reels")

        link_in_bio_caption = get_link_in_bio_caption(product_name)
        pinterest_caption = get_pinterest_seo_caption(product_name)

        ig_id = core.publish_to_instagram(public_url, link_in_bio_caption)
        fb_id = core.publish_to_facebook(public_url, link_in_bio_caption, expected_duration_s=duration)
        tiktok_id = core.publish_to_buffer(
            public_url, link_in_bio_caption, os.environ["BUFFER_TIKTOK_CHANNEL_ID"], "tiktok",
        )
        yt_id = core.publish_to_buffer(
            public_url, link_in_bio_caption, os.environ["BUFFER_YOUTUBE_CHANNEL_ID"], "youtube",
            youtube_title=link_in_bio_caption.split("\n")[0][:100],
        )
        pinterest_id = core.publish_to_buffer(
            public_url, pinterest_caption, os.environ["BUFFER_PINTEREST_CHANNEL_ID"], "pinterest",
        )

        core._write_and_commit_counter(
            repo_root, TEMPLATE_INDEX_FILE, (t_idx + 1) % n_templates,
            f"Single Product Reel ({product_name}): advance template index to {(t_idx + 1) % n_templates}",
        )

        log.info(
            "Done. Instagram media_id=%s Facebook video_id=%s TikTok post_id=%s YouTube post_id=%s "
            "Pinterest post_id=%s product=%r segments=%d applications_available=%d",
            ig_id, fb_id, tiktok_id, yt_id, pinterest_id, product_name, n_segments, len(application_paths),
        )


if __name__ == "__main__":
    required = ["DRIVE_FOLDER", "META_SYSTEM_USER_TOKEN", "META_IG_BUSINESS_ACCOUNT_ID", "META_PAGE_ID",
                "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN",
                "BUFFER_API_KEY", "BUFFER_TIKTOK_CHANNEL_ID", "BUFFER_YOUTUBE_CHANNEL_ID",
                "BUFFER_PINTEREST_CHANNEL_ID"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)
    run_pipeline()
