"""
Villa Reveal Montage -- a NEW, separate pipeline (sibling to
architectural_assembly_reel, not a modification of it) for the chaotic
multi-shot "explosion-to-reveal" reel format, built after gemini-3.8-flash's
full-video critique showed architectural_assembly_reel's single static-camera
build clip has essentially nothing in common with that reference format:
zero cuts vs ~5, zero debris/dust vs heavy debris, locked-off camera vs FPV
dive + barrel-roll + whip-zoom + reverse crane.

Design, following mansion_reel/generate_veo.py's proven multi-clip pattern
(separate Veo generations, re-encoded concat -- independent generations
aren't guaranteed matching encode params):

  Shot 1 (4s) -- FPV dive into a ground explosion: earth bursts open, dust,
                 flying debris and rebar, extreme shake, heavy motion blur.
  Shot 2 (4s) -- Low-angle whip-zoom into the structural frame slamming into
                 the foundation, dust plume, rapid forward tracking.
  Shot 3 (8s) -- Fast reverse crane pull-out and rise, revealing the finished
                 villa; anchored with last_frame=<after.png> from
                 architectural_assembly_reel.generate_concept_frames so the
                 revealed villa matches our established brand design exactly.

This intentionally re-enters the debris/chaos territory that got
furniture_build_reel paused for hallucination issues -- accepted risk, not
an oversight (see run session this was built in). Text-to-video (no start
image) for shots 1-2, same reasoning as mansion_reel: there's no real place
being edited, only shot 3 anchors to a real generated frame.

Usage: python villa_reveal_montage_reel/generate_montage.py <concept text> <out_dir>
Auth: WIF/ADC. Model: veo-3.1-generate-001, 1080p, 9:16, audio on.
"""
import sys
import time
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "architectural_assembly_reel"))
from generate_concept_frames import generate_after, NanoBanana  # noqa: E402

PROJECT = "core-decor-657616"
LOCATION = "us-central1"
MODEL = "veo-3.1-generate-001"  # Standard, not Fast -- project-wide quality/hallucination lesson
POLL_INTERVAL_S = 15
POLL_TIMEOUT_S = 900
MAX_SUBMIT_RETRIES = 5
SUBMIT_RETRY_BASE_S = 20

# Unlike architectural_assembly_reel's VEO_NEGATIVE, this format WANTS shake,
# debris and dust -- only block the generic quality/compliance failure modes.
NEGATIVE_DEFAULT = (
    "text, captions, subtitles, watermark, logo, timestamp, ui, letterboxing, "
    "black bars, "
    "speech, dialogue, talking, human voice, voices, whispering, singing, "
    "chanting, narration, vocals, people speaking, "
    "people, human hands, construction workers, faces, "
    "low quality, blurry, distorted architecture, warping, morphing, extra limbs"
)


def shot_plan(concept):
    return [
        {
            "name": "explosion",
            "duration_s": 4,
            "prompt": (
                "[SHOT TYPE]: FPV drone dive shot, vertical 9:16, plunging rapidly "
                "downward toward bare empty ground. "
                "[ACTION]: The instant the camera reaches the ground it bursts open in a "
                "violent construction-reveal explosion -- shattering earth, chunks of rock "
                "and concrete, dense volumetric dust, spinning rebar and gravel erupting "
                "outward in every direction. The camera weaves and barrel-rolls through the "
                "flying debris. "
                "[CAMERA]: Extreme handheld shake, aggressive motion blur, fast erratic "
                "movement, Dutch-roll tilts, no stabilization. "
                "[LIGHT]: Warm late-afternoon backlight catching the dust and debris "
                "particles, dramatic rim lighting, cinematic haze. "
                "[AUDIO]: A heavy percussive ground-burst impact, cracking rock, a rising "
                "debris-swirl whoosh, no music, no voice."
            ),
        },
        {
            "name": "impact",
            "duration_s": 4,
            "prompt": (
                "[SHOT TYPE]: Low-angle whip-zoom, vertical 9:16, snapping rapidly forward "
                "at ground level toward a concrete foundation slab. "
                "[ACTION]: Dark structural steel beams and timber wall frames slam down "
                "into position on the foundation one after another with hard mechanical "
                "impacts, each landing throwing up a fresh plume of dust that catches the "
                "light; glass panels begin snapping into the open framework as the dust "
                "starts to settle. "
                "[CAMERA]: Fast forward tracking shot with a sudden whip-zoom snap partway "
                "through, moderate handheld shake continuing from the previous impact. "
                "[LIGHT]: Warm golden-hour light through settling dust, deep shadows, rich "
                "cinematic contrast, dense pine woodland visible in the background. "
                "[AUDIO]: Heavy timber and steel impact thuds, a crisp metallic lock on each "
                "beam, glass suction-lock hiss, no music, no voice."
            ),
        },
        {
            "name": "reveal",
            "duration_s": 8,
            "prompt": (
                "[SHOT TYPE / COMPOSITION]: Extreme close, low-angle interior shot, vertical "
                "9:16, camera positioned tight among freshly erected raw timber wall studs and "
                "floor joists, looking out through the open stud framework at a dusty, "
                "backlit stand of pine trees -- exactly the framing of a construction site "
                "moments after the frame went up. "
                "[ACTION]: The camera immediately begins retreating backward and downward, "
                "moving out through the open framed doorway opening directly ahead of it. As "
                "the camera clears the opening and the view widens, the raw studs behind it "
                "complete themselves into finished walls -- glass panels lock into place, the "
                "roofline sets, dust clears from the air -- until, {concept} The villa is now "
                "fully finished -- infinity pool filled and reflecting the sky, fire pit lit, "
                "landscaping settled, warm interior lighting glowing. "
                "[CAMERA MOVEMENT]: One continuous, physically coherent reverse move: first a "
                "backward dolly retreating out through the framed opening at ground level, "
                "matching the tight starting framing exactly, then smoothly transitioning into "
                "a rising crane pulling back and up to a high wide establishing view. No jump "
                "cuts, no sudden scale change, no teleporting to a different vantage point. "
                "[LIGHT]: Warm backlit dust at the start settling into natural volumetric "
                "light and a warm dusk glow by the end, rich cinematic colour, deep clean "
                "shadows, real atmosphere and depth. "
                "[AUDIO]: The dust settles into quiet, water gently lapping the pool edge, a "
                "soft fire crackle, faint evening wind and distant birdsong, no music, no "
                "voice."
            ).format(concept=concept.rstrip(". ") + "."),
            "anchor": "after",
        },
    ]


