"""
Core Decor Reel Pipeline
========================
Each run: pulls the next reel from a rotating pool of human-made template reels in
Google Drive, extracts and masters its audio, copies its exact cut-timing pattern
(not algorithmic beat detection — see the cut-timing section further down for why),
composites a 9:16 Reel using the next block of the 50 swatch+application concept
pairs, and publishes to Instagram and Facebook. State (which template is next, which
concept block is next, which caption is next) persists as small text files committed
to this repo, the same pattern as day_counter.txt in the millionchallenge repo — no
database, no external state store.

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
    GOOGLE_OAUTH_CLIENT_ID       For pulling templates from the Drive Template Reels
    GOOGLE_OAUTH_CLIENT_SECRET   folder — same OAuth app already used for hosting
    GOOGLE_OAUTH_REFRESH_TOKEN   uploads, read from env instead of a local file so
                                  this works unattended in GitHub Actions
    SWATCH_ASSETS_DIR            Folder of the 50 swatch images (committed to this repo)
    APPLICATION_ASSETS_DIR       Folder of the 50 application images (committed too)
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


def render_pushin_clip(image_path, duration, output_path, width, height, fps=30,
                        zoom_rate_per_second=0.07, max_zoom=1.5):
    """
    Plain Ken Burns push-in via ffmpeg's zoompan filter -- no depth model, no
    parallax. Originally built and validated for Dolly Reel; promoted here once
    Hot Takes became a second consumer of the exact same technique, rather than
    duplicating ffmpeg-flag logic that's already had one real bug fixed in it
    (see the x/y note below). Two depth-based prototypes were tried first
    (concept_tools/_test_parallax.py, _test_layered_parallax.py) and both
    introduced visible geometric artifacts (bent lines / ghosting) that this
    plain center-zoom has none of -- see dolly_reel/dolly_reel_pipeline.py's
    module docstring for the full comparison.

    `force_original_aspect_ratio=increase` + `crop` before the zoompan, not a
    bare `scale=W:H`, because source images across this project's asset
    folders aren't all identically-proportioned (assets/application is
    1072-1080px wide at 1920 tall depending on series; assets/application_eseries
    ranges up to 1088 -- all close to 9:16 but not pixel-identical). A bare
    scale would stretch whichever dimension doesn't match; this cover-fits
    then center-crops instead, matching what a static ImageClip resize+crop
    would have done, before any zoom is applied on top.

    Then scales the source 3x before zoompan (supersampling) so the crop
    window doesn't visibly soften at the most-zoomed-in frame.

    x/y MUST be set explicitly -- zoompan defaults both to 0, which anchors
    the crop window at the source's top-left corner rather than its center.
    A real live run confirmed this exactly: every clip read as drifting
    toward the bottom-right instead of pushing straight into the middle,
    because the top-left corner stayed pinned in place while the rest of
    the frame grew and was pushed outward around it. The centered formula --
    x='iw/2-(iw/zoom/2)', y='ih/2-(ih/zoom/2)' -- keeps the crop window
    centered on the source at every zoom level instead.
    """
    target_zoom = min(1.0 + zoom_rate_per_second * duration, max_zoom)
    n_frames = max(round(duration * fps), 1)
    increment = (target_zoom - 1.0) / n_frames

    _run_ffmpeg(
        ["-framerate", str(fps), "-loop", "1", "-i", str(image_path),
         "-vf", f"scale={width * 3}:{height * 3}:force_original_aspect_ratio=increase,"
                f"crop={width * 3}:{height * 3},"
                f"zoompan=z='min(zoom+{increment},{target_zoom})':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={n_frames}:s={width}x{height}:fps={fps}",
         "-frames:v", str(n_frames), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         str(output_path)],
        f"push-in clip for {Path(image_path).name} ({duration:.2f}s, target zoom {target_zoom:.2f})",
    )
    return output_path


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


def build_reel(beat_timestamps, audio_duration, swatch_dir, application_dir, output_path,
                audio_wav_path, concept_start_offset=0):
    """
    Builds a 1080x1920 clip, alternating swatch/application images at each beat
    boundary, muxed with the mastered audio. Total duration matches audio_duration —
    the last segment is stretched to the end rather than left short or truncating audio.

    Always ends on an application shot, never a swatch — a firm requirement, not a
    preference. The swatch/application alternation starts with swatch at segment 0, so
    it naturally ends on application only when the total segment count is EVEN; an odd
    count would leave a bare swatch as the very last thing shown. Rather than special-
    case the final segment (which could land two application shots back to back), the
    fix is applied once, up front: if the segment count is odd, the first internal cut
    is dropped, giving the opening swatch a slightly longer hold and making the total
    count even — the carefully-timed ENDING is left untouched either way.

    concept_start_offset lets a daily rotation begin partway through the 50 concept
    pairs instead of always starting at c01, so consecutive days don't all open on the
    same handful of concepts. Returns (output_path, concepts_used_count) so the caller
    can advance the rotation state by however many concepts this particular reel
    actually consumed.
    """
    from moviepy import AudioFileClip, ImageClip, concatenate_videoclips

    W, H = 1080, 1920
    FPS = 30

    def snap_to_frame(t):
        # Every boundary quantized to an exact frame multiple BEFORE any duration
        # is computed, not after — computing durations from unsnapped boundaries
        # and rounding each clip's frame count independently lets sub-frame error
        # compound across the sequence. Confirmed on a real rebuild: the first five
        # cuts of an eight-cut template landed frame-exact, but the sixth and
        # seventh had each drifted a full frame (+0.033s) from the source template
        # — small individually, cumulative in effect, and avoidable entirely by
        # snapping boundaries themselves rather than letting per-clip durations
        # each round independently. Same fix already applied in the algorithmic
        # beat-sync function elsewhere in this file; this path never had it.
        return round(t * FPS) / FPS

    boundaries = sorted(set(snap_to_frame(t) for t in beat_timestamps if 0 <= t <= audio_duration))
    if not boundaries or boundaries[0] > 0:
        boundaries = [0.0] + boundaries
    if boundaries[-1] < audio_duration:
        boundaries.append(audio_duration)

    n_segments = len(boundaries) - 1
    if n_segments % 2 != 0 and n_segments > 1:
        # PRIOR VERSION WAS MATHEMATICALLY BROKEN — confirmed on a real published
        # post that still ended on a swatch despite this exact fix supposedly being
        # in place. It split the longest segment into two halves showing the SAME
        # duplicated image, reasoning that adding a boundary (rather than merging
        # two into one) would avoid ever sacrificing an original beat. True, but
        # irrelevant to the actual requirement: whether the reel ends on swatch or
        # application is determined by the PARITY OF HOW MANY TIMES THE IMAGE
        # ACTUALLY CHANGES (flips), not by the total segment count. A duplicated-
        # image split is a "stay the same" step, not a "flip" — it changes segment
        # count from odd to even but changes the flip count NOT AT ALL, so the
        # ending was never actually fixed. This was missed because verification
        # only checked that cut TIMESTAMPS matched the source template — which they
        # did — never that the delivered video's final image was actually an
        # application. Both real templates fixed by the previous version were
        # re-checked after finding this and BOTH were still silently ending on a
        # swatch the whole time.
        #
        # Correct fix: split the longest segment's TIME range into two (preserving
        # every original template cut, same as before), but let the two halves take
        # DIFFERENT, normally-sequential content — not a repeat — by falling
        # straight back to simple position-based alternation (i % 2) for every
        # segment once the boundary list is finalized. An inserted boundary with
        # ordinary alternating content on both sides is a genuine flip, which is
        # what actually fixes the parity: for any even final segment count with
        # strict position-based alternation starting on swatch, the last segment
        # is mathematically guaranteed to be i % 2 == 1 — application. No src
        # tracking, no duplicate-detection edge cases; this is deliberately the
        # simplest version that's actually correct, not a more-clever one that
        # merely looks correct on the cases already tested.
        durations = [boundaries[i + 1] - boundaries[i] for i in range(n_segments)]
        longest_idx = max(range(n_segments), key=lambda i: durations[i])
        mid = snap_to_frame((boundaries[longest_idx] + boundaries[longest_idx + 1]) / 2)
        boundaries.insert(longest_idx + 1, mid)
        n_segments += 1

    all_pairs = _pair_swatches_with_applications(swatch_dir, application_dir)
    rotated_pairs = all_pairs[concept_start_offset % len(all_pairs):] + \
                     all_pairs[:concept_start_offset % len(all_pairs)]
    pairs = itertools.cycle(rotated_pairs)
    current_pair = next(pairs)
    concepts_used = 1

    clips = []
    for i in range(n_segments):
        start, end = boundaries[i], boundaries[i + 1]
        duration = max(end - start, 1 / 24)  # never emit a zero/negative-length clip

        if i % 2 == 0:
            image_path = current_pair[0]  # this pair's swatch
        else:
            image_path = current_pair[1]  # the SAME pair's application shot
            if i < n_segments - 1:         # don't advance past the final application
                current_pair = next(pairs)
                concepts_used += 1

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
    audio = AudioFileClip(str(audio_wav_path))
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
    log.info("Reel written to %s (%.1fs, %d concepts, starting offset %d)",
              output_path, audio_duration, concepts_used, concept_start_offset)
    return output_path, concepts_used


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
    _git_push_with_retry(repo_root)


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
    _git_push_with_retry(repo_root)

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
                                     application_dir, output_path, concept_start_offset=0):
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
    return build_reel(template_cut_timestamps, audio_duration, swatch_dir, application_dir,
                       output_path, audio_wav_path=audio_wav_path,
                       concept_start_offset=concept_start_offset)



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


def publish_to_buffer(video_public_url, caption, channel_id, platform, youtube_title=None):
    """
    Publishes to TikTok or YouTube via Buffer's GraphQL API — the direct-API route
    for these two platforms is high-friction enough (TikTok's own app review,
    YouTube's OAuth verification) that Buffer's free tier is used as a pragmatic
    shortcut instead, same as the video_public_url already hosted for Instagram/
    Facebook. Verified against real posts on both platforms before this was written,
    not assumed from docs alone.

    YouTube requires platform-specific metadata (title, categoryId) that TikTok
    doesn't — passing youtube_title is required when platform == "youtube", ignored
    otherwise. Category 26 (Howto & Style) is hardcoded as a reasonable fit for
    interior design content; revisit if that stops being accurate.
    """
    token = os.environ["BUFFER_API_KEY"]
    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        __typename
        ... on PostActionSuccess { post { id status } }
        ... on InvalidInputError { message }
        ... on LimitReachedError { message }
        ... on UnauthorizedError { message }
        ... on UnexpectedError { message }
        ... on RestProxyError { message }
        ... on NotFoundError { message }
      }
    }
    """
    post_input = {
        "channelId": channel_id,
        "mode": "shareNow",
        "schedulingType": "automatic",
        "needsApproval": False,
        "text": caption,
        "assets": [{"video": {"url": video_public_url}}],
    }
    if platform == "youtube":
        if not youtube_title:
            raise PipelineError("youtube_title is required when publishing to YouTube via Buffer")
        post_input["assets"][0]["video"]["metadata"] = {"title": youtube_title}
        post_input["metadata"] = {"youtube": {"title": youtube_title, "categoryId": "26", "privacy": "public"}}

    r = requests.post(
        "https://api.buffer.com/graphql",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": mutation, "variables": {"input": post_input}},
        timeout=60,
    )
    body = r.json()
    result = body.get("data", {}).get("createPost", {})
    if result.get("__typename") != "PostActionSuccess":
        raise PipelineError(f"Buffer publish to {platform} failed: {result.get('message', body)}")
    post_id = result["post"]["id"]
    log.info("Published to %s via Buffer: post id %s", platform, post_id)
    return post_id


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


def publish_to_facebook(video_public_url, caption, expected_duration_s=None):
    """
    Publishes via the dedicated Reels Publishing API (/{page_id}/video_reels), pull-
    based — Meta fetches the file from video_public_url rather than us pushing bytes.

    THIS REPLACES A PUSH-BASED IMPLEMENTATION THAT NEVER WORKED RELIABLY. History,
    because the failure mode was strange enough to be worth remembering exactly:

    The general Video API (/{page_id}/videos with the Resumable Upload API's push
    model) silently truncated concatenated/multi-cut videos on the server side —
    confirmed repeatedly on real published posts: delivered `length` came back as
    1.7s, 4s, 10s, and 4.8s against source files that were actually ~20s, across
    different encoding attempts (default keyframes, forced regular GOP intervals,
    faststart, non-faststart). Every attempt returned a normal success response with
    no error — this was only ever caught by polling the delivered video's own
    `length` afterward. Isolated via a systematic elimination, not a guess: any
    SINGLE continuous-source video (a flat color, a static photo) of equal or
    greater size/duration delivered correctly every time; ANY video built by
    concatenating multiple distinct clips truncated, unpredictably, regardless of
    which concatenation method built it (MoviePy's re-encode, ffmpeg's stream-copy
    concat demuxer) or which encoding parameters were used. The trigger was
    concatenation itself, not file size, duration, or a specific encoder setting —
    and the push-based upload API is where it happened, since Meta's own Reels spec
    requires "Closed GOP (2-5 seconds)" and our per-cut keyframes (every cut, often
    under a second apart) likely violate that, though this was never confirmed as
    the exact mechanism — only that avoiding the push path entirely fixed it.

    The pull-based Reels API was tested against the SAME real 19.85s production
    reel that had just been truncated to 4s via the push method, immediately after
    that failure, with no other changes. It delivered `length: 19.805`, fully
    processed, fully published. That's why this replaced the old implementation
    outright rather than sitting alongside it as an alternative.

    Same permissions as before (pages_show_list, pages_read_engagement,
    pages_manage_posts) — no new grant needed. Needs a Page token from someone who
    can perform CREATE_CONTENT, same as always.
    """
    page_id = os.environ["META_PAGE_ID"]
    token = os.environ["META_SYSTEM_USER_TOKEN"]

    log.info("Starting Reels upload session...")
    r = requests.post(
        f"{GRAPH_API_BASE}/{page_id}/video_reels",
        headers={"Content-Type": "application/json"},
        json={"upload_phase": "start", "access_token": token},
        timeout=30,
    )
    body = r.json()
    if r.status_code >= 400 or "error" in body:
        raise PipelineError(f"Reels session start error: {body.get('error', body)}")
    video_id = body["video_id"]
    upload_url = body["upload_url"]

    log.info("Pulling %s into Reels upload (video_id=%s)...", video_public_url, video_id)
    r = requests.post(
        upload_url,
        headers={"Authorization": f"OAuth {token}", "file_url": video_public_url},
        timeout=60,
    )
    body = r.json()
    if r.status_code >= 400 or not body.get("success"):
        raise PipelineError(f"Reels pull-upload error: {body}")

    # Confirm the server's own byte count before publishing — trusting "success":true
    # alone is exactly the class of premature trust that caused the original bug.
    for _ in range(12):
        check = requests.get(f"{GRAPH_API_BASE}/{video_id}", params={"fields": "status", "access_token": token})
        status = check.json().get("status", {})
        if status.get("uploading_phase", {}).get("status") == "complete":
            log.info("Upload confirmed complete: %d bytes transferred",
                      status["uploading_phase"].get("bytes_transferred", 0))
            break
        time.sleep(5)
    else:
        raise PipelineError(f"Reels upload for video_id {video_id} never reached complete status")

    log.info("Publishing Reel...")
    r = requests.post(
        f"{GRAPH_API_BASE}/{page_id}/video_reels",
        params={"access_token": token, "video_id": video_id, "upload_phase": "finish",
                "video_state": "PUBLISHED", "description": caption},
        timeout=30,
    )
    body = r.json()
    if r.status_code >= 400 or not body.get("success"):
        raise PipelineError(f"Reels publish error: {body}")
    log.info("Published to Facebook Reels: video_id=%s post_id=%s", video_id, body.get("post_id"))

    if expected_duration_s:
        _verify_facebook_video_duration(video_id, token, expected_duration_s)
    return video_id


def _verify_facebook_video_duration(video_id, token, expected_duration_s, tolerance_s=1.0):
    """
    Not optional, not defensive-programming-for-its-own-sake: this is the one check
    that actually caught the truncation bug in the first place. A "success" response
    from any Facebook publish step in this pipeline is not proof the delivered video
    is complete — confirmed repeatedly. Polls Meta's own reported `length` for the
    published video and raises if it doesn't match what was actually sent.
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
# Image carousel publishing — added for carousel_post/, the fourth content type.
# Genuinely different container shapes from the REELS/video paths above, not a
# variant of them: Instagram needs per-image "carousel item" containers folded
# into one parent container; Facebook has no carousel object at all and uses an
# ordinary multi-photo feed post instead; Buffer's asset schema takes an "image"
# key instead of "video". Kept here rather than inside carousel_post/ because
# they lean on the exact same _graph_post/_graph_get/PipelineError plumbing
# already centralized in this file — genuinely shared, not content-type-specific.
# ---------------------------------------------------------------------------

def upload_images_to_public_host(local_paths, repo_root, media_subdir="media/carousels"):
    """
    Same zero-cost git-commit + raw.githubusercontent.com hosting pattern as
    upload_video_to_public_host above, generalized for a BATCH of images landing
    in one commit/push rather than one video per push — a carousel always needs
    at least two images published together, and pushing them one at a time would
    mean multiple commits (and multiple propagation waits) for what is really one
    unit of content.
    """
    import shutil

    repo_root = Path(repo_root)
    media_dir = repo_root / media_subdir
    media_dir.mkdir(parents=True, exist_ok=True)

    ts = int(time.time())
    dests = []
    for i, local_path in enumerate(local_paths):
        dest = media_dir / f"carousel_{ts}_{i}.jpg"
        shutil.copy(local_path, dest)
        dests.append(dest)

    _prune_old_carousel_images(media_dir, keep_latest=20)  # 10 carousels' worth, 2 images each

    subprocess.run(["git", "-C", str(repo_root), "add", "-A", media_subdir], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-m", f"Add carousel images {ts}"], check=True)
    _git_push_with_retry(repo_root)

    remote = subprocess.run(
        ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=True,
    ).stdout
    owner, repo = _parse_owner_repo(remote)
    branch = subprocess.run(
        ["git", "-C", str(repo_root), "branch", "--show-current"],
        capture_output=True, text=True, check=True,
    ).stdout.strip() or "main"

    urls = []
    for dest in dests:
        rel_path = dest.relative_to(repo_root).as_posix()
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{rel_path}"
        for attempt in range(6):
            time.sleep(3)
            try:
                r = requests.head(raw_url, timeout=10, allow_redirects=True)
                if r.status_code == 200:
                    log.info("Confirmed carousel image is live at %s", raw_url)
                    urls.append(raw_url)
                    break
            except requests.RequestException:
                pass
        else:
            raise PipelineError(f"Pushed {dest.name} but raw.githubusercontent.com isn't serving it yet: {raw_url}")
    return urls


def _prune_old_carousel_images(media_dir, keep_latest):
    files = sorted(Path(media_dir).glob("carousel_*.jpg"), key=lambda p: p.stat().st_mtime)
    for old_file in files[:-keep_latest] if len(files) > keep_latest else []:
        old_file.unlink()
        log.info("Pruned old carousel image: %s", old_file.name)


def publish_carousel_to_instagram(image_urls, caption):
    """
    A carousel is a different container SHAPE from the REELS path in
    publish_to_instagram above, not a variant of it: each image first becomes
    its own is_carousel_item child container, then one parent container with
    media_type=CAROUSEL references all of them by id via children, and only
    the PARENT gets published. Order is preserved exactly as given — callers
    pass image_urls as one or more [swatch_url, application_url] pairs
    concatenated in order, so each concept's swatch is seen right before its
    own application shot, same reveal logic already used throughout the video
    reel pipelines. Instagram allows up to 10 children per carousel; callers
    are responsible for staying under that.

    Meta's content-publishing API accepts JPEG only for image_url (confirmed
    against Meta's own docs before writing this — a PNG image_url is rejected
    outright) and requires an aspect ratio between 4:5 and 1.91:1. Never call
    this with a raw asset PNG; see carousel_post/prepare_image.py for the
    conversion this depends on.
    """
    if len(image_urls) < 2:
        raise PipelineError(f"Instagram carousel needs at least 2 images, got {len(image_urls)}")

    ig_user_id = os.environ["META_IG_BUSINESS_ACCOUNT_ID"]

    child_ids = []
    for url in image_urls:
        child = _graph_post(f"{ig_user_id}/media", image_url=url, is_carousel_item="true")
        child_ids.append(child["id"])
    log.info("Created %d carousel item containers: %s", len(child_ids), child_ids)

    container = _graph_post(
        f"{ig_user_id}/media",
        media_type="CAROUSEL", children=",".join(child_ids), caption=caption,
    )
    container_id = container["id"]

    log.info("Polling carousel container %s for FINISHED status...", container_id)
    deadline = time.time() + 5 * 60
    while time.time() < deadline:
        status = _graph_get(container_id, fields="status_code")["status_code"]
        log.info("  container status: %s", status)
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise PipelineError(f"Instagram carousel container {container_id} failed with status {status}")
        time.sleep(10)
    else:
        raise PipelineError(f"Instagram carousel container {container_id} did not finish within timeout")

    result = _graph_post(f"{ig_user_id}/media_publish", creation_id=container_id)
    log.info("Published Instagram carousel: media id %s", result["id"])
    return result["id"]


def publish_photo_post_to_facebook(image_urls, caption):
    """
    Facebook Pages have no separate "carousel" object the way Instagram does —
    the closest equivalent is an ordinary feed post with multiple attached
    photos, which Facebook's own UI renders as a swipeable gallery. Each photo
    is uploaded UNPUBLISHED first (published=false) to get a photo id without it
    appearing as its own standalone post, then one /feed post attaches all of
    them via attached_media, in the same order given.
    """
    page_id = os.environ["META_PAGE_ID"]

    media_fbids = []
    for url in image_urls:
        photo = _graph_post(f"{page_id}/photos", url=url, published="false")
        media_fbids.append(photo["id"])
    log.info("Uploaded %d unpublished Facebook photos: %s", len(media_fbids), media_fbids)

    attached_media = json.dumps([{"media_fbid": fbid} for fbid in media_fbids])
    result = _graph_post(f"{page_id}/feed", message=caption, attached_media=attached_media)
    log.info("Published Facebook photo post: post id %s", result["id"])
    return result["id"]


def publish_image_carousel_to_buffer(image_urls, caption, channel_id, platform):
    """
    Best-effort image/carousel post via Buffer's GraphQL API, for platforms this
    project reaches only through Buffer (TikTok, Pinterest) rather than a direct
    API. UNTESTED against this project's real Buffer account as of when this was
    written — same "first real run is the test" position already taken for the
    Pinterest video path in single_product_reel (see that module for the
    precedent). Callers should treat a failure here as non-fatal.

    The asset shape — `{"image": {"url": ...}}` per entry, an ordered list for
    multiple images — is confirmed from Buffer's own current API docs, not
    guessed. What is NOT confirmed: whether Buffer actually surfaces multiple
    image assets as a real swipeable carousel on TikTok's "photo mode" or a
    Pinterest multi-image pin for THIS project's connected channels, versus
    posting only the first image, or rejecting multi-image assets for a given
    channel type outright. If this misbehaves, check the real response body
    before assuming the schema itself is wrong.
    """
    token = os.environ["BUFFER_API_KEY"]
    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        __typename
        ... on PostActionSuccess { post { id status } }
        ... on InvalidInputError { message }
        ... on LimitReachedError { message }
        ... on UnauthorizedError { message }
        ... on UnexpectedError { message }
        ... on RestProxyError { message }
        ... on NotFoundError { message }
      }
    }
    """
    post_input = {
        "channelId": channel_id,
        "mode": "shareNow",
        "schedulingType": "automatic",
        "needsApproval": False,
        "text": caption,
        "assets": [{"image": {"url": url}} for url in image_urls],
    }
    r = requests.post(
        "https://api.buffer.com/graphql",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": mutation, "variables": {"input": post_input}},
        timeout=60,
    )
    body = r.json()
    result = body.get("data", {}).get("createPost", {})
    if result.get("__typename") != "PostActionSuccess":
        raise PipelineError(f"Buffer image publish to {platform} failed: {result.get('message', body)}")
    post_id = result["post"]["id"]
    log.info("Published image carousel to %s via Buffer: post id %s", platform, post_id)
    return post_id


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

