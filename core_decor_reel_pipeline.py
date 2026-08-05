"""
Core Decor Reel Pipeline
========================
Ingests a source clip, masters its audio, detects beat timing, composites a 9:16 Reel
from swatch + application image assets synced to those beats, and publishes to
Instagram and Facebook via the Meta Graph API.

STAGE 1 NOTE — read before changing the audio chain:
The original spec for this stage called for a sub-semitone pitch shift decoupled from
tempo, plus noise injected specifically below the audible threshold, framed as altering
the track's "acoustic fingerprint" while keeping it "pleasant to human ears." That
combination — imperceptible-to-humans but fingerprint-altering — is the standard
technique for slipping audio past content-matching systems (Meta's own Rights Manager
among them), not an audio-quality technique. It is not implemented here. What IS
implemented is ordinary mastering: an EQ shelf for clarity and loudness normalization to
-14 LUFS, which is simply Instagram/Spotify's own standard delivery target, nothing more.

Requires: ffmpeg binary on PATH, Python packages: librosa, moviepy, requests, numpy.
    pip install librosa moviepy requests numpy --break-system-packages

Environment variables (already configured as GitHub Actions secrets in this project —
see SECRETS_SETUP.md):
    META_SYSTEM_USER_TOKEN       Meta system user access token
    META_IG_BUSINESS_ACCOUNT_ID  Instagram professional account ID
    META_PAGE_ID                 Facebook Page ID
    GDRIVE_INPUT_PATH            Local mount/sync path to watch for source clips
    SWATCH_ASSETS_DIR            Folder of swatch images
    APPLICATION_ASSETS_DIR       Folder of application-photo images
    OUTPUT_DIR                   Where processed_audio.wav / final_output_reel.mp4 land

    No hosting/storage secret is needed: finished reels are committed straight into
    this repo's own media/reels/ folder and served for free via raw.githubusercontent.com
    — the same pattern already running in the millionchallenge repo. The repo must be
    public for that URL to work; see upload_video_to_public_host() below for why that's
    safe.
"""

import itertools
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("core_decor_reel")

GRAPH_API_VERSION = "v22.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Meta enforces these at publish time, not container-creation time, so failures show up
# late and unhelpfully unless checked ourselves first.
MAX_REEL_SECONDS = 90
MIN_REEL_SECONDS = 3
REQUIRED_ASPECT = (9, 16)


class PipelineError(Exception):
    """Raised for any stage failure that should stop the pipeline before spending a
    Meta API call — cheaper to fail loud locally than to publish something broken."""


def _run_ffmpeg(args, description):
    log.info("ffmpeg: %s", description)
    result = subprocess.run(
        ["ffmpeg", "-y", *args],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        log.error("ffmpeg failed (%s):\n%s", description, result.stderr[-2000:])
        raise PipelineError(f"ffmpeg step failed: {description}")


# ---------------------------------------------------------------------------
# STAGE 1 — Ingest & audio mastering
# ---------------------------------------------------------------------------

def find_new_clips(gdrive_input_path):
    """Returns .mp4 files present in the watched directory."""
    p = Path(gdrive_input_path)
    if not p.is_dir():
        raise PipelineError(f"GDRIVE_INPUT_PATH does not exist or isn't a directory: {p}")
    clips = sorted(p.glob("*.mp4"))
    log.info("Found %d clip(s) in %s", len(clips), p)
    return clips


def extract_and_master_audio(source_video_path, output_wav_path):
    """
    Extracts the audio track and applies ordinary mastering only:
      - a gentle high-shelf EQ lift for clarity
      - loudness normalization to -14 LUFS (Instagram/Spotify's standard target)
    No pitch manipulation, no injected noise. See module docstring for why.

    NOTE: this previously auto-detected and trimmed a trailing outro/jingle (some
    Instagram downloads append one, and it was confirmed to drag beat_track's global
    tempo estimate off for the WHOLE track, not just its own few seconds). Removed by
    request — future source tracks are expected to arrive without one. If that
    assumption stops holding, the fix is straightforward to reinstate: detect a
    sustained quiet gap in the back half of the track via RMS, trim to it before
    mastering.
    """
    source_video_path = Path(source_video_path)
    output_wav_path = Path(output_wav_path)
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)

    audio_filter = (
        "equalizer=f=8000:t=q:w=1:g=2,"   # gentle high-shelf lift for clarity
        "loudnorm=I=-14:TP=-1.5:LRA=11"    # normalize to -14 LUFS, standard IG/Spotify target
    )
    _run_ffmpeg(
        ["-i", str(source_video_path), "-vn", "-af", audio_filter,
         "-ar", "48000", "-ac", "2", str(output_wav_path)],
        f"extract + master audio from {source_video_path.name}",
    )
    log.info("Mastered audio written to %s", output_wav_path)
    return output_wav_path