def _to_veo_image(path: Path):
    pil = Image.open(path).convert("RGB")
    buf = BytesIO()
    pil.save(buf, format="PNG")
    return types.Image(image_bytes=buf.getvalue(), mime_type="image/png")


def _submit(client, prompt, duration, image=None, last_frame=None):
    cfg = dict(
        aspect_ratio="9:16", duration_seconds=int(duration), generate_audio=True,
        number_of_videos=1, negative_prompt=NEGATIVE_DEFAULT, resolution="1080p",
    )
    if last_frame is not None:
        cfg["last_frame"] = last_frame
    for attempt in range(MAX_SUBMIT_RETRIES):
        try:
            kw = dict(model=MODEL, prompt=prompt, config=types.GenerateVideosConfig(**cfg))
            if image is not None:
                kw["image"] = image
            return client.models.generate_videos(**kw)
        except genai_errors.ClientError as e:
            msg = str(e)
            if "resolution" in msg.lower() and "last_frame" not in cfg:
                cfg.pop("resolution", None)
                continue
            if ("429" in msg or "RESOURCE_EXHAUSTED" in msg) and attempt < MAX_SUBMIT_RETRIES - 1:
                d = SUBMIT_RETRY_BASE_S * (2 ** attempt)
                print(f"  429 on submit, retry in {d}s")
                time.sleep(d)
                continue
            raise


def _extract_last_frame(video_path: Path, out_png: Path):
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-sseof", "-0.1", "-i", str(video_path),
         "-frames:v", "1", str(out_png)],
        check=True,
    )
    return out_png


def _generate_clip(client, shot, out_path, after_img_path=None, start_img_path=None):
    print(f"--- {shot['name']} ({shot['duration_s']}s) ---")
    image = _to_veo_image(start_img_path) if start_img_path else None
    last_frame = _to_veo_image(after_img_path) if shot.get("anchor") == "after" else None
    op = _submit(client, shot["prompt"], shot["duration_s"], image=image, last_frame=last_frame)
    waited = 0
    while not op.done:
        if waited >= POLL_TIMEOUT_S:
            raise RuntimeError(f"timeout on {shot['name']}")
        time.sleep(POLL_INTERVAL_S)
        waited += POLL_INTERVAL_S
        op = client.operations.get(op)
        print(f"  ...{waited}s done={op.done}")
    if getattr(op, "error", None):
        raise RuntimeError(f"{shot['name']}: {op.error}")
    vids = getattr(op.response, "generated_videos", None) or []
    if not vids:
        raise RuntimeError(f"{shot['name']}: no video in response")
    out_path.write_bytes(vids[0].video.video_bytes)
    print(f"  saved {out_path} ({out_path.stat().st_size} bytes)")


def concat(paths, dst):
    import subprocess
    cmd = ["ffmpeg", "-y", "-v", "error"]
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


def generate_all(concept, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    print("--- nano banana: AFTER (finished villa, dusk -- anchors the reveal shot) ---")
    nb = NanoBanana()
    after_img = generate_after(nb, concept)
    after_path = out_dir / "after.png"
    after_img.save(after_path)
    print(f"Saved {after_path}")

    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    shots = shot_plan(concept)
    clips = []
    prev_clip = None
    for shot in shots:
        cp = out_dir / f"clip_{shot['name']}.mp4"
        if cp.exists():
            print(f"--- {shot['name']}: reusing existing {cp} ---")
        else:
            start_img_path = None
            if shot.get("anchor") == "after" and prev_clip is not None:
                start_img_path = out_dir / f"{shot['name']}_start.png"
                _extract_last_frame(prev_clip, start_img_path)
            _generate_clip(client, shot, cp, after_img_path=after_path, start_img_path=start_img_path)
        clips.append(cp)
        prev_clip = cp

    raw = out_dir / "raw.mp4"
    concat(clips, raw)
    return raw


def main():
    if len(sys.argv) != 3:
        print("Usage: generate_montage.py <concept text> <out_dir>")
        raise SystemExit(1)
    concept, out_dir = sys.argv[1], Path(sys.argv[2])
    generate_all(concept, out_dir)


if __name__ == "__main__":
    main()
