"""
Veo generation for architectural_assembly_reel.

ONE 8s veo-3.1-generate-001 Standard generation, image=site (start) /
config.last_frame=after (end) -- the exact single-shot mechanism
daily_villa_reel/run_daily.py already uses, not multiple clips concatenated.
Veo natively supports an 8s duration; there is no need to split the build
into shorter clips and stitch them.

The single structured prompt narrates the ENTIRE progressive snap-assembly
build -- foundation, frame, glass, roof, pool, landscaping, dusk lighting --
as one continuous accelerated sequence, with a matching continuous audio
description covering the same beats in order. Camera is strictly static
throughout (Dev's spec: no pans, no orbit, no shake).

Deliberately workerless/machineless, unlike Daily Villa Reel's visible
cranes+excavators: elements snap into position on their own, which is what
Dev's own spec describes ("elements descending from above, snapping onto the
grid") and sidesteps the exact hallucination failure mode that got
furniture_build_reel paused (workers/hands reading as physically
inconsistent frame to frame).

VEO_NEGATIVE and the post-generation speech check + local de-voice repair
(applied in run_daily.py) are reused verbatim from
daily_villa_reel/run_daily.py -- the hard-won fix for Veo's "ASMR" cue
slipping in a hallucinated human voice.

Usage: python architectural_assembly_reel/generate_veo_clips.py <frames_dir> <out_path.mp4>
Expects <frames_dir>/{site,after}.png
"""
import sys
import time
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image

PROJECT = "core-decor-657616"
LOCATION = "us-central1"
MODEL = "veo-3.1-generate-001"  # Standard, not Fast -- Fast was the quality/hallucination culprit (2026-08-30)
DURATION_S = 8
MAX_RETRIES = 5
RETRY_BASE_S = 20

# The structured Veo prompt (Dev's cinematic-prompt-engineer format, same
# shape as daily_villa_reel's VEO_PROMPT_TEMPLATE). Only [ENVIRONMENT &
# LIGHTING] varies per concept.
VEO_PROMPT_TEMPLATE = """[SHOT TYPE / COMPOSITION]: Static wide establishing shot, ground level, vertical 9:16, the building site centred in frame with the landscape filling the background.
[SUBJECT & ACTION]: An entire warm-minimalist luxury villa assembles itself from bare, empty ground to a completely finished home in one continuous accelerated snap-build -- a gravel driveway and concrete foundation slab snap into place first, then dark timber wall modules and structural steel beams descend rapidly from above and lock into position one after another, then floor-to-ceiling glass panels snap into the open frame in sequence, then the flat cantilevered roofline drops into place as one piece, then the infinity pool basin fills rapidly with water, the outdoor fire pit ignites, and landscaping and warm interior lighting fill in as the sky settles into dusk -- ending locked on the pristine completed villa.
[ENVIRONMENT & LIGHTING]: {concept}. Natural volumetric light shifting to a warm dusk glow by the end, rich cinematic colour, deep clean shadows, real atmosphere and depth.
[CAMERA MOVEMENT]: Strictly static, locked-off frame; absolutely no pans, no orbit, no zoom, no shake.
[AUDIO / DIALOGUE]: Crisp, close-miked, deeply tactile ASMR-style snap-assembly sound design, precisely timed to each element locking into place -- a heavy gravel drop and a deep stone thud as the foundation lands, wooden beams sliding into place with a heavy timber clack and a crisp metallic lock, glass panels suction-locking into the frame one after another with a soft release hiss, a final roof-panel clunk, water rushing in to fill the pool, a soft fire-ignition whoosh, faint wind chimes as dusk settles in. This track contains ONLY mechanical, material and environmental sound. There is NO human voice, NO speech, NO ASMR whispering, NO whispering, NO singing, NO chanting, NO narration and NO spoken words of any language anywhere in the clip. No music, no score."""

