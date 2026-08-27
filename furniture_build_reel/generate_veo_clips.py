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

v2 (2026-08-27): Dev liked f01 but flagged the hook as the weak point --
opening on a plain shot of materials on the floor gives a viewer nothing to
stop scrolling for. Added a ~1.3s flash-forward TEASER clip at the very
START, before `materials`, punching out from the finished piece to the
full reveal before cutting back to raw materials.

v3 (2026-08-27, same day): REMOVED the v2 hook entirely. Dev's later,
explicit rule (stated while reviewing resort_reveal_reel, applies to every
format): "NEVER show the finished product/construction first, that's the
opposite of a good hook." The v2 hook did exactly that. The video now
opens directly on `materials` -- nothing to spoil -- same fix already
applied to resort_reveal_reel.

Also v3: Dev shared external research (Vertex AI Imagen/Veo prompting
guidance) with one claim worth testing directly against this project's
still-open bug -- Dev flagged real furniture_build_reel output (f02) with
objects appearing/disappearing between frames, and STATIC_RULE alone
hadn't fixed it. The research's claim: Veo I2V prompts should use PURE
MOTION VERBS only and never re-describe a subject/object already visible
in the conditioning image, because re-describing static geometry causes
the model to re-render (and warp) it rather than leave it alone. Rewrote
every TRANSITIONS entry to drop material/color/appearance re-description
(no more "steel bracket," "raw wood plank," "cordless drill" as
descriptors -- just the action) and removed STATIC_RULE from the prompt
text entirely, on the theory that stating "everything else stays static"
is ITSELF a form of re-describing the whole scene. NEGATIVE_PROMPT (the
structured field, not inline text) is unchanged and still does the
touch-less-change/music suppression work. Not yet verified against a real
run before this file was rewritten -- the run this change ships with IS
the test.

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

CAMERA_BASE = "Static locked-off shot, steady real-time pacing, not a time-lapse."

NEGATIVE_PROMPT = (
    "spontaneous or unexplained changes to walls, floor, or furniture the "
    "carpenter is not physically touching, objects instantly appearing or "
    "disappearing, materials changing with no visible cause, time-lapse or "
    "sped-up motion, teleporting props, background music, musical score, "
    "soundtrack, upbeat music, dramatic music"
)

# v3: motion-only per Dev's research -- one camera vector (CAMERA_BASE),
# one primary action, one ambient-particle layer, minimal object naming.
# Deliberately does NOT re-describe material, color, or appearance of
# anything already visible in the conditioning image (no "steel bracket,"
# "raw wood plank," "cordless drill" as descriptors) -- the claim being
# tested is that re-describing static geometry is what was causing Veo to
# re-render (and hallucinate/warp) it, not a lack of a "stay static" rule.
TRANSITIONS = {
    ("materials", "framing"): (
        f"{CAMERA_BASE} The carpenter kneels, drives a screw into a "
        "bracket, then lifts a board up into place against the frame. "
        "Fine sawdust drifts through the light. "
        "SFX: a drill motor, a board settling into place. "
        "Ambient noise: quiet room tone, faint birdsong."
    ),
    ("framing", "building"): (
        f"{CAMERA_BASE} The carpenter fits several boards into place edge "
        "to edge, running a hand along each seam to check it sits flush. "
        "Fine sawdust drifts through the light. "
        "SFX: the soft knock of wood settling into place, a light sanding "
        "pass. "
        "Ambient noise: quiet room tone."
    ),
    ("building", "lighting"): (
        f"{CAMERA_BASE} The carpenter peels backing from a strip and "
        "presses it into a channel along one edge, the strip glowing warm "
        "as the hand moves along its length. "
        "SFX: adhesive backing peeling away, a soft press of fingers, a "
        "faint electronic click. "
        "Ambient noise: quiet room tone, warm and settled."
    ),
    ("lighting", "after"): (
        f"{CAMERA_BASE} The carpenter lays a throw down and sets two "
        "cushions in place, then steps back out of frame. "
        "SFX: soft fabric rustle, a light thud, quiet footsteps receding. "
        "Ambient noise: warm quiet, faint birdsong."
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
