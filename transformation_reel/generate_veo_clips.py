"""
Generates the actual transformation reel from the 5-stage frames produced by
generate_concept_frames.py. See transformation_reel/ and llms.txt for why this
is a new, standalone content type -- not wired into any publishing pipeline yet.

v3, prepared for FUTURE runs per Dev's direction (2026-08-23) -- NOT run for
real against this version yet. Two changes from the v2 output Dev reviewed:

1. **Model tier: veo-3.1-lite-generate-001 -> veo-3.1-fast-generate-001,
   audio back ON.** v2 dropped to Lite/no-audio specifically to cut cost while
   iterating on the visuals (aspect ratio, motion pacing) -- that job is done
   now. Fast is the tier Dev asked for going forward: real native audio
   support (confirmed -- Fast is NOT audio-limited the way Lite is) at
   roughly $0.10-0.15/s vs Standard's $0.75/s, i.e. still ~5-7x cheaper than
   v1's tier while getting the ASMR audio v1 had and v2 deliberately gave up.
   Real cost estimate for 4 clips x 4s: roughly $1.60-$2.40 for a 16s reel
   (vs. v1's ~$12 on Standard, and v2's ~$0.80 on Lite/no-audio).

2. **Prompts rewritten to Google's own documented Veo 3.1 structure**, not
   this project's earlier prose-paragraph style. Researched via Google Cloud's
   official "Ultimate prompting guide for Veo 3.1" (2026). Key changes:
   - Five-part template per clip: [Cinematography] + [Subject] + [Action] +
     [Context] + [Style & Ambiance] -- camera/shot language now stated
     explicitly (e.g. "Static locked-off medium-wide shot") instead of being
     an afterthought.
   - Audio is now cued with the documented syntax instead of a single prose
     paragraph bolted onto every prompt: `SFX: ...` for discrete sound
     effects, `Ambient noise: ...` for background atmosphere. This is what
     "add ASMR if possible" actually means in Veo's own prompting model --
     close, specific, tactile SFX cues (the scrape of a trowel, the snap of a
     paint tin lid) read as ASMR-adjacent; a vague "ASMR-style audio" prose
     instruction (what v1 used) does not give the model anything concrete to
     render.
   - Negative framing removed in favor of affirmative description, per the
     same guide's own "avoid: no man-made structures / better: a desolate
     landscape with no buildings" example -- consistent with the identical
     rule already established for BFL FLUX prompting elsewhere in this repo
     (see llms.txt), now confirmed to also hold for Veo.

See generate_concept_frames.py's own v3 header for the third change Dev asked
for -- a much more dramatically derelict "before" stage for more transformation
"wow factor."

4 clips x 4s = 16s total. Concatenated with ffmpeg (re-encode, not stream-copy
-- two independent Veo generations aren't guaranteed to share encoding params).
Concat now handles an audio stream again (a=1), unlike v2's video-only concat.

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
MODEL = "veo-3.1-fast-generate-001"
CLIP_DURATION_S = 4
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 600

# Appended to every clip's Cinematography clause. Real-time pacing is still
# the fix from v2 (workers looked sped up when this was missing) -- kept
# explicit rather than assumed just because clips are short now.
CAMERA_BASE = "Static locked-off shot, real-time pacing, not a time-lapse."

# One entry per adjacent stage pair, in STAGES order. Each follows Google's
# own five-part structure: Cinematography + Subject + Action + Context +
# Style/Ambiance, with audio cued via SFX:/Ambient noise: rather than prose.
# Each clip only covers the SMALL step between its two specific frames (the
# v2 fix for motion compression) -- kept in v3.
TRANSITIONS = {
    ("before", "demo"): (
        f"{CAMERA_BASE} Two tradespeople in work clothes clear debris from a "
        "derelict high-rise living room: one sweeps broken plaster into a "
        "dustpan, the other carries a bucket of rubble toward a debris bin. "
        "Pale morning light through a floor-to-ceiling window wall, exposed "
        "damaged walls and ceiling around them. "
        "SFX: the scrape of a dustpan on concrete, chunks of rubble thudding "
        "into a plastic bin, dust brushing off gloved hands. "
        "Ambient noise: faint wind against the glass, distant city hum far "
        "below."
    ),
    ("demo", "framing"): (
        f"{CAMERA_BASE} A tradesperson kneels fitting new flooring boards "
        "edge to edge while another rolls primer onto a repaired wall near "
        "the fireplace, paint tins and boxed materials staged on a drop "
        "cloth. "
        "SFX: the soft click of a flooring board snapping into place, the "
        "wet roll of a paint roller against the wall, a paint tin lid "
        "popping open. "
        "Ambient noise: quiet room tone, the occasional creak of a knee on "
        "the drop cloth."
    ),
    ("framing", "finishing"): (
        f"{CAMERA_BASE} A tradesperson carries in an armchair and sets it "
        "down carefully beside a plastic-wrapped sofa, then another hangs a "
        "framed piece of art above the finished fireplace mantel. "
        "SFX: the soft thud of upholstered furniture legs meeting the floor, "
        "the crinkle of protective plastic wrap, a light tap as the frame is "
        "leveled against the wall. "
        "Ambient noise: quiet room tone, warm and settled."
    ),
    ("finishing", "after"): (
        f"{CAMERA_BASE} A tradesperson lifts the protective plastic off the "
        "sofa in one smooth pull and steps out of frame, leaving the room "
        "fully finished, lamps glowing warm against the dusk skyline through "
        "the window wall. "
        "SFX: the crisp rustle and pull of plastic sheeting coming free, "
        "soft footsteps receding. "
        "Ambient noise: warm quiet, the faint crackle of the lit fireplace."
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
    # Re-encode via the concat FILTER, not stream-copy via the concat demuxer --
    # see v1's own header/llms.txt for why. Audio streams are back (generate_
    # audio=True again in v3), so the filter graph concats both video and audio.
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
