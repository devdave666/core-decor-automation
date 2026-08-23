"""
Generates the actual transformation reel from the 5-stage frames produced by
generate_concept_frames.py. See transformation_reel/ and llms.txt for why this
is a new, standalone content type -- not wired into any publishing pipeline yet.

v2, revised after reviewing the first real t01 output with Dev. Three real
problems in v1, all fixed here:

1. **Wrong tier for the job.** v1 used veo-3.1-generate-001 (standard) with
   generate_audio=True, at ~$0.75/s -- $12 for a 16s reel. Dev doesn't want
   native audio at all (ASMR sound is a separate, later decision, not
   something to keep paying Veo's audio premium for while still iterating on
   the VISUALS). Switched to veo-3.1-lite-generate-001, audio off. Confirmed
   present in this project's catalog (see llms.txt / discover_and_test_video_
   model.py output) but not yet load-tested with image+last_frame conditioning
   specifically -- if Lite rejects that combination, that's a real finding to
   report, not to work around silently.

2. **Workers looked sped up.** v1's motion prompts literally said
   "time-lapse-style" -- that's not a Veo rendering quirk, that's this
   project's own prompt asking for exactly the effect Dev didn't want. Removed
   entirely; every motion prompt below now explicitly asks for real-time,
   naturally-paced human movement instead.

3. **Too much narrative distance per clip compounded #2.** Going from bare
   derelict to half-finished in one 8s clip forces the model to compress a lot
   of visual change into a short window, which reads as speed even without an
   explicit time-lapse instruction. generate_concept_frames.py now produces 5
   keyframes (before/demo/framing/finishing/after) instead of 3, so each of
   the 4 clips below only has to bridge ONE small step, and each clip is
   shorter (4s instead of 8s) -- "add more frames and generate smaller clips"
   per Dev's own diagnosis.

4 clips x 4s = 16s total, matching the original target length. Concatenated
with ffmpeg for the final video, same re-encode-not-stream-copy approach as
v1 (two independent Veo generations aren't guaranteed to share encoding
params).

Usage: python transformation_reel/generate_veo_clips.py <concept_id> <frames_dir> <out_dir>
Expects <frames_dir>/<concept_id>_{before,demo,framing,finishing,after}.png
(from generate_concept_frames.py). Writes <out_dir>/<concept_id>_clip_a..d.mp4
and the concatenated <out_dir>/<concept_id>_transformation.mp4.
"""
import subprocess
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

from generate_concept_frames import STAGES

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "us-central1"
MODEL = "veo-3.1-lite-generate-001"
CLIP_DURATION_S = 4
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 600

REALTIME_NOTE = (
    "Real-time, naturally-paced human movement -- NOT a time-lapse, NOT sped "
    "up. Static camera."
)

# One motion prompt per adjacent stage pair, in STAGES order. Each describes
# only the SMALL step between those two specific frames, not the whole arc --
# that's the fix for both the pacing and the sped-up-motion problems above.
TRANSITIONS = {
    ("before", "demo"): (
        "Workers begin clearing the room: sweeping debris, carrying a small "
        f"pile of rubble to a bin, starting to strip a section of wall. {REALTIME_NOTE}"
    ),
    ("demo", "framing"): (
        "Workers install new flooring boards and apply a base coat of paint or "
        f"plaster near the fireplace, materials staged on drop cloths. {REALTIME_NOTE}"
    ),
    ("framing", "finishing"): (
        "Workers carry in and position a piece of furniture, hang a light "
        f"fixture, wipe down a newly finished surface. {REALTIME_NOTE}"
    ),
    ("finishing", "after"): (
        "Workers place final decor items, step back, and leave the frame, "
        f"revealing the completed, styled room. {REALTIME_NOTE}"
    ),
}


def generate_clip(client, start_image_path, end_image_path, motion_prompt, out_path):
    print(f"--- generating clip: {out_path.name} ---")
    start_image = types.Image.from_file(location=str(start_image_path))
    end_image = types.Image.from_file(location=str(end_image_path))

    operation = client.models.generate_videos(
        model=MODEL,
        prompt=motion_prompt,
        image=start_image,
        config=types.GenerateVideosConfig(
            aspect_ratio="9:16",
            duration_seconds=CLIP_DURATION_S,
            generate_audio=False,
            last_frame=end_image,
            number_of_videos=1,
        ),
    )

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


def concatenate(clip_paths, out_path):
    # Re-encode via the concat FILTER, not stream-copy via the concat demuxer --
    # see v1's own header/llms.txt for why. No audio streams now (generate_audio
    # =False), so the filter graph only needs to concat video.
    cmd = ["ffmpeg", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]
    n = len(clip_paths)
    filter_inputs = "".join(f"[{i}:v:0]" for i in range(n))
    cmd += [
        "-filter_complex", f"{filter_inputs}concat=n={n}:v=1:a=0[v]",
        "-map", "[v]",
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

    final = out_dir / f"{concept_id}_transformation.mp4"
    concatenate(clip_paths, final)


if __name__ == "__main__":
    main()
