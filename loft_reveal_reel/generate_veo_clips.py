"""
Generates the loft reveal reel. v2 (2026-08-28), a structural rewrite after
Dev supplied external research that correctly diagnosed v1's real forensic
QA failure (see llms.txt for the full failure report). Three changes, each
mapped directly to one of the research's findings:

1. **No more Veo `last_frame=` target conditioning, anywhere.** v1 gave Veo
   both a start image AND an independently-generated end image to bridge in
   4 seconds. The research's diagnosis: when those two images disagree on
   what furniture/objects exist, Veo has no choice but to warp or "pop"
   things into existence mid-clip to land on the target -- this is
   Google's own documented First/Last-Frame behavior, not a bug, and no
   amount of prompt wording (including this project's own negative_prompt
   field) can override a hard pixel contradiction between two conditioning
   images. v2 calls `generate_videos` with `image=` ONLY, no `last_frame=`
   -- Veo generates forward motion from a single starting point with no
   forced destination.
2. **Motion-only prompts.** Google's own Veo prompting guidance (quoted
   verbatim in Dev's research): "Your source image already provides the
   subject, scene, and style... Do not re-describe the character,
   background, or lighting depicted in the image." v1's TRANSITIONS prompts
   re-described lighting, environment and character identity in every
   clip -- redundant with the image, and per the research, actively
   conflicting with it. v2's prompts are camera + one atomic physical
   action, nothing else. No STATIC_RULE prose, no re-stated identity
   description -- the source image alone carries all of that now.
3. **Interleaved real-frame editing, not a pre-built still chain.** Each
   clip starts from either the original `infested` still (clip A) or an
   edited version of the ACTUAL last frame Veo rendered for the PREVIOUS
   clip (clips B-G) -- via `generate_concept_frames.edit_forward()`, which
   makes exactly ONE small, itemized change to that real frame (e.g. "the
   wall is now painted white") and nothing else. This is the closest this
   pipeline can get to the research's "single spatial anchor" principle
   without true depth/mask-conditioned inpainting: every image after
   `infested` is a small edit of something Veo actually rendered, not a
   fresh independent synthesis, so architecture has far less room to drift
   between clips than v1's fully-independent keyframe chain had.

Each clip is still exactly 4 seconds; still exactly 7 clips per Dev's
original request; still uses last-rendered-frame extraction (proven
technique, unchanged) -- just for the edit-forward step now, not for
picking the next clip's start image directly (that's still true too, since
edit_forward's OUTPUT becomes the next clip's start image).

Usage: python loft_reveal_reel/generate_veo_clips.py <concept_id> <frames_dir> <out_dir>
Expects <frames_dir>/<concept_id>_{character,after,infested}.png (from
generate_concept_frames.py). Writes <out_dir>/<concept_id>_clip_a..g.mp4,
<out_dir>/<concept_id>_stepNN.png (the interleaved edit stills, for
inspection), and the concatenated <out_dir>/<concept_id>_loft.mp4.
"""
import subprocess
import sys
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from generate_concept_frames import CHARACTER_DESCRIPTION, edit_forward

PROJECT = "core-decor-657616"
LOCATION = "us-central1"
MODEL = "veo-3.1-generate-001"  # Standard, not Fast -- Fast was the quality/hallucination culprit (2026-08-30)
CLIP_DURATION_S = 4
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 600
MAX_SUBMIT_RETRIES = 5
SUBMIT_RETRY_BASE_DELAY_S = 20

CAMERA_BASE = "Static locked-off shot, real-time pacing, not a time-lapse."

# Kept as a config-level safety net (a real, separate lever per the SDK's
# own field, not prose inside the main prompt) -- but per the research, it's
# no longer being asked to fight a forced target-frame contradiction, just
# to nudge away from drift during otherwise-unconstrained forward motion.
NEGATIVE_PROMPT = (
    "objects instantly appearing or disappearing, furniture or decor "
    "materializing that wasn't in the starting image, materials changing "
    "with no visible cause, time-lapse or sped-up motion, teleporting "
    "props, live rodents, mice, rats, insects, or any live animals "
    "visible, a second person entering frame, the woman's face, hair, "
    "build, or clothing changing partway through the shot, duplicate or "
    "doubled versions of the woman, background music, musical score, "
    "soundtrack, upbeat music, dramatic music"
)