TEMPLATE_INDEX_FILE = "template_index.txt"
CONCEPT_OFFSET_FILE = "concept_offset.txt"

# DERIVED FROM THE ASSET FOLDERS, NOT HARDCODED. This was `N_CONCEPTS = 50` back
# when the c-series was the whole library, and it silently became wrong the moment
# the d-series was promoted into assets/: the offset was taken modulo 50, so with
# 57 pairs on disk indices 50-56 could never be the START of a reel. Every new
# concept added from now on would have been reachable only by mid-reel spillover.
# Deriving it means the rotation covers whatever is actually there.


def _git_push_with_retry(repo_root, max_attempts=5):
    """
    Five independent pipelines now commit+push directly to `main` with no
    server-side coordination (the original daily reel, Hot Takes, Single
    Product Reel, Carousel Post, Dolly Reel), each on its own schedule plus
    workflow_dispatch, all capable of landing a push in the same few-minute
    window. A bare `git push` loses that race outright with a hard
    non-fast-forward failure and no retry -- confirmed for real on
    2026-08-18, when a manually-dispatched Dolly Reel run's own push
    collided with Carousel Post's scheduled run mid-flight and the whole
    pipeline died one step short of publishing, after already building a
    valid 19.8s reel. Retry with `git pull --rebase` between attempts
    instead of failing on the very first collision.
    """
    for attempt in range(1, max_attempts + 1):
        result = subprocess.run(["git", "-C", str(repo_root), "push"], capture_output=True, text=True)
        if result.returncode == 0:
            return
        log.warning("git push failed (attempt %d/%d): %s", attempt, max_attempts, result.stderr.strip())
        if attempt == max_attempts:
            raise PipelineError(f"git push failed after {max_attempts} attempts: {result.stderr.strip()}")
        subprocess.run(["git", "-C", str(repo_root), "pull", "--rebase", "origin", "main"], check=True)
        time.sleep(2 * attempt)


