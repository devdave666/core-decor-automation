"""
Generates the resort-reveal reel from the 5-stage frames produced by
generate_concept_frames.py. Sibling to transformation_reel/ and
furniture_build_reel/'s Veo scripts -- reuses their hardening (submission-
time 429 retry, Windows-safe ffmpeg encoding, GenerateVideosConfig.
negative_prompt).

v2 (2026-08-27), corrected before the first real run: the original version
of this file opened with a dedicated Veo drone clip showing the ALREADY-
FINISHED resort, meant as a stronger hook than furniture_build_reel's
punch-out zoom (which Dev said didn't land). Dev then gave a direct rule
that applies here retroactively: NEVER show the finished product first --
that is the opposite of a good hook, not a fix for one. Restructured
before any Veo cost was spent on the wrong order:

The video now opens directly on `forest` (pristine, untouched -- nothing to
spoil) and plays the 4 timelapse build-progress clips in order
(forest->clearing->foundation->structure->after). The finished resort is
never seen until clip d's own natural conclusion. The Veo-generated drone
push (still a single, isolated, simple camera move -- the one class of
camera instruction this project's own research flagged as worth trusting)
now runs LAST, as a closing cinematic flourish AFTER the timelapse has
already revealed the resort on its own -- punctuating a payoff that
already happened, not spoiling it in advance. This also matches Dev's own
original plan documented much earlier in this project's research: "static
until a single drone pull-back at the very end."

The four build-progress clips stay static locked-off aerial shots -- but
timelapse-paced, not real-time, per Dev's explicit ask (the opposite of
transformation_reel's "not a time-lapse" rule, and deliberately so: this
format has no workers to look unnaturally sped-up, just accelerated light/
cloud motion implying days passing, which is the genre's own established
look, not a defect). No STATIC_RULE carried over from the sibling formats
either -- that rule exists to stop unexplained changes NOT caused by a
visible worker's hands, but this format has no workers at all; structures
appearing between timelapse frames with nothing visibly building them is
the correct aesthetic here, not the touch-less-change bug those formats
had to fix.

Usage: python resort_reveal_reel/generate_veo_clips.py <concept_id> <frames_dir> <out_dir>
Expects <frames_dir>/<concept_id>_{forest,clearing,foundation,structure,after}.png
Writes <out_dir>/<concept_id>_clip_a..d.mp4, <out_dir>/<concept_id>_clip_e_drone.mp4,
and the concatenated <out_dir>/<concept_id>_resort.mp4.
"""
import subprocess
import sys
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from generate_concept_frames import STAGES

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "us-central1"
MODEL = "veo-3.1-fast-generate-001"
CLIP_DURATION_S = 4
DRONE_FINALE_DURATION_S = 4
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 600
MAX_SUBMIT_RETRIES = 5
SUBMIT_RETRY_BASE_DELAY_S = 20

TIMELAPSE_CAMERA_BASE = (
    "Static locked-off aerial drone shot, fixed altitude and angle, "
    "TIME-LAPSE pacing: clouds streak rapidly across the sky, sunlight "
    "sweeps and shifts quickly as if many days are compressing into "
    "seconds, dappled light moves fast across the canopy."
)

TIMELAPSE_NEGATIVE_PROMPT = (
    "clear-cut deforestation, bulldozers, heavy construction machinery, "
    "cranes, visible construction workers, exposed bare dirt scars, bare "
    "clear-cut ground, vehicles, background music, musical score, "
    "soundtrack, upbeat music, dramatic music"
)

DRONE_FINALE_NEGATIVE_PROMPT = (
    "clear-cut deforestation, bulldozers, heavy construction machinery, "
    "cranes, exposed bare dirt scars, jerky or shaky camera movement, "
    "time-lapse motion, sped-up motion, background music, musical score, "
    "soundtrack, upbeat music, dramatic music"
)