def get_audio_duration_seconds(wav_path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(wav_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise PipelineError(f"ffprobe couldn't read duration of {wav_path}")
    return float(result.stdout.strip())


# ---------------------------------------------------------------------------
# STAGE 2 — Rhythm & timing extraction
# ---------------------------------------------------------------------------

def _correct_octave_error(bpm):
    """
    Beat trackers using autocorrelation/comb-filtering commonly confuse a tempo with
    its double or half — the research flagged this explicitly (90 BPM mistaken for
    180). Typical reel/background music sits in a fairly narrow practical range;
    if the raw estimate falls outside it, prefer whichever octave (as-is, doubled,
    or halved) lands inside. Returns the corrected BPM, or the original if none of
    the three candidates land in range — better to leave an unusual-but-real tempo
    alone than force it somewhere wrong.
    """
    plausible_lo, plausible_hi = 70, 160
    for candidate in (bpm, bpm * 2, bpm / 2):
        if plausible_lo <= candidate <= plausible_hi:
            return candidate
    return bpm


def extract_beat_timestamps(wav_path):
    """Loads processed_audio.wav and returns (bpm, [beat_timestamps_in_seconds])."""
    import librosa  # imported lazily: heavy dependency, only needed for this stage

    y, sr = librosa.load(str(wav_path), sr=None, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])

    corrected = _correct_octave_error(bpm)
    if corrected != bpm:
        # Relabeling the number alone would leave beat_frames aligned to the WRONG
        # tempo — actually re-track with the corrected value as a prior so the beat
        # positions themselves shift, not just the reported BPM.
        log.info("%.1f BPM looks like a likely octave error — re-tracking with a %.1f BPM prior", bpm, corrected)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, start_bpm=corrected)
        bpm = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])

    beat_timestamps = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    log.info("Detected tempo: %.1f BPM, %d beats", bpm, len(beat_timestamps))

    if not beat_timestamps or beat_timestamps[0] > 0.05:
        beat_timestamps = [0.0] + beat_timestamps
    return bpm, beat_timestamps


def extract_impact_beats(wav_path, n_impacts=4, min_gap_seconds=2.0, min_start_seconds=1.5):
    """
    Finds the N most acoustically impactful beats, not just the next N on the
    rhythmic grid. Every beat sits on the regular pulse, but only some coincide with
    a real spike in energy — a drum hit, a bass slam, a crash. This ranks each beat
    by the onset-strength envelope's value AT that beat, rather than treating all
    beats as equal, and enforces a minimum gap so selected moments are spread across
    the track rather than clustered in one loud passage.

    min_start_seconds excludes candidates too close to t=0: a track's very first
    onset is often the strongest in the whole clip simply because it's the transition
    from silence, not because it's musically special — and even a genuine hit that
    early leaves no anticipation window before the first reveal. Confirmed on a real
    test track: an early spike at 0.22s outscored everything in the first 2 seconds
    but was still weaker than later hits, and would have made the first swatch flash
    for a fifth of a second before cutting.

    Returns (bpm, [impact_timestamps_in_seconds], sorted ascending).
    """
    import librosa
    import numpy as np

    y, sr = librosa.load(str(wav_path), sr=None, mono=True)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, onset_envelope=onset_env)
    bpm = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])

    corrected = _correct_octave_error(bpm)
    if corrected != bpm:
        log.info("%.1f BPM looks like a likely octave error — re-tracking with a %.1f BPM prior", bpm, corrected)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, onset_envelope=onset_env, start_bpm=corrected)
        bpm = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])

    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)
    beat_strengths = np.interp(beat_times, onset_times, onset_env)

    ranked = np.argsort(beat_strengths)[::-1]  # strongest beat first
    selected = []
    for idx in ranked:
        t = float(beat_times[idx])
        if t < min_start_seconds:
            continue
        if all(abs(t - s) >= min_gap_seconds for s in selected):
            selected.append(t)
        if len(selected) == n_impacts:
            break

    if len(selected) < n_impacts:
        log.warning(
            "Only found %d impact beat(s) at least %.1fs apart after t=%.1fs (wanted %d) — "
            "track may be too short or too uniform. Consider lowering min_gap_seconds.",
            len(selected), min_gap_seconds, min_start_seconds, n_impacts,
        )

    selected.sort()
    log.info("Selected %d impact beats at: %s", len(selected), [round(t, 2) for t in selected])
    return bpm, selected


