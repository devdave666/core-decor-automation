"""
Generate a "similar viral video" from a shot plan, with Veo 3.1 Fast at 1080p.

Text-to-video (no start image -- the reference is an AI architectural fantasy,
not a real place being edited). Reads the veo_prompts from analyze.py's JSON
(or a --prompts JSON file), generates each as its own Veo clip, concatenates
with a re-encoding ffmpeg filter (independent Veo generations aren't guaranteed
to share encoding params -- same lesson as transformation_reel).

Usage: python mansion_reel/generate_veo.py <plan.json> <out_dir>
Auth: WIF/ADC. Model: veo-3.1-generate-001 (Standard -- Fast was the
quality/hallucination culprit, 2026-08-30), resolution 1080p, 9:16, audio on.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "us-central1"
MODEL = "veo-3.1-generate-001"  # Standard, not Fast -- Fast was the quality/hallucination culprit (2026-08-30)
POLL_INTERVAL_S = 15
POLL_TIMEOUT_S = 900
MAX_SUBMIT_RETRIES = 5
SUBMIT_RETRY_BASE_S = 20

NEGATIVE_DEFAULT = (
    "text, captions, watermark, logo, ui, timestamp, letterboxing, black bars, "
    "distorted architecture, warping, morphing buildings, people with extra "
    "limbs, blurry, low quality, jump cuts, fast time-lapse"
)


def _submit(client, prompt, negative, duration, ref_bytes=None):
    cfg = dict(
        aspect_ratio="9:16",
        duration_seconds=int(duration),
        generate_audio=True,
        number_of_videos=1,
        negative_prompt=negative or NEGATIVE_DEFAULT,
    )
    if ref_bytes:
        # asset reference. Veo 3.1 FAST rejected references at 1080p ("does not
        # support this mix of references"); on Standard this may be allowed --
        # untested, so kept conservative at 720p + upscale in finish.
        cfg["reference_images"] = [types.VideoGenerationReferenceImage(
            image=types.Image(image_bytes=ref_bytes, mime_type="image/png"),
            reference_type="asset",
        )]
    else:
        cfg["resolution"] = "1080p"
    for attempt in range(MAX_SUBMIT_RETRIES):
        try:
            return client.models.generate_videos(
                model=MODEL, prompt=prompt,
                config=types.GenerateVideosConfig(**cfg),
            )
        except genai_errors.ClientError as e:
            if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and attempt < MAX_SUBMIT_RETRIES - 1:
                d = SUBMIT_RETRY_BASE_S * (2 ** attempt)
                print(f"  429 on submit, retry in {d}s")
                time.sleep(d)
                continue
            raise


def _generate(client, prompt, negative, duration, out_path, ref_bytes=None):
    print(f"--- {out_path.name} ({duration}s{' +styleref' if ref_bytes else ''}) ---\n  {prompt[:160]}...")
    op = _submit(client, prompt, negative, duration, ref_bytes)
    waited = 0
    while not op.done:
        if waited >= POLL_TIMEOUT_S:
            raise RuntimeError(f"timeout on {out_path.name}")
        time.sleep(POLL_INTERVAL_S)
        waited += POLL_INTERVAL_S
        op = client.operations.get(op)
        print(f"  ...{waited}s done={op.done}")
    if getattr(op, "error", None):
        raise RuntimeError(f"{out_path.name}: {op.error}")
    vids = getattr(op.response, "generated_videos", None) or []
    if not vids:
        raise RuntimeError(f"{out_path.name}: no video in response")
    out_path.write_bytes(vids[0].video.video_bytes)
    print(f"  saved {out_path} ({out_path.stat().st_size} bytes)")


def concat(paths, dst):
    cmd = ["ffmpeg", "-y"]
    for p in paths:
        cmd += ["-i", str(p)]
    n = len(paths)
    fin = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
    cmd += ["-filter_complex", f"{fin}concat=n={n}:v=1:a=1[v][a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-level", "4.2", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(dst)]
    subprocess.run(cmd, check=True)
    print(f"concatenated -> {dst}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("out_dir")
    ap.add_argument("--ref-frame", help="style-reference image for regenerated clips")
    ap.add_argument("--clips", help="1-indexed comma list to (re)generate; others reused from out_dir")
    ap.add_argument("--no-concat", action="store_true")
    args = ap.parse_args()

    plan = json.loads(Path(args.plan).read_text())
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = plan["veo_prompts"] if isinstance(plan, dict) else plan
    todo = set(int(x) for x in args.clips.split(",")) if args.clips else set(range(1, len(shots) + 1))
    ref_bytes = Path(args.ref_frame).read_bytes() if args.ref_frame else None

    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    clips = []
    for i, shot in enumerate(shots):
        n = i + 1
        cp = out_dir / f"clip_{n}.mp4"
        if n in todo:
            _generate(client, shot["prompt"], shot.get("negative_prompt", ""),
                      min(int(shot.get("duration_s", 8)), 8), cp, ref_bytes)
        elif not cp.exists():
            raise SystemExit(f"clip {n} not in --clips and {cp} missing")
        else:
            print(f"--- clip_{n}.mp4: reusing existing ---")
        clips.append(cp)

    if not args.no_concat:
        concat(clips, out_dir / "mansion_reel.mp4")


if __name__ == "__main__":
    main()
