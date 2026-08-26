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

v4 (2026-08-26), two hardening fixes learned from a sibling project's Veo work
on this same account, applied before this pipeline's first real run:

1. **generate_videos submission itself now retries on 429**, not just the
   polling loop. The sibling project confirmed this project's ~2-concurrent-
   job cap throws RESOURCE_EXHAUSTED synchronously at submission time, before
   there's even an operation to poll -- a bare `client.models.generate_videos`
   call would crash the whole run on the very first transient rate limit.
   Same backoff shape already used in generate_concept_frames.py.
2. **ffmpeg concat output now pins pix_fmt/profile/level/faststart.** Without
   these, ffmpeg picks its own defaults (observed as yuv444p on the sibling
   project), which plays fine on most platforms but Windows' built-in player
   rejects outright as "unsupported encoding settings." Forcing yuv420p +
   High profile + level 4.0 is the standard broadly-compatible target.

Also v4: a fifth "hero reveal" clip -- a slow push-in on the finished `after`
still, appended after the 4 Veo clips -- for a stronger scroll-stopping final
beat than a flat static hold on the last Veo frame. Built via this project's
own `render_pushin_clip` (core_decor_reel_pipeline.py, already validated on
Hot Takes and Dolly Reel), NOT by asking Veo for a camera move: the sibling
project found Veo's own camera-motion instructions unreliable even for simple
moves, and its recommendation was to isolate any hard camera move as its own
generation rather than blend it into a Veo shot. A deterministic ffmpeg
zoompan on a still costs nothing and can't hallucinate, so it's the safer way
to get that final push. Silent (`_mux_silent_audio`) so it concatenates
cleanly against the Veo clips' real audio tracks.

4 Veo clips x 4s + 1 push-in x 2.5s = 18.5s total. Concatenated with ffmpeg
(re-encode, not stream-copy -- independent sources aren't guaranteed to share
encoding params). Concat handles an audio stream (a=1); the hero clip's is
silence.