def build_reveal_reel(impact_beats, audio_wav_path, swatch_dir, application_dir, output_path,
                       n_pairs=4):
    """
    Builds exactly n_pairs swatch->application reveals, each timed so the cut FROM
    swatch TO its own application lands exactly on an impact beat — the payoff synced
    to the hit. The cut into the NEXT pair's swatch happens at the midpoint between
    the current impact beat and the next one, giving the application a moment to
    breathe and the next swatch a moment to build anticipation before its own reveal.
    The final application holds to the end of the audio rather than cutting away
    right after the last hit.
    """
    from moviepy import AudioFileClip, ImageClip, concatenate_videoclips

    FPS = 30

    def snap_to_frame(t):
        # Quantize every boundary to an exact frame multiple BEFORE computing any
        # duration, so rounding error is corrected at each cut rather than
        # accumulating across many concatenated clips (the research's "beats drift
        # out of sync over time" pitfall — duration-based assembly compounds
        # sub-frame rounding; snapping the boundaries themselves prevents that).
        return round(t * FPS) / FPS

    audio = AudioFileClip(str(audio_wav_path))
    audio_duration = audio.duration

    if len(impact_beats) < n_pairs:
        raise PipelineError(
            f"Need {n_pairs} impact beats, only found {len(impact_beats)}. "
            f"Lower min_gap_seconds in extract_impact_beats() or use a longer/livelier track."
        )
    impact_beats = sorted(snap_to_frame(t) for t in impact_beats[:n_pairs])

    pairs_cycle = itertools.cycle(_pair_swatches_with_applications(swatch_dir, application_dir))
    W, H = 1080, 1920

    # Chunk boundaries: chunk i runs from segment_starts[i] to segment_starts[i+1],
    # split at impact_beats[i] into swatch phase then application phase.
    segment_starts = [0.0] + [
        snap_to_frame((impact_beats[i] + impact_beats[i + 1]) / 2) for i in range(n_pairs - 1)
    ] + [audio_duration]

    def make_image_clip(image_path, duration):
        img_clip = ImageClip(str(image_path))
        scale = max(W / img_clip.w, H / img_clip.h)
        img_clip = img_clip.resized(scale)
        return img_clip.cropped(
            x_center=img_clip.w / 2, y_center=img_clip.h / 2, width=W, height=H
        ).with_duration(max(duration, 1 / 24))

    clips = []
    for i in range(n_pairs):
        swatch_path, application_path = next(pairs_cycle)
        chunk_start, chunk_end = segment_starts[i], segment_starts[i + 1]
        reveal_at = impact_beats[i]

        clips.append(make_image_clip(swatch_path, reveal_at - chunk_start))       # anticipation
        clips.append(make_image_clip(application_path, chunk_end - reveal_at))    # the reveal
        log.info(
            "Pair %d: swatch %.2fs -> REVEAL at %.2fs -> application until %.2fs",
            i + 1, chunk_start, reveal_at, chunk_end,
        )

    video = concatenate_videoclips(clips, method="compose")
    video = video.with_audio(audio).with_duration(audio_duration)

    output_path = Path(output_path)
    video.write_videofile(
        str(output_path),
        fps=30, codec="libx264", audio_codec="aac", pixel_format="yuv420p",
        # +faststart moves the moov atom (metadata index) before mdat (media data).
        # Without it, ffmpeg/MoviePy write mdat first — confirmed via byte inspection
        # on a real render — which Meta's video processing rejected outright with a
        # generic "problem uploading your video file" error, no permission-related
        # message at all. This is a container-level fix, not a re-encode.
        ffmpeg_params=["-movflags", "+faststart"],
        logger=None,
    )
    log.info("Reveal reel written to %s (%.1fs, %d pairs)", output_path, audio_duration, n_pairs)
    return output_path


# ---------------------------------------------------------------------------
# STAGE 3 — Video compositing
# ---------------------------------------------------------------------------

def _list_images(directory):
    exts = {".png", ".jpg", ".jpeg"}
    files = sorted(f for f in Path(directory).iterdir() if f.suffix.lower() in exts)
    if not files:
        raise PipelineError(f"No images found in {directory}")
    return files


