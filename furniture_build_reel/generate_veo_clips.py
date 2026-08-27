"""
Generates the furniture-build reel from the 5-stage frames produced by
generate_concept_frames.py. Sibling to transformation_reel/generate_veo_clips.py
-- reuses every hardening fix that project already earned the hard way,
rather than re-discovering any of them on a brand new format:

1. Submission-time 429 retry (`_submit_with_retry`) -- this account's
   concurrent-Veo-job cap throws RESOURCE_EXHAUSTED synchronously at
   submission, before there's an operation to poll.
2. ffmpeg concat output pinned to yuv420p/High/level 4.0/faststart --
   Windows Media Player rejects ffmpeg's own default pix_fmt choice.
3. A silent Ken Burns hero-reveal push-in (`render_pushin_clip`) on the
   finished `after` still, appended as a 5th clip -- deterministic, can't
   hallucinate, costs nothing, stronger closing beat than a flat hold.
4. `STATIC_RULE` (affirmative "only what's touched changes") +
   `NEGATIVE_PROMPT` (the real GenerateVideosConfig.negative_prompt field)
   covering both the touch-less-change bug AND the unrequested-background-
   music bug transformation_reel hit on real runs -- applied here from the
   start instead of waiting to hit the same two bugs again on a new format.

Usage: python furniture_build_reel/generate_veo_clips.py <concept_id> <frames_dir> <out_dir>
Expects <frames_dir>/<concept_id>_{materials,framing,building,lighting,after}.png
Writes <out_dir>/<concept_id>_clip_a..d.mp4, <out_dir>/<concept_id>_clip_e_reveal.mp4,
and the concatenated <out_dir>/<concept_id>_build.mp4.
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
MODEL = "veo-3.1-fast-generate-001"
CLIP_DURATION_S = 4
HERO_REVEAL_DURATION_S = 2.5
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 600
MAX_SUBMIT_RETRIES = 5
SUBMIT_RETRY_BASE_DELAY_S = 20

CAMERA_BASE = "Static locked-off shot, real-time pacing, not a time-lapse."

STATIC_RULE = (
    "Every other surface, wall, and object in the frame that the carpenter "
    "is not directly touching stays completely static and unchanged from "
    "the previous frame -- material and color only change exactly where "
    "their hands are working."
)

NEGATIVE_PROMPT = (
    "spontaneous or unexplained changes to walls, floor, or furniture the "
    "carpenter is not physically touching, objects instantly appearing or "
    "disappearing, materials changing with no visible cause, time-lapse or "
    "sped-up motion, teleporting props, background music, musical score, "
    "soundtrack, upbeat music, dramatic music"
)

TRANSITIONS = {
    ("materials", "framing"): (
        f"{CAMERA_BASE} A carpenter kneels and drives screws through a "
        "steel bracket into the wall with a cordless drill, then lifts a "
        "raw wood plank into place across the first brackets. "
        f"{STATIC_RULE} "
        "SFX: the whir and stutter of a cordless drill driving a screw, "
        "a wood plank knocking into place, a tape measure snapping back "
        "into its case. "
        "Ambient noise: quiet room tone, faint birdsong through the window."
    ),
    ("framing", "building"): (
        f"{CAMERA_BASE} A carpenter fits several more raw boards edge to "
        "edge across the frame, running a hand along a seam to check it's "
        f"flush before reaching for the next board. {STATIC_RULE} "
        "SFX: the soft knock of wood settling into place, a light sanding "
        "pass with a cloth, boards shifting against each other. "
        "Ambient noise: quiet room tone, the occasional creak of a knee on "
        "the floor."
    ),
    ("building", "lighting"): (
        f"{CAMERA_BASE} A carpenter peels the adhesive backing off a coil "
        "of LED strip and presses it carefully into a channel along one "
        "edge of the finished piece, the strip beginning to glow warm as "
        f"they work along its length. {STATIC_RULE} "
        "SFX: the crackle of adhesive backing peeling away, a soft press "
        "of fingers along the strip, a faint electronic click as it powers "
        "on. "
        "Ambient noise: quiet room tone, warm and settled."
    ),
    ("lighting", "after"): (
        f"{CAMERA_BASE} A carpenter lays a linen throw across the finished "
        "piece and sets two cushions in place, then steps back out of "
        "frame, leaving the piece fully finished and glowing warm against "
        f"the late-afternoon light through the window. {STATIC_RULE} "
        "SFX: the soft rustle of linen fabric being laid out, the light "
        "thud of a cushion settling into place, quiet footsteps receding. "
        "Ambient noise: warm quiet, faint birdsong through the window."
    ),
}


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


def generate_clip(client, start_image_path, end_image_path, motion_prompt, out_path):
    print(f"--- generating clip: {out_path.name} ---")
    start_image = types.Image.from_file(location=str(start_image_path))
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
    letters = "abcd"
    for i in range(len(STAGES) - 1):
        start_stage, end_stage = STAGES[i], STAGES[i + 1]
        clip_path = out_dir / f"{concept_id}_clip_{letters[i]}.mp4"
        generate_clip(
            client,
            frame_paths[start_stage],
            frame_paths[end_stage],
            TRANSITIONS[(start_stage, end_stage)],
            clip_path,
        )
        clip_paths.append(clip_path)

    hero_path = out_dir / f"{concept_id}_clip_e_reveal.mp4"
    generate_hero_reveal(frame_paths["after"], hero_path)
    clip_paths.append(hero_path)

    final = out_dir / f"{concept_id}_build.mp4"
    concatenate(clip_paths, final)


if __name__ == "__main__":
    main()
