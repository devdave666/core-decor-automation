"""
Dolly Reel -- a NEW Core Decor content type (2026-08-18), UNVERIFIED as of
this writing (see the bottom of this docstring). Requested by Dev after
sharing a reference clip: a continuous forward dolly push-in through a room,
built here from a sequence of STATIC application photos only -- no swatches,
no swatch/application pairing logic, same "application photos only" scope as
Hot Takes.

Structurally this is Hot Takes' beat-synced-montage shape, not the original
swatch+application pipeline's: reuses the Drive Template Reels rotation for
audio AND real cut-timing (core.extract_template_cut_timestamps), one
application photo per detected cut segment, own counters
(application_index.txt, template_index.txt, caption_index.txt, all living in
this folder so this rotation never collides with the other three pipelines'
own state -- same reasoning already recorded in llms.txt for why Hot Takes
doesn't reuse the root-level counter files). compute_segment_boundaries below
is a deliberate copy of hot_takes_pipeline's function of the same name, not
an import -- sibling content-type modules in this repo only import
core_decor_reel_pipeline.py, never each other.

The ONE thing that's actually new here: instead of holding each application
photo static for its segment (Hot Takes) or alternating swatch/application
per cut (the main pipeline), each segment gets a Ken Burns PUSH-IN --
_pushin_clip() below, plain ffmpeg zoompan, no depth model.

## Why no real 2.5D/3D parallax, despite Dev's original ask naming it

Dev's brief named "2.5D Parallax Zoom" / "3D Camera Projection Push" / "Vertigo
Effect" explicitly, from a reference clip that was REAL filmed/rendered
footage (genuine parallax is free when a real camera moves through real 3D
space). A single static AI-generated photo has no depth information on its
own, so matching that look means estimating depth first. Two real prototypes
were built and tested locally (concept_tools/_test_parallax.py and
_test_layered_parallax.py, both throwaway, not part of any pipeline) against
a real application photo, using a local depth model (Depth Anything V2 Small,
CPU, ~2s/image -- the depth estimation itself was genuinely accurate, this
wasn't the problem):

1. Continuous per-pixel depth-weighted zoom (an inverse-warp trick: each
   pixel's local zoom amount scales with its own depth). Produced real
   parallax separation but visibly BENT every straight line in the shot --
   window mullions, countertop edges, cabinet fronts all curved by the final
   frame. Not acceptable against this brand's architectural photography.
2. Layered parallax (3 discrete depth bands -- background/midground/
   foreground -- each a RIGID center-zoom of the full photo, blended with
   depth-driven soft weights, the classic multiplane-camera trick). Fixed the
   bent-lines problem, but produced visible dark ghosting/double-edge halos
   at every depth boundary (around the pendant lights, the chair, the
   counter-to-window edge) -- two differently-scaled copies of the same photo
   not quite lining up where layers blend.

Both artifacts are the direct cost of skipping what genuine depth-based
parallax actually requires: true 3D reprojection (rendering from a moving
virtual camera against the depth map as a surface) PLUS inpainting the small
slivers of background revealed from behind foreground objects as the camera
pushes in -- real information that doesn't exist in a single 2D photo and
has to be synthesized. That's a real, larger piece of engineering (either a
dedicated inpainting model or a lighter OpenCV fill, neither built or tested
here) that wasn't worth the risk against an unproven payoff for a first
version. Dev's call, given the side-by-side comparison: ship the plain
Ken Burns push-in now (zero artifacts, matches the "push-in" half of the
brief exactly), leave true parallax as a possible future investment.

## Status as of this writing

**Never run end-to-end against live accounts.** Every piece was checked
individually (the Ken Burns push-in technique itself was validated in the
throwaway test above with zero geometric artifacts; this module's ffmpeg
concat + audio mux logic compiles and follows the same pattern as every
other pipeline in this repo) but no real post has gone out yet. Per Dev's
explicit instruction: the first workflow_dispatch run IS meant to be a real
live post for his review -- NOT held back behind a preview step -- and
whether this becomes a scheduled, production content type (a `schedule:`
trigger added to dolly-reel.yml, same as every other pipeline here) depends
on his approval of that first real run's actual output.
"""
import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core_decor_reel_pipeline as core  # noqa: E402  (path insert must come first)

log = logging.getLogger("dolly_reel")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

HERE = Path(__file__).resolve().parent
APPLICATION_DIR = HERE.parent / "assets" / "application"
APPLICATION_INDEX_FILE = "dolly_reel/application_index.txt"
TEMPLATE_INDEX_FILE = "dolly_reel/template_index.txt"
CAPTION_INDEX_FILE = "dolly_reel/caption_index.txt"

FPS = 30
ZOOM_RATE_PER_SECOND = 0.07  # matches the tested push-in feel: 1.0 -> 1.35 zoom over 5s
MAX_ZOOM = 1.5               # cap so a long segment never pushes in far enough to soften/pixelate
W, H = 1072, 1920            # this project's application asset size -- already 9:16, no aspect prep needed


def _snap_to_frame(t):
    return round(t * FPS) / FPS


def compute_segment_boundaries(template_cut_timestamps, duration, min_segment_s=0.5):
    """Deliberate copy of hot_takes_pipeline.compute_segment_boundaries -- see
    this module's docstring for why it's duplicated rather than imported."""
    boundaries = sorted(set(_snap_to_frame(t) for t in template_cut_timestamps if 0 < t < duration))
    while boundaries and (duration - boundaries[-1]) < min_segment_s:
        boundaries.pop()
    return [0.0] + boundaries + [duration]