v4.1 (2026-08-26), after Dev flagged real t01 output: some surfaces (paint,
flooring) were visibly changing without the tradesperson touching them --
Veo filling the gap between two frames that differ in many places at once by
drifting changes across the whole room rather than confining them to the
worker's hands. Two fixes, both applied to every clip:
1. `STATIC_RULE`, appended to each Action clause -- affirmative ("everything
   the tradesperson ISN'T touching stays static"), not inline negative
   language, consistent with this file's own established rule against
   negative prompt framing.
2. `negative_prompt` on GenerateVideosConfig -- the real structured lever for
   negative prompting Veo actually exposes (confirmed against the installed
   SDK's pydantic model fields), separate from the prose prompt. There is no
   JSON-structured prompt input for this API (checked generate_videos' real
   signature -- prompt is a plain string), so this field is the closest
   equivalent available.

Confirmed working against a real t02 run: sampled frames across the full
18.58s output showed every material change traced to the worker actually
touching it, no recurrence of the t01 bug.

v4.2 (2026-08-26), after Dev caught one clip in the published t02 reel with
unrequested upbeat background music -- every clip's audio cues only ever
specify SFX:/Ambient noise: (diegetic room sound), never music, but nothing
had explicitly ruled music out, so `generate_audio=True` was free to add a
score on its own. Fixed the same way as v4.1's other bug: added music terms
(`background music, musical score, soundtrack, upbeat music, dramatic
music`) to `NEGATIVE_PROMPT` rather than the main prompt. Not yet verified
against a real run.

Usage: python transformation_reel/generate_veo_clips.py <concept_id> <frames_dir> <out_dir>
Expects <frames_dir>/<concept_id>_{before,demo,framing,finishing,after}.png
(from generate_concept_frames.py). Writes <out_dir>/<concept_id>_clip_a..d.mp4,
<out_dir>/<concept_id>_clip_e_reveal.mp4, and the concatenated
<out_dir>/<concept_id>_transformation.mp4.
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

# Appended to every clip's Cinematography clause. Real-time pacing is still
# the fix from v2 (workers looked sped up when this was missing) -- kept
# explicit rather than assumed just because clips are short now.
CAMERA_BASE = "Static locked-off shot, real-time pacing, not a time-lapse."

# v4 addition: the real t01 run showed surfaces changing (paint, flooring)
# with no visible tradesperson touching them -- the two reference frames just
# differ in a lot of places at once, and Veo was filling that gap by drifting
# material changes across the whole room instead of confining them to the
# worker's hands. Affirmative framing per this project's own established rule
# (see this file's v3 header -- negative instructions inside the PROMPT text
# itself read poorly to Veo, same finding as BFL FLUX elsewhere in this repo).
# Appended to every clip's Action clause, right after the specific action
# description, so "everything else stays still" is anchored to a concrete
# subject rather than floating as a generic disclaimer.
STATIC_RULE = (
    "Every other surface, wall, and object in the frame that the tradesperson "
    "is not directly touching stays completely static and unchanged from the "
    "previous frame -- material and color only change exactly where their "
    "hands are working."
)

# The actual "negative prompting" lever for Veo: a dedicated config field
# (GenerateVideosConfig.negative_prompt), separate from the main prompt, not
# inline negative language inside it -- confirmed via the installed SDK's own
# pydantic model fields, not assumed. There is no JSON-structured prompt input
# for this API (generate_videos' prompt argument is a plain string; checked
# the SDK's real method signature before assuming otherwise), so this field is
# the closest real equivalent to "JSON prompting" available here.
#
# v4.2: Dev caught one clip in the published t02 reel with unrequested
# upbeat background music -- every prompt's audio cues only ever specify
# SFX:/Ambient noise: (diegetic room sound), never music, but generate_
# audio=True leaves Veo free to add a score on its own since nothing
# explicitly ruled it out. Added music terms here rather than to the main
# prompt, same reasoning as the rest of this field: this is what negative_
# prompt is for.
NEGATIVE_PROMPT = (
    "spontaneous or unexplained changes to walls, flooring, or furniture the "
    "tradesperson is not physically touching, objects instantly appearing or "
    "disappearing, materials changing with no visible cause, time-lapse or "
    "sped-up motion, teleporting props, background music, musical score, "
    "soundtrack, upbeat music, dramatic music"
)

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
        f"{STATIC_RULE} Pale morning light through a floor-to-ceiling window "
        "wall, exposed damaged walls and ceiling around them. "
        "SFX: the scrape of a dustpan on concrete, chunks of rubble thudding "
        "into a plastic bin, dust brushing off gloved hands. "
        "Ambient noise: faint wind against the glass, distant city hum far "
        "below."
    ),
    ("demo", "framing"): (
        f"{CAMERA_BASE} A tradesperson kneels fitting new flooring boards "
        "edge to edge while another rolls primer onto a repaired wall near "
        "the fireplace, paint tins and boxed materials staged on a drop "
        f"cloth. {STATIC_RULE} "
        "SFX: the soft click of a flooring board snapping into place, the "
        "wet roll of a paint roller against the wall, a paint tin lid "
        "popping open. "
        "Ambient noise: quiet room tone, the occasional creak of a knee on "
        "the drop cloth."
    ),
    ("framing", "finishing"): (
        f"{CAMERA_BASE} A tradesperson carries in an armchair and sets it "
        "down carefully beside a plastic-wrapped sofa, then another hangs a "
        f"framed piece of art above the finished fireplace mantel. {STATIC_RULE} "
        "SFX: the soft thud of upholstered furniture legs meeting the floor, "
        "the crinkle of protective plastic wrap, a light tap as the frame is "
        "leveled against the wall. "
        "Ambient noise: quiet room tone, warm and settled."
    ),
    ("finishing", "after"): (
        f"{CAMERA_BASE} A tradesperson lifts the protective plastic off the "
        "sofa in one smooth pull and steps out of frame, leaving the room "
        "fully finished, lamps glowing warm against the dusk skyline through "
        f"the window wall. {STATIC_RULE} "
        "SFX: the crisp rustle and pull of plastic sheeting coming free, "
        "soft footsteps receding. "
        "Ambient noise: warm quiet, the faint crackle of the lit fireplace."
    ),
}


def _submit_with_retry(client, start_image, end_image, motion_prompt):
    # A 429 here is thrown synchronously at submission, before there's even
    # an operation to poll -- this project's concurrent-Veo-job cap makes
    # that a real, expected transient failure, not an edge case.
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
    # concat's filter graph below expects every input to have an audio
    # stream ([i:a:0]) -- the push-in clip is video-only straight out of
    # ffmpeg's zoompan filter, so give it a silent AAC track truncated to
    # its own length (-shortest) rather than special-casing concat for a
    # mixed audio/no-audio input list.
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
        # Pinned explicitly -- ffmpeg's own default pix_fmt choice (observed
        # as yuv444p) plays fine on most platforms but Windows' built-in
        # player rejects it outright as "unsupported encoding settings."
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

    final = out_dir / f"{concept_id}_transformation.mp4"
    concatenate(clip_paths, final)


if __name__ == "__main__":
    main()
