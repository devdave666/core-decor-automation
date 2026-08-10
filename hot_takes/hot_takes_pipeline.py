"""
"Hot Takes" — the second Core Decor content type, alongside the original
swatch+application reveal format in core_decor_reel_pipeline.py (untouched by this
file — nothing here imports anything that would change its behavior).

Format: ONE application photo held for the full duration, with a two-line "They: /
Me:" meme-text reveal — no swatches, no multi-image cuts. Deliberately simpler than
the reveal format: this is a hook-driven, opinion-led style, not a material-
education one, so it doesn't need cut-timing extraction or scene detection at all.

Deliberately reuses, rather than reimplements, everything that isn't specific to
this format: Drive template fetching (for audio only, not timing), Meta/Buffer
publishing, repo hosting, the caption bank, and the generic git-backed counter
helpers — all imported directly from core_decor_reel_pipeline.py one level up.
State files (application_index.txt, opinion_index.txt, caption_index.txt,
template_index.txt) live in this folder specifically so they never collide with
the original pipeline's own rotation counters at the repo root.

New AI sessions: read llms.txt at the repo root first, same as for the main
pipeline — this file's own design notes live there too, not duplicated here.
"""

import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core_decor_reel_pipeline as core  # noqa: E402  (path insert must come first)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from opinion_bank import OPINIONS  # noqa: E402
from text_overlay import render_line_png, W, H  # noqa: E402

log = logging.getLogger("hot_takes")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

HERE = Path(__file__).resolve().parent
APPLICATION_DIR = HERE.parent / "assets" / "application"
APPLICATION_INDEX_FILE = "hot_takes/application_index.txt"
OPINION_INDEX_FILE = "hot_takes/opinion_index.txt"
CAPTION_INDEX_FILE = "hot_takes/caption_index.txt"
TEMPLATE_INDEX_FILE = "hot_takes/template_index.txt"

REVEAL_DELAY_S = 1.6   # how long "They:" sits alone before "Me:" appears
MAX_DURATION_S = 7.0   # meme-style pacing is short and punchy, not a full reveal arc
LINE_GAP_PX = 24


def build_hot_take(application_image_path, opinion_pair, audio_wav_path, output_path):
    """
    Builds one Hot Takes reel: one still application photo, center-crop-filled to
    1080x1920 exactly like the main pipeline's own images (same visual language,
    intentionally), with the two-line meme text revealed in sequence.
    """
    from moviepy import ImageClip, AudioFileClip, CompositeVideoClip

    audio = AudioFileClip(str(audio_wav_path))
    duration = min(audio.duration, MAX_DURATION_S)
    audio = audio.subclipped(0, duration)

    bg = ImageClip(str(application_image_path))
    scale = max(W / bg.w, H / bg.h)
    bg = bg.resized(scale)
    bg = bg.cropped(x_center=bg.w / 2, y_center=bg.h / 2, width=W, height=H)
    bg = bg.with_duration(duration)

    setup, punchline = opinion_pair
    with tempfile.TemporaryDirectory() as tmp:
        line1_path, line1_height = render_line_png(setup, Path(tmp) / "line1.png")
        line2_path, _ = render_line_png(punchline, Path(tmp) / "line2.png",
                                          y_offset=line1_height + LINE_GAP_PX)

        line1_clip = ImageClip(str(line1_path)).with_duration(duration).with_start(0)
        line2_clip = (ImageClip(str(line2_path))
                       .with_duration(max(duration - REVEAL_DELAY_S, 0.1))
                       .with_start(min(REVEAL_DELAY_S, duration)))

        final = CompositeVideoClip([bg, line1_clip, line2_clip], size=(W, H)).with_audio(audio)
        final.write_videofile(
            str(output_path), fps=30, codec="libx264", audio_codec="aac",
            pixel_format="yuv420p", ffmpeg_params=["-movflags", "+faststart"], logger=None,
        )
    return output_path, duration