def _pair_swatches_with_applications(swatch_dir, application_dir):
    """
    Matches each swatch to ITS OWN application shot by filename prefix — this project's
    naming convention is `{concept_id}_{room}_{style}_swatch.png` /
    `..._app.png`, e.g. c01_kit_modlux_swatch.png pairs with c01_kit_modlux_app.png.

    This replaces an earlier version that pulled from two independent cycles over the
    full pool, which let any swatch land next to any unrelated concept's application
    shot — a random-looking stitch rather than a coherent swatch-then-its-own-room
    reveal. Swatch and application must always be the same concept; this is the fix.
    """
    def base_key(path, suffix):
        name = path.stem
        return name[: -len(suffix)] if name.endswith(suffix) else name

    swatches = {base_key(p, "_swatch"): p for p in _list_images(swatch_dir)}
    applications = {base_key(p, "_app"): p for p in _list_images(application_dir)}

    common_keys = sorted(set(swatches) & set(applications))
    if not common_keys:
        raise PipelineError(
            f"No matching swatch/application filename pairs found between "
            f"{swatch_dir} and {application_dir}. Expected shared prefixes like "
            f"'c01_kit_modlux' across '<prefix>_swatch.png' and '<prefix>_app.png'."
        )

    unmatched_swatches = set(swatches) - set(applications)
    unmatched_apps = set(applications) - set(swatches)
    if unmatched_swatches or unmatched_apps:
        log.warning(
            "%d swatch(es) and %d application(s) had no matching counterpart and will "
            "be skipped: %s / %s",
            len(unmatched_swatches), len(unmatched_apps),
            sorted(unmatched_swatches), sorted(unmatched_apps),
        )

    pairs = [(swatches[k], applications[k]) for k in common_keys]
    log.info("Matched %d concept pairs for compositing", len(pairs))
    return pairs


def build_reel(beat_timestamps, audio_duration, swatch_dir, application_dir, output_path):
    """
    Builds a 1080x1920 clip, alternating swatch/application images at each beat
    boundary, muxed with the mastered audio. Total duration matches audio_duration —
    the last segment is stretched to the end rather than left short or truncating audio.
    """
    # MoviePy 2.x: no `.editor` submodule; .resize/.crop/.set_duration/.set_audio were
    # renamed to .resized/.cropped/.with_duration/.with_audio. Verified against the
    # actually-installed version rather than assumed.
    from moviepy import AudioFileClip, ImageClip, concatenate_videoclips

    W, H = 1080, 1920

    boundaries = sorted(set(t for t in beat_timestamps if 0 <= t <= audio_duration))
    if not boundaries or boundaries[0] > 0:
        boundaries = [0.0] + boundaries
    if boundaries[-1] < audio_duration:
        boundaries.append(audio_duration)

    # Concept pairs, cycled one pair per two segments: segment i uses the pair's swatch,
    # segment i+1 uses that SAME pair's application shot, then advance to the next
    # concept. This guarantees swatch and application always belong together.
    pairs = itertools.cycle(_pair_swatches_with_applications(swatch_dir, application_dir))
    current_pair = next(pairs)

    clips = []
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        duration = max(end - start, 1 / 24)  # never emit a zero/negative-length clip

        if i % 2 == 0:
            image_path = current_pair[0]  # this pair's swatch
        else:
            image_path = current_pair[1]  # the SAME pair's application shot
            current_pair = next(pairs)     # advance only after the pair is complete

        # Center-crop-to-fill at 1080x1920 without stretching: scale so the shorter
        # dimension covers the target, then crop the overflow evenly from both sides.
        img_clip = ImageClip(str(image_path))
        scale = max(W / img_clip.w, H / img_clip.h)
        img_clip = img_clip.resized(scale)
        img_clip = img_clip.cropped(
            x_center=img_clip.w / 2, y_center=img_clip.h / 2, width=W, height=H
        ).with_duration(duration)
        clips.append(img_clip)

    video = concatenate_videoclips(clips, method="compose")
    audio = AudioFileClip(str(Path(output_path).parent / "processed_audio.wav"))
    video = video.with_audio(audio).with_duration(audio_duration)

    output_path = Path(output_path)
    video.write_videofile(
        str(output_path),
        fps=30, codec="libx264", audio_codec="aac", pixel_format="yuv420p",
        # +faststart moves the moov atom (metadata index) before mdat (media data).
        # Without it, ffmpeg/MoviePy write mdat first — confirmed via byte inspection
        # on a real render — which Meta's video processing rejected outright with a
        # generic "problem uploading your video file" error, no permission-related
        # message at all. This is a container-level fix, not a re-encode.
        ffmpeg_params=["-movflags", "+faststart"],
        logger=None,
    )
    log.info("Reel written to %s (%.1fs)", output_path, audio_duration)
    return output_path


