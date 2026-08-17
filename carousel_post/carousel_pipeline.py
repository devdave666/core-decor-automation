"""
Carousel Post — the fourth Core Decor content type (2026-08-17)
=================================================================
A genuinely different shape from every other pipeline in this repo: a static
IMAGE carousel, not a video. Two images per post, always in a fixed order —
the c-series swatch first, then its own application shot second — reusing the
"swatch is the anticipation beat, application is the payoff" logic already
established for the video reels, just with no audio and no cut-timing
involved at all. No Drive, no ffmpeg, no librosa: this is the first content
type in the repo that needs none of them.

Deliberately scoped to the ORIGINAL c-series only (c01-c50), not the
darker/richer d-series that shares the same assets/swatches and
assets/application folders — c-series is what this format was asked for
against; nothing stops a d-series carousel from being a future, separate
decision the way d-series video publishing will be.

Reuses core_decor_reel_pipeline.py's Meta auth plumbing (_graph_post/
_graph_get, GRAPH_API_BASE, PipelineError), its git-committed
raw.githubusercontent.com hosting pattern, and its generic counter helpers
directly — same "genuinely shared, no reimplementation" discipline already
used by Hot Takes and Single Product Reel. Owns its OWN counters
(concept_index.txt, caption_index.txt, both living under this folder) so its
rotation position never collides with the other three pipelines' own state —
same reasoning already recorded in llms.txt for why Hot Takes doesn't reuse
the root-level counter files.

Platform scope, decided explicitly rather than guessed: Instagram (native
carousel) and Facebook (multi-photo post) are the two REQUIRED platforms —
both have real, documented carousel/multi-image support via the direct Meta
API already used throughout this project. TikTok and Pinterest are attempted
via Buffer on a best-effort basis (see
core_decor_reel_pipeline.publish_image_carousel_to_buffer's own docstring for
why that path is unverified) and a failure there does NOT fail the run.
YouTube is not attempted at all — this project's YouTube channel is wired via
Buffer for Shorts VIDEO content only, and there is no image/carousel post
surface available through that same channel; this isn't "untested", it's "not
a thing this integration can do".

Usage (see .github/workflows/carousel-post.yml):
    SWATCH_ASSETS_DIR=... APPLICATION_ASSETS_DIR=... \\
        python carousel_post/carousel_pipeline.py
"""
import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core_decor_reel_pipeline as core  # noqa: E402  (path insert must come first)
from prepare_image import prepare_carousel_image  # noqa: E402

log = logging.getLogger("carousel_post")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

CONCEPT_INDEX_FILE = "carousel_post/concept_index.txt"
CAPTION_INDEX_FILE = "carousel_post/caption_index.txt"


def _c_series_pairs(swatch_dir, application_dir):
    """Same filename-prefix pairing as every other pipeline in this repo
    (core._pair_swatches_with_applications), filtered down to the c-series
    only — the d-series shares these same two folders but is out of scope
    here."""
    pairs = core._pair_swatches_with_applications(swatch_dir, application_dir)
    c_pairs = [(s, a) for s, a in pairs if s.stem.startswith("c")]
    if not c_pairs:
        raise core.PipelineError(f"No c-series swatch/application pairs found in {swatch_dir} / {application_dir}")
    return c_pairs


def _next_caption(repo_root):
    from caption_bank import get_caption

    index = core._read_counter(repo_root, CAPTION_INDEX_FILE, default=0)
    return get_caption(index), index


