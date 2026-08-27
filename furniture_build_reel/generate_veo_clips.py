"""
Generates the furniture-build reel from the 8-stage frames produced by
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
touch-less-change/music suppression work. CONFIRMED WORKING on a real
run -- 14 frames sampled densely across the output, zero flicker, zero
unexplained appear/disappear (see llms.txt for the full test writeup).

v4 (2026-08-27, same day): Dev shared a second piece of research/feedback,
this one describing generic AI-timelapse failure modes (objects morphing
mid-shot, a bed appearing on an unassembled lumber pile) and proposing a
"fix" that turned out to already be this project's own architecture
(separate keyframes, per-transition Veo calls, locked-off camera) --
nothing to change there. One piece of its advice DID conflict with v3's
confirmed fix, though: "explicitly define unchanged elements in every
prompt" (wall color, floor, light direction) is close to the same
re-description v3 just proved causes hallucination here. Rather than
either blindly applying it or flatly rejecting it, split the difference
and made it a real test: added a short ENVIRONMENT-only anchor to
CAMERA_BASE (wall/floor/window light -- things that are the same in
literally every frame of a single concept) while deliberately still NOT
re-describing the SUBJECT or the OBJECT being worked on, which is what
v3's fix actually targeted. These are different failure modes -- v3 was
about the model re-rendering an object's appearance each time its
material/color got restated; this is testing whether anchoring the
never-changing backdrop helps without reintroducing that.

v5 (2026-08-27, same day): v3 and v4 were BOTH real prompt-wording fixes,
and BOTH failed real verification -- Dev ran actual Gemini multimodal
video analysis (not this project's own sparse-still-frame review, which
had missed all of this) against real f02 and f03 output and found
genuine physically-impossible jumps in both: a bracket system replaced
outright by full cabinetry in one cut, Murphy-bed hardware appearing
fully installed with zero intermediate steps, an entire wall frame
appearing instantly mounted, tools/materials vanishing between the
pre-reveal and reveal shots. Conclusion: the bug was never about prompt
wording. It's that 5 stages made each 4s Veo clip bridge too large a
physical delta to render plausibly, no matter how the prompt for that
clip was phrased. Fixed at the actual source -- generate_concept_frames.py
widened 5 -> 8 stages, splitting exactly the transitions Gemini's
analysis flagged. TRANSITIONS below rewritten to match, keeping v3's
motion-only style (still real-time, NOT time-lapse -- see
generate_concept_frames.py's v2 docstring for why time-lapse pacing was
deliberately rejected here despite being Dev's other suggested fix: this
format has a visible worker, and transformation_reel already hit and
fixed the exact "workers look unnaturally sped up" bug from time-lapse
phrasing once before). Unverified until the next real run -- and per
Dev's correction, "looks clean" now means passing real Gemini video
analysis, not sparse-still-frame sampling.

v6 (2026-08-27, same day): v5's 8/9-stage widening was verified CLEAN by
a naive gemini-2.5-pro pass (raw video, generic prompt) -- Dev then had
Gemini 3.6 Flash (in the "global" Vertex AI location; it 404s in
us-central1, a real regional gap, not unavailability) analyze the SAME
published file with extended thinking + a forensic system_instruction,
and it found severe issues: duplicate drills, bracket counts changing
mid-clip, reverse-motion object pickup, instant color/trim changes.
Re-ran gemini-2.5-pro with the SAME improved prompt/config (not a
different model) and it found the identical issues -- proving the
original "clean" verdict was a METHODOLOGY failure (generic prompt, no
extended thinking), not evidence the video was actually fine. The naive
raw-video-plus-generic-prompt QA check is retired; forensic system_
instruction + `thinking_config=types.ThinkingConfig(thinking_budget=1024)`
is now required for any verification claim.

Two of the newly-confirmed failure modes trace directly back to v3's own
choice to remove STATIC_RULE (duplicate/multiplying objects, background
prop counts changing) -- v3's theory that stating "everything else stays
static" caused re-rendering is now disproven by the SAME forensic
analysis; removing it did not fix the touch-less-change bug, it likely
made background-prop consistency worse with nothing gained. Restored as
`STATIC_SCENE_RULE`, shorter than the original, applied to every
transition. Also reworded the `lighting`->`cleanup` transition, which
Veo had been rendering as tools flying backward into the carpenter's
hands (an ambiguous "gathers and carries out" instruction read as
reversed motion) -- now explicit about a single continuous forward
motion. `NEGATIVE_PROMPT` extended with the specific new failure modes
(duplicate/doubled objects, object counts changing, reverse motion,
gravity-defying movement). Unverified until the next real run with the
now-mandatory forensic QA method.

Usage: python furniture_build_reel/generate_veo_clips.py <concept_id> <frames_dir> <out_dir>
Expects <frames_dir>/<concept_id>_{materials,bracket_start,framing,building,
wiring,lighting,cleanup,after}.png
Writes <out_dir>/<concept_id>_clip_a..h.mp4, <out_dir>/<concept_id>_clip_i_reveal.mp4,
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

CAMERA_BASE = (
    "Static locked-off shot, steady real-time pacing, not a time-lapse. "
    "Same wall, same floor, same window light throughout."
)

# v6: restored an affirmative static-scene constraint (removed in v3 on an
# unverified theory that stating it caused re-rendering) after real forensic
# analysis (gemini-2.5-pro AND gemini-3.6-flash, both with a proper forensic
# prompt + extended thinking) found the SAME v3 "motion-only" output still
# had duplicate tools, bracket counts changing mid-clip, and reversed/
# gravity-defying object motion during cleanup. The theory that removing
# this caused the original bug is now disproven -- removing it did not fix
# anything, and may have made background-prop consistency worse. Kept
# short/generic rather than reverting to v2's full material re-description.
STATIC_SCENE_RULE = (
    "Every object in the frame keeps a consistent count, position, and "
    "appearance except the one thing the carpenter is actively touching."
)

NEGATIVE_PROMPT = (
    "spontaneous or unexplained changes to walls, floor, or furniture the "
    "carpenter is not physically touching, objects instantly appearing or "
    "disappearing, duplicate or doubled tools and objects, the number of "
    "brackets or boards changing between frames, materials changing with "
    "no visible cause, objects flying or moving backward, reverse motion, "
    "gravity-defying object movement, time-lapse or sped-up motion, "
    "teleporting props, background music, musical score, soundtrack, "
    "upbeat music, dramatic music"
)

# v3 style kept (motion-only, minimal object naming), now covering 7 SMALL
# steps instead of 4 larger ones -- v5's actual fix is the narrower delta
# between each adjacent pair, not the wording style.
TRANSITIONS = {
    ("materials", "bracket_start"): (
        f"{CAMERA_BASE} The carpenter kneels and drives a screw, mounting "
        f"one bracket to the wall. {STATIC_SCENE_RULE} "
        "SFX: a drill motor, a bracket settling flush against the wall. "
        "Ambient noise: quiet room tone, faint birdsong."
    ),
    ("bracket_start", "framing"): (
        f"{CAMERA_BASE} The carpenter drives another screw to mount a "
        f"second bracket, then lifts a board up and rests it across them. "
        f"{STATIC_SCENE_RULE} "
        "SFX: a drill motor, a board settling into place. "
        "Ambient noise: quiet room tone."
    ),
    ("framing", "building"): (
        f"{CAMERA_BASE} The carpenter fits several more boards into place "
        f"edge to edge, running a hand along each seam to check it sits "
        f"flush. {STATIC_SCENE_RULE} "
        "SFX: the soft knock of wood settling into place. "
        "Ambient noise: quiet room tone."
    ),
    ("building", "insert"): (
        f"{CAMERA_BASE} The carpenter lifts a large component out of its "
        f"box and fits it into its opening in the structure, pressing it "
        f"flush into place. {STATIC_SCENE_RULE} "
        "SFX: a heavy thud settling into place, cardboard tearing away. "
        "Ambient noise: quiet room tone."
    ),
    ("insert", "wiring"): (
        f"{CAMERA_BASE} The carpenter peels backing from a strip and "
        f"presses it into a channel along one edge, working along its "
        f"length. {STATIC_SCENE_RULE} "
        "SFX: adhesive backing peeling away, a soft press of fingers. "
        "Ambient noise: quiet room tone."
    ),
    ("wiring", "lighting"): (
        f"{CAMERA_BASE} The carpenter presses a small connector together, "
        f"and the strip lights up warm along its length. {STATIC_SCENE_RULE} "
        "SFX: a faint electronic click. "
        "Ambient noise: quiet room tone, warm and settled."
    ),
    ("lighting", "cleanup"): (
        f"{CAMERA_BASE} The carpenter bends down, picks up a box of tools "
        "from the floor with both hands, straightens up, and walks toward "
        "the door carrying it, moving forward and out of frame -- a single "
        f"continuous forward motion, never backward. {STATIC_SCENE_RULE} "
        "SFX: tools clinking inside the box, footsteps receding. "
        "Ambient noise: quiet room tone."
    ),
    ("cleanup", "after"): (
        f"{CAMERA_BASE} The carpenter sets a folded throw down and steps "
        f"back out of frame. {STATIC_SCENE_RULE} "
        "SFX: soft fabric rustle, quiet footsteps receding. "
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
    letters = "abcdefgh"
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

    hero_path = out_dir / f"{concept_id}_clip_i_reveal.mp4"
    generate_hero_reveal(frame_paths["after"], hero_path)
    clip_paths.append(hero_path)

    final = out_dir / f"{concept_id}_build.mp4"
    concatenate(clip_paths, final)


if __name__ == "__main__":
    main()