# Reused verbatim from daily_villa_reel/run_daily.py -- the fix for Veo's
# "ASMR" cue slipping in a hallucinated human voice -- plus this format's
# own no-worker/no-machinery rule.
VEO_NEGATIVE = (
    "speech, dialogue, talking, conversation, voiceover, narration, human voice, "
    "voices, whispering, whisper, ASMR whispering, singing, humming, chanting, "
    "mumbling, gibberish, foreign language, vocals, people speaking, crowd noise, "
    "radio chatter, "
    "music, musical score, soundtrack, song, melody, background music, lo-fi, "
    "text, captions, subtitles, watermark, logo, timestamp, ui, letterboxing, "
    "black bars, camera shake, jitter, camera pan, camera orbit, low quality, "
    "blurry, distorted architecture, warping, morphing, "
    "construction workers, people, human hands, vehicles, machinery, cranes, "
    "excavators"
)


def veo_prompt_for(concept):
    p = VEO_PROMPT_TEMPLATE.format(concept=concept.rstrip(". "))
    print(f"--- structured Veo prompt ---\n{p}\n")
    return p


def _to_veo_image(path: Path):
    pil = Image.open(path).convert("RGB")
    buf = BytesIO()
    pil.save(buf, format="PNG")
    return types.Image(image_bytes=buf.getvalue(), mime_type="image/png")


def veo_build(site_path, after_path, prompt, out_path):
    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    start, end = _to_veo_image(site_path), _to_veo_image(after_path)

    def submit(res):
        cfg = dict(aspect_ratio="9:16", duration_seconds=DURATION_S, generate_audio=True,
                   number_of_videos=1, last_frame=end, negative_prompt=VEO_NEGATIVE)
        if res:
            cfg["resolution"] = res
        return client.models.generate_videos(
            model=MODEL, prompt=prompt, image=start,
            config=types.GenerateVideosConfig(**cfg))

    def one_generation(res):
        for attempt in range(MAX_RETRIES):
            try:
                op = submit(res)
                break
            except genai_errors.ClientError as e:
                msg = str(e)
                if res and ("resolution" in msg.lower() or "mix of references" in msg.lower()
                            or "not support" in msg.lower() or "INVALID_ARGUMENT" in msg):
                    print(f"  1080p rejected ({msg[:120]}); falling back to default res")
                    return one_generation(None)
                if ("429" in msg or "RESOURCE_EXHAUSTED" in msg) and attempt < MAX_RETRIES - 1:
                    d = RETRY_BASE_S * (2 ** attempt)
                    print(f"  429 on submit, retry in {d}s")
                    time.sleep(d)
                    continue
                raise
        waited = 0
        while not op.done:
            if waited >= 900:
                raise RuntimeError("veo timeout")
            time.sleep(15)
            waited += 15
            op = client.operations.get(op)
            print(f"  ...{waited}s done={op.done}")
        if getattr(op, "error", None):
            raise RuntimeError(f"veo op failed: {op.error}")
        vids = getattr(op.response, "generated_videos", None) or []
        if not vids:
            raise RuntimeError(f"no video: {op.response!r}"[:400])
        return vids[0].video.video_bytes

    print(f"--- veo 3.1 standard: build ({DURATION_S}s) ---")
    data = one_generation("1080p")
    out_path.write_bytes(data)
    print(f"  saved {out_path} ({len(data)} bytes)")


def generate_all(frames: dict, concept: str, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = veo_prompt_for(concept)
    veo_build(frames["site"], frames["after"], prompt, out_path)
    return out_path


def main():
    if len(sys.argv) != 4:
        print("Usage: generate_veo_clips.py <frames_dir> <concept text> <out_path.mp4>")
        raise SystemExit(1)
    frames_dir, concept, out_path = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    frames = {"site": frames_dir / "site.png", "after": frames_dir / "after.png"}
    for stage, p in frames.items():
        if not p.exists():
            raise FileNotFoundError(f"missing expected frame: {p}")
    generate_all(frames, concept, out_path)


if __name__ == "__main__":
    main()