def _read_counter(repo_root, filename, default=0):
    p = Path(repo_root) / filename
    return int(p.read_text().strip()) if p.exists() else default


def _write_and_commit_counter(repo_root, filename, value, message):
    p = Path(repo_root) / filename
    p.write_text(str(value))
    subprocess.run(["git", "-C", str(repo_root), "add", filename], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-m", message], check=True)
    _git_push_with_retry(repo_root)


def fetch_next_template(repo_root, output_dir):
    """
    Pulls the next template reel from the Drive Template Reels folder, rotating
    through whatever's there (grows automatically as more templates get added — the
    rotation just wraps at however many currently exist, not a fixed count of 4).
    """
    from drive_upload import TEMPLATE_REELS_FOLDER_ID, download_file, list_files_in_folder

    templates = list_files_in_folder(TEMPLATE_REELS_FOLDER_ID)
    if not templates:
        raise PipelineError("No template reels found in the Drive Template Reels folder")

    idx = _read_counter(repo_root, TEMPLATE_INDEX_FILE, default=0) % len(templates)
    template = templates[idx]
    log.info("Using template %d/%d: %s", idx + 1, len(templates), template["name"])

    dest = Path(output_dir) / "template.mp4"
    download_file(template["id"], dest)
    return dest, idx, len(templates)


def run_pipeline():
    swatch_dir = os.environ["SWATCH_ASSETS_DIR"]
    application_dir = os.environ["APPLICATION_ASSETS_DIR"]
    # In GitHub Actions this is set automatically; locally it's wherever you cloned
    # this repo. Either way it must be the root of the git working directory that
    # gets pushed to for hosting + all rotation-state counters.
    repo_root = os.environ.get("GITHUB_WORKSPACE") or os.environ.get("REPO_ROOT", ".")
    output_dir = Path(os.environ.get("OUTPUT_DIR", "./output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        template_path, template_idx, n_templates = fetch_next_template(repo_root, output_dir)

        wav_path = extract_and_master_audio(template_path, output_dir / "processed_audio.wav")
        cuts = extract_template_cut_timestamps(template_path)

        n_concepts = len(_pair_swatches_with_applications(swatch_dir, application_dir))
        concept_offset = _read_counter(repo_root, CONCEPT_OFFSET_FILE, default=0) % n_concepts
        reel_path, concepts_used = build_reel_from_template_timing(
            cuts, wav_path, swatch_dir, application_dir,
            output_dir / "final_output_reel.mp4", concept_start_offset=concept_offset,
        )
        duration = get_audio_duration_seconds(wav_path)
        validate_reel_for_meta(reel_path, duration)

        public_url = upload_video_to_public_host(reel_path, repo_root)
        caption, caption_idx = get_next_caption_and_index(repo_root)

        ig_id = publish_to_instagram(public_url, caption)
        # Opt-in escape hatch for A/B-testing whether Meta throttles reach on
        # API-published Facebook posts vs. Instagram's own native auto-cross-
        # post. Off by default (SKIP_FACEBOOK_API unset on every scheduled
        # run) -- only skips the direct call on a manual dispatch that sets
        # it explicitly. Facebook still gets the post either way, just via
        # IG's cross-post setting instead of our API route when skipped.
        skip_facebook_api = os.environ.get("SKIP_FACEBOOK_API", "false").lower() == "true"
        if skip_facebook_api:
            log.info("SKIP_FACEBOOK_API=true -- letting Instagram's auto-cross-post reach Facebook instead of publish_to_facebook()")
            fb_id = None
        else:
            fb_id = publish_to_facebook(public_url, caption, expected_duration_s=duration)
        tiktok_id = publish_to_buffer(public_url, caption, os.environ["BUFFER_TIKTOK_CHANNEL_ID"], "tiktok")
        yt_id = publish_to_buffer(public_url, caption, os.environ["BUFFER_YOUTUBE_CHANNEL_ID"], "youtube",
                                    youtube_title=caption.split("\n")[0][:100])

        # Advance all rotation state ONLY after both platforms confirm — a failed run
        # shouldn't skip a template, a block of concepts, or a caption slot.
        advance_caption_index(repo_root, caption_idx)
        _write_and_commit_counter(repo_root, TEMPLATE_INDEX_FILE, (template_idx + 1) % n_templates,
                                    f"Advance template index to {(template_idx + 1) % n_templates}")
        _write_and_commit_counter(repo_root, CONCEPT_OFFSET_FILE,
                                    (concept_offset + concepts_used) % n_concepts,
                                    f"Advance concept offset to {(concept_offset + concepts_used) % n_concepts}")

        log.info("Done. Instagram media_id=%s Facebook video_id=%s TikTok post_id=%s YouTube post_id=%s "
                  "template=%d/%d concepts_used=%d",
                  ig_id, fb_id, tiktok_id, yt_id, template_idx + 1, n_templates, concepts_used)

    except PipelineError as e:
        log.error("Pipeline stopped: %s", e)
        raise
    except Exception:
        log.exception("Unexpected error in pipeline run")
        raise


if __name__ == "__main__":
    required = ["META_SYSTEM_USER_TOKEN", "META_IG_BUSINESS_ACCOUNT_ID", "META_PAGE_ID",
                "SWATCH_ASSETS_DIR", "APPLICATION_ASSETS_DIR",
                "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN",
                "BUFFER_API_KEY", "BUFFER_TIKTOK_CHANNEL_ID", "BUFFER_YOUTUBE_CHANNEL_ID"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)
    run_pipeline()
