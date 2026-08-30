"""
Generates the stained-glass reel from the 4-stage frames produced by
generate_concept_frames.py. Sibling to transformation_reel/generate_veo_
clips.py -- reuses its two most recently proven fixes rather than
starting over:

1. **Last-rendered-frame chaining** (transformation_reel v5, confirmed
   working on a real t03 run -- see llms.txt): only the FIRST clip starts
   from a pre-generated still. Every clip after that starts from the
   actual last frame extracted (via ffmpeg) from the PREVIOUS clip's real
   output, not from the next stage's independently-generated still. The
   pre-generated stage stills are still used as each clip's `last_frame=`
   TARGET, so planned direction is unchanged -- only the START of clips
   2-3 differs from the old approach.
2. **Atomic single-action prompts** (furniture_build_reel v8): exactly
   ONE physical action per clip, camera phrase short and first, subject+
   verb immediately after, environment/lighting description kept brief
   and last.

New for this format, per Dev's explicit direction: a NARROW subject (one
small window detail, never a wide room view -- see TIGHT_FRAMING_RULE in
generate_concept_frames.py) and SLOW, deliberate pacing. Every sibling
format's camera phrase says "real-time pacing"; this one says "slow,
unhurried, deliberate pacing" instead -- the whole point this time is
craftsmanship read as careful, not rushed.

Usage: python stained_glass_reel/generate_veo_clips.py <concept_id> <frames_dir> <out_dir>
Expects <frames_dir>/<concept_id>_{raw,assembling,fitting,after}.png
Writes <out_dir>/<concept_id>_clip_a..c.mp4, <out_dir>/<concept_id>_clip_d_reveal.mp4,
and the concatenated <out_dir>/<concept_id>_stained_glass.mp4.
"""
import subprocess
import sys
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from generate_concept_frames import STAGES, VEO_CANVAS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core_decor_reel_pipeline import render_pushin_clip  # noqa: E402

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "us-central1"
MODEL = "veo-3.1-generate-001"  # Standard, not Fast -- Fast was the quality/hallucination culprit (2026-08-30)
CLIP_DURATION_S = 4
HERO_REVEAL_DURATION_S = 2.5
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 600
MAX_SUBMIT_RETRIES = 5
SUBMIT_RETRY_BASE_DELAY_S = 20

# "Slow, unhurried, deliberate" replaces every sibling format's "real-time
# pacing" -- Dev asked explicitly for the artisan's movements to read as
# slowed down, not just not-sped-up.
CAMERA_BASE = "Static locked-off close-up shot, slow and unhurried pacing."

STATIC_SCENE_RULE = (
    "Every object in the frame keeps a consistent count, position, and "
    "appearance except the one thing the artisan is actively touching."
)

NEGATIVE_PROMPT = (
    "spontaneous or unexplained changes to the window, wall, or "
    "workbench objects the artisan is not physically touching, objects "
    "instantly appearing or disappearing, duplicate or doubled tools and "
    "glass pieces, materials changing with no visible cause, objects "
    "flying or moving backward, reverse motion, gravity-defying object "
    "movement, time-lapse or sped-up motion, teleporting props, wide "
    "shot, camera pulling back, background music, musical score, "
    "soundtrack, upbeat music, dramatic music"
)

TRANSITIONS = {
    ("raw", "assembling"): (
        f"{CAMERA_BASE} The artisan slowly guides a soldering iron along "
        f"one seam of lead came, the motion careful and unhurried. "
        f"{STATIC_SCENE_RULE} Warm workshop light. "
        "SFX: a soft hiss of the soldering iron, molten solder settling. "
        "Ambient noise: quiet workshop tone."
    ),
    ("assembling", "fitting"): (
        f"{CAMERA_BASE} The artisan slowly lifts the finished glass panel "
        f"with both hands and eases it into the window frame. "
        f"{STATIC_SCENE_RULE} Warm afternoon light just beginning to "
        "catch the glass. "
        "SFX: a soft wooden creak as the frame receives it. "
        "Ambient noise: quiet room tone."
    ),
    ("fitting", "after"): (
        f"{CAMERA_BASE} The artisan gently presses a glazing point into "
        f"place along the frame edge, then slowly withdraws their hand "
        f"out of frame. {STATIC_SCENE_RULE} Warm sunlight now streaming "
        "fully through the glass. "
        "SFX: a soft click as the glazing point seats. "
        "Ambient noise: warm quiet."
    ),
}


def _extract_last_frame(video_path, out_path):
    subprocess.run(
        ["ffmpeg", "-y", "-sseof", "-0.1", "-i", str(video_path),
         "-update", "1", "-frames:v", "1", str(out_path)],
        check=True,
    )
    return out_path