def _pushin_clip(image_path, duration, output_path):
    """
    Plain Ken Burns push-in via ffmpeg's zoompan filter -- no depth model, no
    parallax. See this module's docstring for why: two depth-based prototypes
    were tested and both introduced visible geometric artifacts that this
    approach has none of.

    Scales the source 3x before zoompan (supersampling) so the crop window
    doesn't visibly soften at the most-zoomed-in frame -- same technique
    validated in the throwaway comparison test.

    x/y MUST be set explicitly -- zoompan defaults both to 0, which anchors
    the crop window at the source's top-left corner rather than its center.
    A real live run confirmed this exactly: every clip read as drifting
    toward the bottom-right instead of pushing straight into the middle,
    because the top-left corner stayed pinned in place while the rest of
    the frame grew and was pushed outward around it. The standard centered
    formula -- x='iw/2-(iw/zoom/2)', y='ih/2-(ih/zoom/2)' -- keeps the crop
    window centered on the source at every zoom level instead.
    """
    target_zoom = min(1.0 + ZOOM_RATE_PER_SECOND * duration, MAX_ZOOM)
    n_frames = max(round(duration * FPS), 1)
    increment = (target_zoom - 1.0) / n_frames

    core._run_ffmpeg(
        ["-framerate", str(FPS), "-loop", "1", "-i", str(image_path),
         "-vf", f"scale={W * 3}:{H * 3},"
                f"zoompan=z='min(zoom+{increment},{target_zoom})':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={n_frames}:s={W}x{H}:fps={FPS}",
         "-frames:v", str(n_frames), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         str(output_path)],
        f"push-in clip for {Path(image_path).name} ({duration:.2f}s, target zoom {target_zoom:.2f})",
    )
    return output_path


def _fetch_template_for_audio(repo_root, output_dir):
    """Own equivalent of core.fetch_next_template / hot_takes's own copy of the
    same -- deliberately not reused directly, see this module's docstring."""
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

        template_path, t_idx, n_templates = _fetch_template_for_audio(repo_root, tmp)
        wav_path = tmp / "audio.wav"
        core.extract_and_master_audio(template_path, wav_path)
        duration = core.get_audio_duration_seconds(wav_path)

        cut_timestamps = core.extract_template_cut_timestamps(template_path)
        boundaries = compute_segment_boundaries(cut_timestamps, duration)
        n_segments = len(boundaries) - 1
        log.info("Template produced %d segments within %.1fs", n_segments, duration)

        app_idx = core._read_counter(repo_root, APPLICATION_INDEX_FILE, default=0) % len(images)
        selected_images = [images[(app_idx + i) % len(images)] for i in range(n_segments)]
        log.info("Using application images %d-%d/%d (wrapping as needed)",
                  app_idx + 1, app_idx + n_segments, len(images))

        concat_list = tmp / "concat.txt"
        with open(concat_list, "w") as f:
            for i in range(n_segments):
                seg_duration = boundaries[i + 1] - boundaries[i]
                seg_path = tmp / f"segment_{i:03d}.mp4"
                _pushin_clip(selected_images[i], seg_duration, seg_path)
                f.write(f"file '{seg_path.as_posix()}'\n")

        silent_path = tmp / "silent.mp4"
        core._run_ffmpeg(
            ["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(silent_path)],
            f"concatenate {n_segments} push-in segments",
        )

        output_path = tmp / "dolly_reel.mp4"
        core._run_ffmpeg(
            ["-i", str(silent_path), "-i", str(wav_path),
             "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-shortest",
             "-movflags", "+faststart", str(output_path)],
            "mux push-in video with mastered audio",
        )

        core.validate_reel_for_meta(output_path, duration)

        caption, cap_idx = _get_next_caption(repo_root)

        public_url = core.upload_video_to_public_host(output_path, repo_root, media_subdir="media/dolly_reels")

        ig_id = core.publish_to_instagram(public_url, caption)
        fb_id = core.publish_to_facebook(public_url, caption, expected_duration_s=duration)
        tiktok_id = core.publish_to_buffer(public_url, caption, os.environ["BUFFER_TIKTOK_CHANNEL_ID"], "tiktok")
        yt_id = core.publish_to_buffer(public_url, caption, os.environ["BUFFER_YOUTUBE_CHANNEL_ID"], "youtube",
                                        youtube_title=caption.split("\n")[0][:100])

        core._write_and_commit_counter(
            repo_root, APPLICATION_INDEX_FILE, (app_idx + n_segments) % len(images),
            f"Dolly Reel: advance application index to {(app_idx + n_segments) % len(images)}",
        )
        core._write_and_commit_counter(
            repo_root, TEMPLATE_INDEX_FILE, (t_idx + 1) % n_templates,
            f"Dolly Reel: advance template index to {(t_idx + 1) % n_templates}",
        )
        core._write_and_commit_counter(
            repo_root, CAPTION_INDEX_FILE, cap_idx + 1,
            f"Dolly Reel: advance caption index to {cap_idx + 1}",
        )

        log.info(
            "Done. Instagram media_id=%s Facebook video_id=%s TikTok post_id=%s YouTube post_id=%s "
            "template=%d/%d segments=%d",
            ig_id, fb_id, tiktok_id, yt_id, t_idx + 1, n_templates, n_segments,
        )


if __name__ == "__main__":
    required = ["META_SYSTEM_USER_TOKEN", "META_IG_BUSINESS_ACCOUNT_ID", "META_PAGE_ID",
                "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN",
                "BUFFER_API_KEY", "BUFFER_TIKTOK_CHANNEL_ID", "BUFFER_YOUTUBE_CHANNEL_ID"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)
    run_pipeline()
