"""
Generates the stone-reveal reel from the 7-stage frames produced by
generate_concept_frames.py. Sibling to the other three formats' Veo
scripts -- reuses their hardening (submission-time 429 retry, Windows-safe
ffmpeg encoding, GenerateVideosConfig.negative_prompt, the silent
render_pushin_clip hero reveal).

This format has TWO locations (an industrial stone yard, then a domestic
room), not one continuous space like every sibling format. The cut BETWEEN
them (polishing -> slabs_delivered) is deliberately NOT asked of Veo as
continuous motion -- first/last-frame conditioning asks Veo to invent
motion that turns one photo into another; asking it to interpolate between
a factory and a bathroom isn't a real camera move, it's two different
places, and this project's own research already flags complex/unnatural
camera-motion asks as the least reliable class of Veo prompt. Instead,
`slabs_delivered` gets its own short deterministic ffmpeg push-in (same
`render_pushin_clip` used for the closing hero reveal) -- a clean editorial
cut to the destination room, not a hallucinated blend between two places.

Two Veo-motion segments either side of that cut:
- QUARRY (real machine motion, real-time): quarry_slab->cutting,
  cutting->polishing.
- ROOM (real installer motion, real-time): slabs_delivered->installation,
  installation->lighting, lighting->after.
STATIC_RULE (only what's touched/worked changes) and NEGATIVE_PROMPT
(touch-less changes + unrequested music) both carried over from
furniture_build_reel/transformation_reel, generalized to cover a machine
doing the "touching" in the quarry segment, not just a person.

Usage: python stone_reveal_reel/generate_veo_clips.py <concept_id> <frames_dir> <out_dir>
Expects <frames_dir>/<concept_id>_{quarry_slab,cutting,polishing,
slabs_delivered,installation,lighting,after}.png
Writes <out_dir>/<concept_id>_clip_a..b.mp4 (quarry), _clip_c_delivered.mp4
(ffmpeg cut), _clip_d..f.mp4 (room), _clip_g_reveal.mp4 (hero push-in), and
the concatenated <out_dir>/<concept_id>_stone.mp4.
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
MODEL = "veo-3.1-generate-001"  # Standard, not Fast -- Fast was the quality/hallucination culprit (2026-08-30)
CLIP_DURATION_S = 4
DELIVERED_CUT_DURATION_S = 2.5
HERO_REVEAL_DURATION_S = 2.5
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 600
MAX_SUBMIT_RETRIES = 5
SUBMIT_RETRY_BASE_DELAY_S = 20

CAMERA_BASE = "Static locked-off shot, real-time pacing, not a time-lapse."

STATIC_RULE = (
    "Every other surface and object in the frame that is not directly "
    "being worked on stays completely static and unchanged from the "
    "previous frame -- material and state only change exactly where the "
    "visible machine or hands are working."
)

NEGATIVE_PROMPT = (
    "spontaneous or unexplained changes to surfaces or objects not being "
    "worked on, objects instantly appearing or disappearing, materials "
    "changing with no visible cause, time-lapse or sped-up motion, "
    "teleporting props, background music, musical score, soundtrack, "
    "upbeat music, dramatic music"
)

TRANSITIONS = {
    ("quarry_slab", "cutting"): (
        f"{CAMERA_BASE} A large industrial saw blade slowly cuts into the "
        "edge of the raw stone slab, water spraying continuously to cool "
        f"the blade and the cut face. {STATIC_RULE} "
        "SFX: the whine of the saw motor under load, water spraying and "
        "splattering, a faint hiss of stone dust. "
        "Ambient noise: distant factory machinery hum, echo of a large "
        "warehouse space."
    ),
    ("cutting", "polishing"): (
        f"{CAMERA_BASE} A polishing head grinds slowly across the cut "
        "face of the slab, wet polish and water streaming down as the "
        "surface transforms from dull and rough to a glossy mirror sheen. "
        f"{STATIC_RULE} "
        "SFX: the grinding whir of the polishing head, water sloshing and "
        "dripping steadily, a wet squeak as the head passes. "
        "Ambient noise: distant factory machinery hum."
    ),
    ("slabs_delivered", "installation"): (
        f"{CAMERA_BASE} An installer kneels and carefully lowers a "
        "polished stone slab into place on the bare floor, pressing it "
        f"flush and checking the seam with a straightedge. {STATIC_RULE} "
        "SFX: the scrape of stone sliding into place, a soft tap "
        "leveling it, a straightedge clicking against the seam. "
        "Ambient noise: quiet room tone."
    ),
    ("installation", "lighting"): (
        f"{CAMERA_BASE} An installer peels the adhesive backing off a "
        "warm LED light strip and presses it carefully into the channel "
        "along a seam of the finished stone floor, the strip beginning "
        f"to glow warm as they work along its length. {STATIC_RULE} "
        "SFX: adhesive backing peeling away, a soft press of fingers "
        "along the strip, a faint electronic click as it powers on. "
        "Ambient noise: quiet room tone, warm and settled."
    ),
    ("lighting", "after"): (
        f"{CAMERA_BASE} An installer sets a folded linen towel beside "
        "the freestanding tub and steps back out of frame, leaving the "
        "room fully finished, LED glow washing along every seam line, "
        f"warm light through the glass walls. {STATIC_RULE} "
        "SFX: the soft rustle of linen fabric, quiet footsteps receding. "
        "Ambient noise: warm quiet, faint birdsong from the garden "
        "outside."
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


def generate_pushin(image_path, duration, out_path, label):
    print(f"--- generating {label}: {out_path.name} ---")
    silent_path = out_path.with_suffix(".silent.mp4")
    render_pushin_clip(
        image_path, duration, silent_path,
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

    quarry_pairs = [("quarry_slab", "cutting"), ("cutting", "polishing")]
    letters = "ab"
    for letter, (start_stage, end_stage) in zip(letters, quarry_pairs):
        clip_path = out_dir / f"{concept_id}_clip_{letter}.mp4"
        generate_clip(
            client, frame_paths[start_stage], frame_paths[end_stage],
            TRANSITIONS[(start_stage, end_stage)], clip_path,
        )
        clip_paths.append(clip_path)

    delivered_path = out_dir / f"{concept_id}_clip_c_delivered.mp4"
    generate_pushin(
        frame_paths["slabs_delivered"], DELIVERED_CUT_DURATION_S, delivered_path,
        "editorial cut to destination room",
    )
    clip_paths.append(delivered_path)

    room_pairs = [
        ("slabs_delivered", "installation"),
        ("installation", "lighting"),
        ("lighting", "after"),
    ]
    letters = "def"
    for letter, (start_stage, end_stage) in zip(letters, room_pairs):
        clip_path = out_dir / f"{concept_id}_clip_{letter}.mp4"
        generate_clip(
            client, frame_paths[start_stage], frame_paths[end_stage],
            TRANSITIONS[(start_stage, end_stage)], clip_path,
        )
        clip_paths.append(clip_path)

    hero_path = out_dir / f"{concept_id}_clip_g_reveal.mp4"
    generate_pushin(frame_paths["after"], HERO_REVEAL_DURATION_S, hero_path, "hero reveal push-in")
    clip_paths.append(hero_path)

    final = out_dir / f"{concept_id}_stone.mp4"
    concatenate(clip_paths, final)


if __name__ == "__main__":
    main()
