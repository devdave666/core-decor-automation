"""
Generates the actual transformation reel from the before/mid/after frames
produced by generate_concept_frames.py. See transformation_reel/ and llms.txt
for why this is a new, standalone content type -- not wired into any
publishing pipeline yet.

Veo 3.1 (confirmed working in this project as veo-3.1-generate-001 -- see
llms.txt "Veo video generation: confirmed working end-to-end") caps a single
first/last-frame generation at 8 seconds. A 15s reel showing "before -> workers
mid-renovation -> after" needs THREE frames and TWO chained 8s generations, not
one:
  clip A: before  -> mid    (demo/prep, workers arriving, work beginning)
  clip B: mid     -> after  (finishing touches, styling, reveal)
concatenated with ffmpeg for a ~15-16s final video. Using "mid" as the shared
frame keeps the two clips visually continuous rather than two independent
before/after pairs.

ASMR audio: no separate audio-generation step exists in this project, and
adding a licensed SFX library is a real decision, not a default to make
silently -- Veo 3.1 generates synced audio natively in the same pass (see
llms.txt / Google's own docs), so both clips are generated with
generate_audio=True and a prompt that explicitly asks for close, tactile,
satisfying renovation sound design (paint rollers, drill, hammer taps, fabric
placement) rather than leaving audio to chance. If that isn't ASMR-quality
enough on real output, review the result before reaching for a licensed SFX
track -- don't assume this is insufficient without checking the actual audio.

Usage: python transformation_reel/generate_veo_clips.py <concept_id> <frames_dir> <out_dir>
Expects <frames_dir>/<concept_id>_before.png, _mid.png, _after.png (from
generate_concept_frames.py). Writes <out_dir>/<concept_id>_clip_a.mp4,
_clip_b.mp4, and the concatenated <out_dir>/<concept_id>_transformation.mp4.
"""
import subprocess
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "us-central1"
MODEL = "veo-3.1-generate-001"
POLL_INTERVAL_S = 15
POLL_TIMEOUT_S = 600

ASMR_AUDIO_NOTE = (
    "Audio: close, tactile, ASMR-style renovation sound design synced to the "
    "action -- the soft roll of a paint roller, taps of a hammer, the whir of a "
    "drill, the rustle of fabric and soft thud as furniture is set down. No "
    "music, no voiceover, no talking."
)


def generate_clip(client, start_image_path, end_image_path, motion_prompt, out_path):
    print(f"--- generating clip: {out_path.name} ---")
    start_image = types.Image.from_file(location=str(start_image_path))
    end_image = types.Image.from_file(location=str(end_image_path))

    operation = client.models.generate_videos(
        model=MODEL,
        prompt=f"{motion_prompt} {ASMR_AUDIO_NOTE}",
        image=start_image,
        config=types.GenerateVideosConfig(
            aspect_ratio="9:16",
            duration_seconds=8,
            generate_audio=True,
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
    # Re-encode via the concat FILTER, not stream-copy via the concat demuxer:
    # two separate Veo generations aren't guaranteed to share identical encoding
    # parameters (GOP structure, exact audio sample rate), and this project has
    # already been burned once by assuming concatenated clips would "just work"
    # downstream (see llms.txt's Facebook Reels truncation bug) -- re-encoding
    # here is cheap and removes that whole class of mismatch.
    cmd = ["ffmpeg", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]
    n = len(clip_paths)
    filter_inputs = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
    cmd += [
        "-filter_complex", f"{filter_inputs}concat=n={n}:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]",
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

    before = frames_dir / f"{concept_id}_before.png"
    mid = frames_dir / f"{concept_id}_mid.png"
    after = frames_dir / f"{concept_id}_after.png"
    for p in (before, mid, after):
        if not p.exists():
            raise FileNotFoundError(f"Missing expected frame: {p}")

    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)

    clip_a = out_dir / f"{concept_id}_clip_a.mp4"
    generate_clip(
        client, before, mid,
        "A beat-down, unfinished room transforms as human tradespeople begin "
        "renovating it: demolition dust settling, a worker starting to roll "
        "paint onto a wall, another beginning to lay new flooring, tools and "
        "materials arriving. Time-lapse-style but with real human movement, "
        "static camera, cinematic warm light building as the work progresses.",
        clip_a,
    )

    clip_b = out_dir / f"{concept_id}_clip_b.mp4"
    generate_clip(
        client, mid, after,
        "The same room's renovation reaches completion: workers finish "
        "installing final details, place furniture and decor, step back and "
        "leave frame, revealing a fully finished, styled, high-end interior. "
        "Static camera, warm lamplight glowing, cinematic reveal.",
        clip_b,
    )

    final = out_dir / f"{concept_id}_transformation.mp4"
    concatenate([clip_a, clip_b], final)


if __name__ == "__main__":
    main()