# Each entry: (motion prompt for Veo -- ONE atomic action, no scene/identity
# re-description) and (edit delta for the still that follows -- None for the
# final clip, which needs no further still). Applied in order.
STEPS = [
    {
        "motion": (
            f"{CAMERA_BASE} She crouches, picks up a full trash bag and a "
            "stack of ruined cardboard boxes, and carries them toward the "
            "door, stepping out of frame. "
            "SFX: the rustle of a heavy trash bag, cardboard scraping the "
            "floor. Ambient noise: faint city hum through the windows."
        ),
        "edit": (
            "the loose debris, droppings and litter have been swept from "
            "the floor -- the room is now clear of clutter, but the "
            "grease marks along the walls, the gnawed holes in the "
            "baseboard, and the dark, worn, damaged wood floor are all "
            "still exactly as before, untouched."
        ),
    },
    {
        "motion": (
            f"{CAMERA_BASE} She kneels at the baseboard and presses a "
            "patch of wire mesh over a gnawed hole, holding it flat with "
            "one hand. "
            "SFX: the soft press of mesh against wood. Ambient noise: "
            "quiet room tone."
        ),
        "edit": (
            "the mesh patch is now fully covered and smoothed over with "
            "pale filler compound, blended flush with the wall -- a small "
            "tray of compound and a putty knife rest on a drop cloth "
            "below it."
        ),
    },
    {
        "motion": (
            f"{CAMERA_BASE} She rolls fresh white paint onto the wall with "
            "a roller on an extension pole, smooth even strokes top to "
            "bottom. "
            "SFX: the wet roll of a paint roller against the wall. "
            "Ambient noise: quiet room tone."
        ),
        "edit": (
            "the wall she was painting is now fully painted a clean bright "
            "white floor to ceiling -- but the floor beneath it is still "
            "the same dark, worn, damaged wood as before, clearly in need "
            "of replacement."
        ),
    },
    {
        "motion": (
            f"{CAMERA_BASE} She kneels and taps a new floorboard into "
            "place edge to edge with a rubber mallet. "
            "SFX: the soft thud of a rubber mallet, a board clicking into "
            "place. Ambient noise: quiet room tone."
        ),
        "edit": (
            "the new light whitewashed-oak flooring she was laying now "
            "fully covers the entire floor of the room, completely "
            "replacing the old dark damaged wood."
        ),
    },
    {
        "motion": (
            f"{CAMERA_BASE} She carries a single black leather armchair "
            "into the room by herself and sets it down carefully on the "
            "new floor. "
            "SFX: the soft thud of the armchair's legs meeting the floor. "
            "Ambient noise: quiet room tone, warm and settled."
        ),
        "edit": (
            "a rolled-up jute area rug now leans against the wall nearby, "
            "waiting to be laid out, and an unlit floor lamp stands in "
            "the corner."
        ),
    },
    {
        "motion": (
            f"{CAMERA_BASE} She unrolls the area rug flat onto the floor "
            "beside the armchair, then sets a potted plant down next to "
            "it. "
            "SFX: the soft unfurling rustle of the rug. Ambient noise: "
            "quiet room tone, warm and settled."
        ),
        "edit": (
            # v2.1 fix: dropped a reference to "the open shelving" here --
            # forensic QA caught an entire bookshelf materializing at this
            # cut because no shelving unit was ever established in any
            # earlier frame; this delta had asked the model to put objects
            # on furniture that didn't exist yet. Only describe objects
            # placed on/beside things already actually in frame.
            "the floor lamp beside the armchair is now positioned and "
            "ready, though still switched off."
        ),
    },
    {
        "motion": (
            f"{CAMERA_BASE} She switches on the floor lamp, warm light "
            "filling the room, then steps back and puts her hands on her "
            "hips, admiring the space she renovated herself. "
            "SFX: the soft click of a lamp switch. Ambient noise: warm "
            "quiet, faint city hum far below."
        ),
        "edit": None,
    },
]


def _extract_last_frame(video_path, out_path):
    subprocess.run(
        ["ffmpeg", "-y", "-sseof", "-0.1", "-i", str(video_path),
         "-update", "1", "-frames:v", "1", str(out_path)],
        check=True,
    )
    return out_path


def _submit_with_retry(client, start_image, motion_prompt):
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


def generate_clip(client, start_image, motion_prompt, out_path):
    print(f"--- generating clip: {out_path.name} ---")
    operation = _submit_with_retry(client, start_image, motion_prompt)

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

    infested_path = frames_dir / f"{concept_id}_infested.png"
    character_path = frames_dir / f"{concept_id}_character.png"
    for p in (infested_path, character_path):
        if not p.exists():
            raise FileNotFoundError(f"Missing expected frame: {p}")

    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)

    character_image = types.Image.from_file(location=str(character_path))

    clip_paths = []
    letters = "abcdefg"
    start_image = types.Image.from_file(location=str(infested_path))
    for i, step in enumerate(STEPS):
        clip_path = out_dir / f"{concept_id}_clip_{letters[i]}.mp4"
        generate_clip(client, start_image, step["motion"], clip_path)
        clip_paths.append(clip_path)

        if step["edit"] is not None:
            last_frame_path = out_dir / f"{concept_id}_clip_{letters[i]}_lastframe.png"
            _extract_last_frame(clip_path, last_frame_path)
            last_frame_img = types.Image.from_file(location=str(last_frame_path))
            # edit_forward expects PIL-style objects loaded via its own
            # module's image-generation path (genai types.Part inline
            # bytes), so re-open the harvested frame through PIL for the
            # image-editing call, keeping this module's Veo-side types.Image
            # objects separate from the image-editing client's inputs.
            from PIL import Image as PILImage
            prev_pil = PILImage.open(last_frame_path).convert("RGB")
            character_pil = PILImage.open(character_path).convert("RGB")
            next_still = edit_forward(client, prev_pil, character_pil, step["edit"])
            step_path = out_dir / f"{concept_id}_step{i + 1:02d}.png"
            next_still.save(step_path)
            print(f"  saved {step_path}")
            start_image = types.Image.from_file(location=str(step_path))

    final = out_dir / f"{concept_id}_loft.mp4"
    concatenate(clip_paths, final)


if __name__ == "__main__":
    main()