def _submit_with_retry(client, start_image, end_image, motion_prompt):
    for attempt in range(MAX_SUBMIT_RETRIES):
        try:
            return client.models.generate_videos(
                model=MODEL,
                prompt=motion_prompt,
                image=start_image,
                config=types.GenerateVideosConfig(
                    aspect_ratio="9:16",
                    duration_seconds=CLIP_DURATION_S,
                    generate_audio=True,
                    last_frame=end_image,
                    number_of_videos=1,
                    negative_prompt=NEGATIVE_PROMPT,
                ),
            )
        except genai_errors.ClientError as e:
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            if not is_rate_limit or attempt == MAX_SUBMIT_RETRIES - 1:
                raise
            delay = SUBMIT_RETRY_BASE_DELAY_S * (2 ** attempt)
            print(f"  429 rate-limited on submit, retrying in {delay}s (attempt {attempt + 1}/{MAX_SUBMIT_RETRIES})...")
            time.sleep(delay)


def generate_clip(client, start_image, end_image_path, motion_prompt, out_path):
    print(f"--- generating clip: {out_path.name} ---")
    end_image = types.Image.from_file(location=str(end_image_path))

    operation = _submit_with_retry(client, start_image, end_image, motion_prompt)

    waited = 0
    while not operation.done:
        if waited >= POLL_TIMEOUT_S:
            raise RuntimeError(f"Timed out after {waited}s waiting for {out_path.name}")
        time.sleep(POLL_INTERVAL_S)
        waited += POLL_INTERVAL_S
        operation = client.operations.get(operation)
        print(f"  ...polling, {waited}s elapsed, done={operation.done}")

    if getattr(operation, "error", None):
        raise RuntimeError(f"Operation failed for {out_path.name}: {operation.error}")

    videos = getattr(operation.response, "generated_videos", None) or []
    if not videos:
        raise RuntimeError(f"No generated_videos for {out_path.name}: {operation.response!r}")

    video_bytes = videos[0].video.video_bytes
    out_path.write_bytes(video_bytes)
    print(f"  saved {out_path} ({len(video_bytes)} bytes)")


def _mux_silent_audio(video_path, out_path):
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path),
         "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
         "-shortest", "-c:v", "copy", "-c:a", "aac",
         str(out_path)],
        check=True,
    )
    return out_path


def generate_hero_reveal(after_image_path, out_path):
    print(f"--- generating hero reveal push-in: {out_path.name} ---")
    silent_path = out_path.with_suffix(".silent.mp4")
    render_pushin_clip(
        after_image_path, HERO_REVEAL_DURATION_S, silent_path,
        width=VEO_CANVAS[0], height=VEO_CANVAS[1],
    )
    _mux_silent_audio(silent_path, out_path)
    silent_path.unlink()
    print(f"  saved {out_path}")
    return out_path


def concatenate(clip_paths, out_path):
    cmd = ["ffmpeg", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]
    n = len(clip_paths)
    filter_inputs = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
    cmd += [
        "-filter_complex", f"{filter_inputs}concat=n={n}:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    print(f"Concatenated -> {out_path}")


def main():
    if len(sys.argv) != 4:
        print("Usage: generate_veo_clips.py <concept_id> <frames_dir> <out_dir>")
        raise SystemExit(1)
    concept_id, frames_dir, out_dir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    out_dir.mkdir(parents=True, exist_ok=True)

    frame_paths = {}
    for stage in STAGES:
        p = frames_dir / f"{concept_id}_{stage}.png"
        if not p.exists():
            raise FileNotFoundError(f"Missing expected frame: {p}")
        frame_paths[stage] = p

    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)

    clip_paths = []
    letters = "abc"
    start_image = types.Image.from_file(location=str(frame_paths[STAGES[0]]))
    for i in range(len(STAGES) - 1):
        start_stage, end_stage = STAGES[i], STAGES[i + 1]
        clip_path = out_dir / f"{concept_id}_clip_{letters[i]}.mp4"
        generate_clip(
            client,
            start_image,
            frame_paths[end_stage],
            TRANSITIONS[(start_stage, end_stage)],
            clip_path,
        )
        clip_paths.append(clip_path)

        if i < len(STAGES) - 2:
            last_frame_path = out_dir / f"{concept_id}_clip_{letters[i]}_lastframe.png"
            _extract_last_frame(clip_path, last_frame_path)
            start_image = types.Image.from_file(location=str(last_frame_path))

    hero_path = out_dir / f"{concept_id}_clip_d_reveal.mp4"
    generate_hero_reveal(frame_paths["after"], hero_path)
    clip_paths.append(hero_path)

    final = out_dir / f"{concept_id}_stained_glass.mp4"
    concatenate(clip_paths, final)


if __name__ == "__main__":
    main()