def run_pipeline():
    swatch_dir = os.environ["SWATCH_ASSETS_DIR"]
    application_dir = os.environ["APPLICATION_ASSETS_DIR"]
    repo_root = os.environ.get("GITHUB_WORKSPACE") or os.environ.get("REPO_ROOT", ".")

    pairs = _c_series_pairs(swatch_dir, application_dir)
    concept_idx = core._read_counter(repo_root, CONCEPT_INDEX_FILE, default=0) % len(pairs)
    swatch_path, app_path = pairs[concept_idx]
    log.info("Concept %d/%d: %s", concept_idx + 1, len(pairs), swatch_path.stem)

    caption, caption_idx = _next_caption(repo_root)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # anchor_y=1.0: crop only ever comes off the TOP, so the swatch card's
        # material-name label (bottom fifth of frame) always survives. The
        # application shot has no such constraint, so it gets a normal
        # centered crop. See prepare_image.py for the full reasoning.
        swatch_jpg = prepare_carousel_image(swatch_path, tmp / "swatch.jpg", anchor_y=1.0)
        app_jpg = prepare_carousel_image(app_path, tmp / "application.jpg", anchor_y=0.5)

        # Swatch first, application second, in ONE push so both raw URLs go
        # live together rather than the second one racing the first commit.
        image_urls = core.upload_images_to_public_host(
            [swatch_jpg, app_jpg], repo_root, media_subdir="media/carousels",
        )

    ig_id = core.publish_carousel_to_instagram(image_urls, caption)
    fb_id = core.publish_photo_post_to_facebook(image_urls, caption)

    tiktok_channel_id = os.environ.get("BUFFER_TIKTOK_CHANNEL_ID", "").strip()
    tiktok_id = None
    if tiktok_channel_id:
        try:
            tiktok_id = core.publish_image_carousel_to_buffer(image_urls, caption, tiktok_channel_id, "tiktok")
        except Exception:
            # Non-fatal — TikTok photo-mode via Buffer has never been verified
            # against this project's account (see publish_image_carousel_to_
            # buffer's own docstring). IG/FB are the proven, required platforms
            # for this format; don't let an unverified extra path block a run
            # that otherwise worked.
            log.exception("TikTok carousel publish failed — continuing, IG/FB already succeeded")
    else:
        log.warning("BUFFER_TIKTOK_CHANNEL_ID not set — skipping TikTok carousel publish for this run.")

    pinterest_channel_id = os.environ.get("BUFFER_PINTEREST_CHANNEL_ID", "").strip()
    pinterest_id = None
    if pinterest_channel_id:
        try:
            pinterest_id = core.publish_image_carousel_to_buffer(
                image_urls, caption, pinterest_channel_id, "pinterest",
            )
        except Exception:
            log.exception("Pinterest carousel publish failed — continuing, IG/FB already succeeded")
    else:
        log.warning("BUFFER_PINTEREST_CHANNEL_ID not set — skipping Pinterest carousel publish for this run.")

    # YouTube deliberately not attempted — see module docstring.

    # Advance state only after the two REQUIRED platforms (IG, FB) confirm — a
    # failed run shouldn't burn a concept slot or a caption slot. TikTok/
    # Pinterest are best-effort and don't gate this, same as Pinterest doesn't
    # gate single_product_reel.
    core._write_and_commit_counter(
        repo_root, CONCEPT_INDEX_FILE, (concept_idx + 1) % len(pairs),
        f"Carousel Post: advance concept index to {(concept_idx + 1) % len(pairs)}",
    )
    core._write_and_commit_counter(
        repo_root, CAPTION_INDEX_FILE, caption_idx + 1,
        f"Carousel Post: advance caption index to {caption_idx + 1}",
    )

    log.info(
        "Done. Instagram media_id=%s Facebook post_id=%s TikTok post_id=%s Pinterest post_id=%s "
        "concept=%d/%d (%s)",
        ig_id, fb_id, tiktok_id, pinterest_id, concept_idx + 1, len(pairs), swatch_path.stem,
    )


if __name__ == "__main__":
    required = ["META_SYSTEM_USER_TOKEN", "META_IG_BUSINESS_ACCOUNT_ID", "META_PAGE_ID",
                "SWATCH_ASSETS_DIR", "APPLICATION_ASSETS_DIR"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)
    run_pipeline()