def validate_reel_for_meta(video_path, duration_seconds):
    """Fail fast locally rather than let Meta silently reject the upload."""
    if not (MIN_REEL_SECONDS <= duration_seconds <= MAX_REEL_SECONDS):
        raise PipelineError(
            f"Reel duration {duration_seconds:.1f}s is outside Meta's API-publishable "
            f"Reels range ({MIN_REEL_SECONDS}-{MAX_REEL_SECONDS}s). Longer clips publish "
            f"as a regular video, not a Reel, or are rejected outright."
        )
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,width,height",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    codec, width, height = probe.stdout.strip().split(",")
    if codec != "h264":
        raise PipelineError(f"Video codec is {codec}, Meta requires H.264 — re-encode before publishing")
    ratio_w, ratio_h = REQUIRED_ASPECT
    if abs(int(width) / int(height) - ratio_w / ratio_h) > 0.02:
        log.warning("Aspect ratio %sx%s is not exactly 9:16 — Meta may reject or letterbox it", width, height)
    log.info("Validated: %ss, %sx%s, codec=%s — publishable as a Reel", duration_seconds, width, height, codec)


# ---------------------------------------------------------------------------
# STAGE 4 — Publish via Meta Graph API
# ---------------------------------------------------------------------------

def get_next_caption_and_index(repo_root):
    """
    Reads caption_index.txt, generates that caption, and returns (caption, index) —
    the CALLER advances the counter only after a confirmed successful publish, same
    discipline as millionchallenge's day_counter.txt (a failed post shouldn't burn a
    caption slot).
    """
    from caption_bank import get_caption

    counter_path = Path(repo_root) / "caption_index.txt"
    index = int(counter_path.read_text().strip()) if counter_path.exists() else 0
    return get_caption(index), index