def _fetch_template_for_audio(repo_root, output_dir):
    """
    Own equivalent of core.fetch_next_template, deliberately not reused — that
    function reads the MAIN pipeline's template_index.txt by way of a hardcoded
    module-level constant, and calling it directly here would make Hot Takes
    silently ride along on whatever position the main pipeline happens to be at,
    not an independently rotating position of its own. Everything else about it
    (listing the same Drive Template Reels folder, downloading the same way) is
    identical and IS reused — only the counter file differs.
    """
    from drive_upload import TEMPLATE_REELS_FOLDER_ID, download_file, list_files_in_folder

    templates = list_files_in_folder(TEMPLATE_REELS_FOLDER_ID)
    if not templates:
        raise core.PipelineError("No template reels found in the Drive Template Reels folder")

    idx = core._read_counter(repo_root, TEMPLATE_INDEX_FILE, default=0) % len(templates)
    template = templates[idx]
    log.info("Using template %d/%d for audio: %s", idx + 1, len(templates), template["name"])

    dest = Path(output_dir) / "template.mp4"
    download_file(template["id"], dest)
    return dest, idx, len(templates)


def _get_next_caption(repo_root):
    """
    Own counter, same reasoning as _fetch_template_for_audio above: reuses
    caption_bank's actual caption content, but core.get_next_caption_and_index
    hardcodes the MAIN pipeline's caption_index.txt internally, and using it
    directly here would have both pipelines racing on the same shared pointer
    whenever they happen to run close together.
    """
    from caption_bank import get_caption
    index = core._read_counter(repo_root, CAPTION_INDEX_FILE, default=0)
    return get_caption(index), index


def run_pipeline():
    repo_root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        images = sorted(APPLICATION_DIR.glob("*.png"))
        if not images:
            raise core.PipelineError(f"No application images found in {APPLICATION_DIR}")
        app_idx = core._read_counter(repo_root, APPLICATION_INDEX_FILE, default=0) % len(images)
        image_path = images[app_idx]
        log.info("Using application image %d/%d: %s", app_idx + 1, len(images), image_path.name)

        op_idx = core._read_counter(repo_root, OPINION_INDEX_FILE, default=0) % len(OPINIONS)
        opinion_pair = OPINIONS[op_idx]
        log.info("Using opinion %d/%d: %r", op_idx + 1, len(OPINIONS), opinion_pair)

        # Reuses the Drive Template Reels rotation for AUDIO ONLY — no cut-timing
        # is extracted, this format doesn't need it. Own template_index.txt (see
        # _fetch_template_for_audio) so this rotation is fully independent of the
        # main pipeline's position in the same Drive folder.
        template_path, t_idx, n_templates = _fetch_template_for_audio(repo_root, tmp)
        wav_path = tmp / "audio.wav"
        core.extract_and_master_audio(template_path, wav_path)

        output_path = tmp / "hot_take.mp4"
        _, duration = build_hot_take(image_path, opinion_pair, wav_path, output_path)
        core.validate_reel_for_meta(output_path, duration)

        caption, cap_idx = _get_next_caption(repo_root)

        public_url = core.upload_video_to_public_host(output_path, repo_root, media_subdir="media/hot_takes")

        ig_id = core.publish_to_instagram(public_url, caption)
        fb_id = core.publish_to_facebook(public_url, caption, expected_duration_s=duration)
        tiktok_id = core.publish_to_buffer(public_url, caption, os.environ["BUFFER_TIKTOK_CHANNEL_ID"], "tiktok")
        yt_id = core.publish_to_buffer(public_url, caption, os.environ["BUFFER_YOUTUBE_CHANNEL_ID"], "youtube",
                                         youtube_title=opinion_pair[0][:100])

        core._write_and_commit_counter(repo_root, APPLICATION_INDEX_FILE, app_idx + 1,
                                        f"Hot Takes: advance application index to {app_idx + 1}")
        core._write_and_commit_counter(repo_root, OPINION_INDEX_FILE, op_idx + 1,
                                        f"Hot Takes: advance opinion index to {op_idx + 1}")
        core._write_and_commit_counter(repo_root, TEMPLATE_INDEX_FILE, (t_idx + 1) % n_templates,
                                        f"Hot Takes: advance template index to {(t_idx + 1) % n_templates}")
        core._write_and_commit_counter(repo_root, CAPTION_INDEX_FILE, cap_idx + 1,
                                        f"Hot Takes: advance caption index to {cap_idx + 1}")

        log.info("Done. Instagram media_id=%s Facebook video_id=%s TikTok post_id=%s YouTube post_id=%s "
                  "opinion=%d/%d image=%d/%d",
                  ig_id, fb_id, tiktok_id, yt_id, op_idx + 1, len(OPINIONS), app_idx + 1, len(images))


if __name__ == "__main__":
    run_pipeline()