TRANSITIONS = {
    ("forest", "clearing"): (
        f"{TIMELAPSE_CAMERA_BASE} Between frames, a single narrow footpath "
        "or boardwalk trail has appeared winding through the undergrowth, "
        "barely visible through the still-almost-unbroken canopy. "
        "SFX: wind sweeping through the canopy, distant birdsong rising "
        "and falling quickly. "
        "Ambient noise: sped-up wind gusts, no machinery, no engines."
    ),
    ("clearing", "foundation"): (
        f"{TIMELAPSE_CAMERA_BASE} Between frames, a few slender elevated "
        "stilts and platform frames have appeared among the trees, still "
        "mostly concealed beneath the canopy. "
        "SFX: wind through the canopy, a faint creak of timber settling. "
        "Ambient noise: sped-up wind gusts, no machinery, no engines."
    ),
    ("foundation", "structure"): (
        f"{TIMELAPSE_CAMERA_BASE} Between frames, several treehouse "
        "structures have taken shape nestled among the trees, connected "
        "by elevated walkways, canopy still visually dominant over the "
        "new structures. "
        "SFX: wind through the canopy, distant birdsong. "
        "Ambient noise: sped-up wind gusts, no machinery, no engines."
    ),
    ("structure", "after"): (
        f"{TIMELAPSE_CAMERA_BASE} Between frames, the resort reaches full "
        "completion -- warm light begins glowing from within the "
        "structures as dusk falls quickly, the canopy still dominant "
        "around and above every building. "
        "SFX: wind through the canopy settling to a light breeze, evening "
        "birdsong. "
        "Ambient noise: wind fading to a warm quiet as the light-lapse "
        "settles into dusk."
    ),
}

DRONE_FINALE_PROMPT = (
    "Cinematic aerial drone shot, real-time (not time-lapse), a single "
    "slow continuous forward push deeper over the forest canopy, gliding "
    "toward the eco-resort nestled among the trees below, warm light "
    "glowing from within its structures at dusk. Smooth, steady, "
    "professional drone cinematography. "
    "SFX: steady wind past the drone, distant birdsong. "
    "Ambient noise: warm evening quiet, wind through the canopy."
)


def _submit_with_retry(client, image, motion_prompt, negative_prompt, duration, end_image=None):
    config_kwargs = dict(
        aspect_ratio="9:16",
        duration_seconds=duration,
        generate_audio=True,
        number_of_videos=1,
        negative_prompt=negative_prompt,
    )
    if end_image is not None:
        config_kwargs["last_frame"] = end_image
    for attempt in range(MAX_SUBMIT_RETRIES):
        try:
            return client.models.generate_videos(
                model=MODEL,
                prompt=motion_prompt,
                image=image,
                config=types.GenerateVideosConfig(**config_kwargs),
            )
        except genai_errors.ClientError as e:
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            if not is_rate_limit or attempt == MAX_SUBMIT_RETRIES - 1:
                raise
            delay = SUBMIT_RETRY_BASE_DELAY_S * (2 ** attempt)
            print(f"  429 rate-limited on submit, retrying in {delay}s (attempt {attempt + 1}/{MAX_SUBMIT_RETRIES})...")
            time.sleep(delay)


def _poll_and_save(operation, client, out_path):
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


def generate_clip(client, start_image_path, end_image_path, motion_prompt, out_path):
    print(f"--- generating clip: {out_path.name} ---")
    start_image = types.Image.from_file(location=str(start_image_path))
    end_image = types.Image.from_file(location=str(end_image_path))
    operation = _submit_with_retry(
        client, start_image, motion_prompt, TIMELAPSE_NEGATIVE_PROMPT,
        CLIP_DURATION_S, end_image=end_image,
    )
    _poll_and_save(operation, client, out_path)


def generate_drone_finale(client, after_image_path, out_path):
    # Runs LAST, after the timelapse has already revealed the resort on
    # its own -- a closing flourish, not a spoiler. See module docstring.
    print(f"--- generating drone finale: {out_path.name} ---")
    after_image = types.Image.from_file(location=str(after_image_path))
    operation = _submit_with_retry(
        client, after_image, DRONE_FINALE_PROMPT, DRONE_FINALE_NEGATIVE_PROMPT,
        DRONE_FINALE_DURATION_S,
    )
    _poll_and_save(operation, client, out_path)


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

    # Runs last, on purpose -- see module docstring. The timelapse (a-d)
    # already revealed the resort; this is a closing flourish, not a hook.
    drone_path = out_dir / f"{concept_id}_clip_e_drone.mp4"
    generate_drone_finale(client, frame_paths["after"], drone_path)
    clip_paths.append(drone_path)

    final = out_dir / f"{concept_id}_resort.mp4"
    concatenate(clip_paths, final)


if __name__ == "__main__":
    main()