def advance_caption_index(repo_root, index):
    counter_path = Path(repo_root) / "caption_index.txt"
    counter_path.write_text(str(index + 1))
    subprocess.run(["git", "-C", str(repo_root), "add", "caption_index.txt"], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-m", f"Advance caption index to {index + 1}"], check=True)
    subprocess.run(["git", "-C", str(repo_root), "push"], check=True)


def _parse_owner_repo(remote_url):
    # handles both https://github.com/owner/repo.git and git@github.com:owner/repo.git
    remote_url = remote_url.strip().removesuffix(".git")
    if remote_url.startswith("git@"):
        return remote_url.split(":")[1].split("/")
    return "/".join(remote_url.split("/")[-2:]).split("/")


def upload_video_to_public_host(local_path, repo_root, media_subdir="media/reels"):
    """
    Zero-cost hosting: commits the finished reel straight into the same repo this
    pipeline already runs from, then returns its raw.githubusercontent.com URL for
    Meta to fetch. This is the exact pattern already running daily in the
    millionchallenge repo (reel.mp4 served the same way) — nothing new to pay for or
    maintain, just reused.

    Requires the repo to be PUBLIC — raw.githubusercontent.com does not serve private
    repo content without an auth token appended, which Meta's fetcher can't supply.
    Nothing secret lives in repo *content* either way (secrets are only ever GitHub
    Actions secrets, encrypted separately), so making this specific repo public is
    safe: `gh repo edit <owner>/<repo> --visibility public`.

    In GitHub Actions, actions/checkout already leaves the workflow sitting inside an
    authenticated git clone (persist-credentials defaults to true), so `git push` just
    works with no extra secret. Running locally works the same way off your own
    `gh auth login` session.
    """
    import shutil

    repo_root = Path(repo_root)
    media_dir = repo_root / media_subdir
    media_dir.mkdir(parents=True, exist_ok=True)

    filename = f"reel_{int(time.time())}.mp4"
    dest = media_dir / filename
    shutil.copy(local_path, dest)

    _prune_old_reels(media_dir, keep_latest=10)  # keep the repo from growing forever

    rel_path = dest.relative_to(repo_root).as_posix()
    subprocess.run(["git", "-C", str(repo_root), "add", "-A", media_subdir], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-m", f"Add reel {filename}"], check=True)
    subprocess.run(["git", "-C", str(repo_root), "push"], check=True)

    remote = subprocess.run(
        ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=True,
    ).stdout
    owner, repo = _parse_owner_repo(remote)
    branch = subprocess.run(
        ["git", "-C", str(repo_root), "branch", "--show-current"],
        capture_output=True, text=True, check=True,
    ).stdout.strip() or "main"

    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{rel_path}"

    # Small propagation wait — pushes are usually near-instant on raw.githubusercontent.com
    # but not guaranteed to be readable in the same second as the push.
    for attempt in range(6):
        time.sleep(3)
        try:
            r = requests.head(raw_url, timeout=10, allow_redirects=True)
            if r.status_code == 200:
                log.info("Confirmed reel is live at %s", raw_url)
                return raw_url
        except requests.RequestException:
            pass
    raise PipelineError(f"Pushed {filename} but raw.githubusercontent.com isn't serving it yet: {raw_url}")


def _prune_old_reels(media_dir, keep_latest):
    """Deletes older committed reels so the repo doesn't grow unbounded — cheap
    insurance since GitHub is free within reasonable size, not unlimited."""
    files = sorted(Path(media_dir).glob("reel_*.mp4"), key=lambda p: p.stat().st_mtime)
    for old_file in files[:-keep_latest] if len(files) > keep_latest else []:
        old_file.unlink()
        log.info("Pruned old reel: %s", old_file.name)


def extract_template_cut_timestamps(template_video_path, scene_threshold=0.3):
    """
    Runs ffmpeg's scene-change filter on a REFERENCE reel (one already made with good
    timing — by hand, in CapCut, wherever) and returns the timestamps where each cut
    happens. This is the same detection method already validated earlier in this
    project: computed segment boundaries matched detected scene-change timestamps to
    within a single video frame on a real rendered clip, so it's trusted, not new.

    Pivot rationale: deriving "musically pleasing" cuts algorithmically from raw audio
    (beat tracking, impact-beat ranking) kept producing results that didn't feel right
    by ear even when the underlying math checked out — the detected beats simply
    aren't always the same thing as a human's sense of good timing. Copying the exact
    cut pattern from a reel that already IS good sidesteps that problem entirely.
    """
    result = subprocess.run(
        ["ffmpeg", "-i", str(template_video_path), "-filter:v",
         f"select='gt(scene,{scene_threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    timestamps = []
    for line in result.stderr.splitlines():
        if "pts_time:" in line:
            for token in line.split():
                if token.startswith("pts_time:"):
                    timestamps.append(float(token.split(":", 1)[1]))
    timestamps = sorted(set(timestamps))
    if not timestamps:
        raise PipelineError(
            f"No scene changes detected in template {template_video_path} at threshold "
            f"{scene_threshold} — try lowering it (e.g. 0.2) if the template's cuts are "
            f"subtle, or confirm the file actually has hard cuts, not crossfades."
        )
    log.info("Extracted %d cut timestamps from template %s", len(timestamps), template_video_path)
    return timestamps


def build_reel_from_template_timing(template_cut_timestamps, audio_wav_path, swatch_dir,
                                     application_dir, output_path):
    """
    Builds a new reel using an EXISTING reel's exact cut-timing pattern applied to
    fresh audio and our own swatch/application pairs, instead of deriving cut points
    from the audio itself. Just substitutes the template's timestamps in place of
    algorithmic beat_timestamps — build_reel's boundary handling already clips/extends
    to whatever the new audio's actual duration is, so a template and a new track of
    different lengths both work: excess template cuts beyond the new audio's length
    are simply dropped, and if the new audio runs longer than the template, the final
    segment extends to cover it.
    """
    audio_duration = get_audio_duration_seconds(audio_wav_path)
    return build_reel(template_cut_timestamps, audio_duration, swatch_dir, application_dir, output_path)



def _graph_post(path, **params):
    token = os.environ["META_SYSTEM_USER_TOKEN"]
    r = requests.post(f"{GRAPH_API_BASE}/{path}", data={**params, "access_token": token}, timeout=60)
    body = r.json()
    if r.status_code >= 400 or "error" in body:
        raise PipelineError(f"Graph API error on {path}: {body.get('error', body)}")
    return body


def _graph_get(path, **params):
    token = os.environ["META_SYSTEM_USER_TOKEN"]
    r = requests.get(f"{GRAPH_API_BASE}/{path}", params={**params, "access_token": token}, timeout=30)
    body = r.json()
    if r.status_code >= 400 or "error" in body:
        raise PipelineError(f"Graph API error on {path}: {body.get('error', body)}")
    return body


def publish_to_instagram(video_public_url, caption):
    ig_user_id = os.environ["META_IG_BUSINESS_ACCOUNT_ID"]

    log.info("Creating Instagram Reels container...")
    container = _graph_post(
        f"{ig_user_id}/media",
        media_type="REELS", video_url=video_public_url, caption=caption, share_to_feed="true",
    )
    container_id = container["id"]

    log.info("Polling container %s for FINISHED status...", container_id)
    deadline = time.time() + 5 * 60  # Meta recommends polling for up to ~5 minutes
    while time.time() < deadline:
        status = _graph_get(container_id, fields="status_code")["status_code"]
        log.info("  container status: %s", status)
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise PipelineError(f"Instagram container {container_id} failed with status {status}")
        time.sleep(15)
    else:
        raise PipelineError(f"Instagram container {container_id} did not finish within timeout")

    log.info("Publishing container %s...", container_id)
    result = _graph_post(f"{ig_user_id}/media_publish", creation_id=container_id)
    log.info("Published to Instagram: media id %s", result["id"])
    return result["id"]


def publish_to_facebook(local_video_path, caption, app_id, expected_duration_s=None):
    """
    Publishes a video to the Facebook Page using the Resumable Upload API — the
    file_url parameter this used to rely on is deprecated. Current required flow,
    per Meta's own docs (confirmed live, not assumed):
      1. POST /{app_id}/uploads with file_name/file_length/file_type -> upload session id
      2. POST /upload:{session_id} with the raw file bytes -> file handle ("h")
      3. POST /{page_id}/videos with fbuploader_video_file_chunk=<handle> -> video id
    Needs pages_show_list, pages_read_engagement, pages_manage_posts only — NOT the
    legacy publish_video permission, despite what the error message implies. Two
    permission detours were burned confirming this before the actual fix was found:
    the error message is misleading, not evidence of a missing grant.

    UPLOAD RELIABILITY WARNING — read before trusting a "success" from this function:
    A single-shot POST of the whole file sometimes silently truncates server-side —
    confirmed on a real published post: Meta's own API reported the delivered video's
    `length` as 1.7s when the source file was 19.85s, with every processing phase
    marked "complete" and no error anywhere in the publish chain. The upload step
    below now follows the documented resume protocol properly (send what you can,
    verify the server's real file_offset via GET, resend the exact remainder if
    incomplete) rather than trusting the first response's presence of an "h" field,
    which is NOT sufficient — a handle can be returned and still fail at publish, or
    reference a truncated file. This was only ever caught by checking the actually
    delivered `length` after the fact, which is why expected_duration_s is checked
    below. Testing this from a sandboxed environment behind a network egress proxy
    showed inconsistent results (worked once, truncated once, produced a handle that
    failed at publish once) with no pattern tied to chunk size or protocol details —
    that inconsistency may be specific to a proxied network path, not this API or this
    code, and re-testing from an unproxied connection is the next real diagnostic step
    if this still misbehaves.
    """
    page_id = os.environ["META_PAGE_ID"]
    token = os.environ["META_SYSTEM_USER_TOKEN"]
    local_video_path = Path(local_video_path)
    file_size = local_video_path.stat().st_size
    with open(local_video_path, "rb") as f:
        file_bytes = f.read()

    log.info("Starting resumable upload session for %s (%d bytes)...", local_video_path.name, file_size)
    r = requests.post(
        f"{GRAPH_API_BASE}/{app_id}/uploads",
        params={"file_name": local_video_path.name, "file_length": file_size,
                "file_type": "video/mp4", "access_token": token},
        timeout=30,
    )
    body = r.json()
    if r.status_code >= 400 or "error" in body:
        raise PipelineError(f"Facebook upload session error: {body.get('error', body)}")
    session_id = body["id"]  # already prefixed "upload:..."

    handle = None
    offset = 0
    for attempt in range(10):
        log.info("Uploading bytes %d-%d of %d (attempt %d)...", offset, file_size, file_size, attempt + 1)
        r = requests.post(
            f"{GRAPH_API_BASE}/{session_id}",
            headers={"Authorization": f"OAuth {token}", "file_offset": str(offset)},
            data=file_bytes[offset:],
            timeout=180,
        )
        body = r.json()
        if "h" in body:
            handle = body["h"].split("\n")[0]  # response has repeated this handle, newline-joined, on every run so far
            break
        # No handle yet: confirm the server's ACTUAL received offset — trusting our
        # own byte count here is exactly what let a truncated upload look complete.
        check = requests.get(f"{GRAPH_API_BASE}/{session_id}", headers={"Authorization": f"OAuth {token}"})
        server_offset = check.json().get("file_offset", offset)
        if server_offset == offset:
            raise PipelineError(
                f"Facebook upload stalled at offset {offset}/{file_size} — server offset "
                f"did not advance after a resend. Response: {body}"
            )
        offset = server_offset
    if handle is None:
        raise PipelineError(f"Facebook upload never returned a handle after {attempt + 1} attempts")

    log.info("Publishing video to Facebook Page %s using handle...", page_id)
    # Shells out to curl rather than using requests here, deliberately. The identical
    # request — same handle, same multipart encoding via files={...} — failed
    # through requests with a generic "problem uploading your video file" error on
    # three separate attempts, while the exact same handle published successfully via
    # curl's -F flag every time it was tried. Never fully isolated the library-level
    # discrepancy; rather than keep debugging blind, this matches the invocation
    # that's actually proven to work.
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{GRAPH_API_BASE}/{page_id}/videos",
         "-F", f"access_token={token}",
         "-F", f"description={caption}",
         "-F", f"fbuploader_video_file_chunk={handle}"],
        capture_output=True, text=True, timeout=60,
    )
    try:
        body = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise PipelineError(f"Facebook publish returned non-JSON: {result.stdout[:500]}")
    if "error" in body:
        raise PipelineError(f"Facebook publish error: {body['error']}")
    video_id = body.get("id")
    log.info("Published to Facebook: video id %s", video_id)

    if expected_duration_s:
        _verify_facebook_video_duration(video_id, token, expected_duration_s)
    return video_id


def _verify_facebook_video_duration(video_id, token, expected_duration_s, tolerance_s=1.0):
    """
    The ONE check that would have caught the truncation bug immediately instead of
    it shipping to a live post unnoticed: a successful publish response and an
    error-free upload chain are not proof the delivered video is complete. Polls
    Meta's own reported `length` for the published video and raises if it doesn't
    match what was actually sent.
    """
    for _ in range(10):
        r = requests.get(f"{GRAPH_API_BASE}/{video_id}",
                          params={"access_token": token, "fields": "length,status"})
        body = r.json()
        status = body.get("status", {}).get("video_status")
        if status == "ready":
            actual = body.get("length", 0)
            if abs(actual - expected_duration_s) > tolerance_s:
                raise PipelineError(
                    f"Facebook published video {video_id} but delivered length is "
                    f"{actual}s, expected ~{expected_duration_s}s — likely truncated "
                    f"upload. Do not treat this publish as successful."
                )
            log.info("Verified: Facebook video %s delivered length %.1fs matches expected", video_id, actual)
            return
        time.sleep(10)
    raise PipelineError(f"Facebook video {video_id} never reached 'ready' status for duration verification")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_pipeline():
    gdrive_input = os.environ["GDRIVE_INPUT_PATH"]
    swatch_dir = os.environ["SWATCH_ASSETS_DIR"]
    application_dir = os.environ["APPLICATION_ASSETS_DIR"]
    # In GitHub Actions this is set automatically; locally it's wherever you cloned
    # this repo. Either way it must be the root of the git working directory that
    # gets pushed to for hosting + the caption counter.
    repo_root = os.environ.get("GITHUB_WORKSPACE") or os.environ.get("REPO_ROOT", ".")
    output_dir = Path(os.environ.get("OUTPUT_DIR", "./output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    clips = find_new_clips(gdrive_input)
    if not clips:
        log.info("No new clips to process. Exiting.")
        return

    for clip in clips:
        log.info("=== Processing %s ===", clip.name)
        try:
            wav_path = extract_and_master_audio(clip, output_dir / "processed_audio.wav")
            duration = get_audio_duration_seconds(wav_path)
            bpm, beats = extract_beat_timestamps(wav_path)

            reel_path = build_reel(beats, duration, swatch_dir, application_dir,
                                    output_dir / "final_output_reel.mp4")
            validate_reel_for_meta(reel_path, duration)

            public_url = upload_video_to_public_host(reel_path, repo_root)
            caption, caption_idx = get_next_caption_and_index(repo_root)

            ig_id = publish_to_instagram(public_url, caption)
            fb_id = publish_to_facebook(reel_path, caption, app_id=os.environ["META_APP_ID"],
                                         expected_duration_s=duration)
            advance_caption_index(repo_root, caption_idx)  # only after both succeed
            log.info("Done. Instagram media_id=%s Facebook video_id=%s caption_index=%s",
                      ig_id, fb_id, caption_idx)

        except PipelineError as e:
            log.error("Pipeline stopped for %s: %s", clip.name, e)
            continue  # move on to next clip rather than aborting the whole batch
        except Exception as e:
            log.exception("Unexpected error processing %s", clip.name)
            continue


if __name__ == "__main__":
    required = ["META_SYSTEM_USER_TOKEN", "META_IG_BUSINESS_ACCOUNT_ID", "META_PAGE_ID",
                "GDRIVE_INPUT_PATH", "SWATCH_ASSETS_DIR", "APPLICATION_ASSETS_DIR"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)
    run_pipeline()
