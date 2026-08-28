"""
Generates the loft reveal reel from the 8-stage frames produced by
generate_concept_frames.py. Sibling to transformation_reel/generate_veo_
clips.py -- reuses its two most recently proven fixes:

1. **Last-rendered-frame chaining** (transformation_reel v5, confirmed
   working on the real t03 run -- see llms.txt): only the FIRST clip starts
   from a pre-generated still. Every clip after that starts from the actual
   last frame extracted (via ffmpeg) from the PREVIOUS clip's real output.
   This matters even more here than on any prior format: the subject is a
   specific woman who has to stay recognizably herself across every cut, and
   chaining Veo's own rendered pixels forward guarantees whatever face/hair/
   outfit Veo actually drew at the end of clip N is exactly what clip N+1
   starts from -- no chance of a "different woman at the cut" mismatch
   between Veo's rendering and the independently-generated stage still.
2. **Real-time pacing + affirmative static-scene framing** (transformation_
   reel v3/v4.1): unchanged from that format, no new pacing request this
   round.

Exactly 7 four-second Veo clips per Dev's explicit request -- no push-in
hero-reveal clip appended this time (every sibling format's extra silent
push-in beat is skipped on purpose here so the count stays exactly 7).

Usage: python loft_reveal_reel/generate_veo_clips.py <concept_id> <frames_dir> <out_dir>
Expects <frames_dir>/<concept_id>_{infested,clearing,repairing,painting,
flooring,furnishing,styling,after}.png
Writes <out_dir>/<concept_id>_clip_a..g.mp4 and the concatenated
<out_dir>/<concept_id>_loft.mp4.
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
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 600
MAX_SUBMIT_RETRIES = 5
SUBMIT_RETRY_BASE_DELAY_S = 20

CAMERA_BASE = "Static locked-off shot, real-time pacing, not a time-lapse."

STATIC_RULE = (
    "Every other surface, wall, and object in the frame that the woman is "
    "not directly touching stays completely static and unchanged from the "
    "previous frame -- material and color only change exactly where her "
    "hands are working."
)

# Base negative terms carried over from transformation_reel, plus two new
# categories specific to this format: rodents (excluded from every frame on
# purpose, see generate_concept_frames.py's header) and identity drift
# (this is the first format where the same named person has to survive 7
# consecutive clips, so appearance consistency gets its own explicit terms).
NEGATIVE_PROMPT = (
    "spontaneous or unexplained changes to walls, flooring, or furniture "
    "the woman is not physically touching, objects instantly appearing or "
    "disappearing, materials changing with no visible cause, time-lapse or "
    "sped-up motion, teleporting props, live rodents, mice, rats, insects, "
    "or any live animals visible, a second person entering frame, the "
    "woman's face, hair, build, or clothing changing partway through the "
    "shot, duplicate or doubled versions of the woman, background music, "
    "musical score, soundtrack, upbeat music, dramatic music"
)

TRANSITIONS = {
    ("infested", "clearing"): (
        f"{CAMERA_BASE} A woman alone in work clothes hauls a full trash "
        "bag and a stack of ruined cardboard boxes toward the door of a "
        "neglected loft, then crouches to sweep debris into a dustpan. "
        f"{STATIC_RULE} Dim grimy light through industrial windows. "
        "SFX: the rustle of a heavy trash bag, cardboard scraping the "
        "floor, the scrape of a dustpan on concrete. "
        "Ambient noise: faint city hum through the windows, distant traffic."
    ),
    ("clearing", "repairing"): (
        f"{CAMERA_BASE} The woman kneels at the baseboard, presses wire "
        "mesh over a gnawed hole, then smooths joint compound over it with "
        f"a putty knife. {STATIC_RULE} Bare work light overhead. "
        "SFX: the scrape of a putty knife, a soft press of mesh against "
        "wood. "
        "Ambient noise: quiet room tone, faint traffic outside."
    ),
    ("repairing", "painting"): (
        f"{CAMERA_BASE} The woman rolls fresh white paint onto the wall "
        "with a roller on an extension pole, smooth even strokes top to "
        f"bottom. {STATIC_RULE} "
        "SFX: the wet roll of a paint roller against the wall. "
        "Ambient noise: quiet room tone."
    ),
    ("painting", "flooring"): (
        f"{CAMERA_BASE} The woman kneels and taps a new floorboard into "
        "place edge to edge with a rubber mallet, then sets a spacer "
        f"wedge against the wall. {STATIC_RULE} Fresh white walls behind "
        "her. "
        "SFX: the soft thud of a rubber mallet, a board clicking into "
        "place. "
        "Ambient noise: quiet room tone."
    ),
    ("flooring", "furnishing"): (
        f"{CAMERA_BASE} The woman carries a single armchair into the "
        "finished room by herself and sets it down carefully on the new "
        f"flooring. {STATIC_RULE} "
        "SFX: the soft thud of the armchair's legs meeting the floor. "
        "Ambient noise: quiet room tone, warm and settled."
    ),
    ("furnishing", "styling"): (
        f"{CAMERA_BASE} The woman unrolls an area rug flat onto the floor "
        "beside the armchair, then sets a potted plant down and steps back "
        f"to check the arrangement. {STATIC_RULE} "
        "SFX: the soft unfurling rustle of the rug, a faint scrape as the "
        "plant pot is set down. "
        "Ambient noise: quiet room tone, warm and settled."
    ),
    ("styling", "after"): (
        f"{CAMERA_BASE} The woman switches on a floor lamp, warm light "
        "filling the finished loft, then steps back and puts her hands on "
        f"her hips, admiring the space she renovated herself. {STATIC_RULE} "
        "Warm lamplight against the dusk skyline through the tall "
        "windows. "
        "SFX: the soft click of a lamp switch. "
        "Ambient noise: warm quiet, faint city hum far below."
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
    letters = "abcdefg"
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

    final = out_dir / f"{concept_id}_loft.mp4"
    concatenate(clip_paths, final)


if __name__ == "__main__":
    main()
