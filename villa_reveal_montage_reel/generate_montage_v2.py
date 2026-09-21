"""
v2 of villa_reveal_montage_reel, redesigned per Google's own Veo 3.1 prompting
guidance (cloud.google.com/blog: "choose one primary camera behavior per
shot... do not stack several incompatible camera moves") after 4 straight
attempts at a 3-shot single-continuous-transformation approach plateaued
around 4-5/10 on the same shot2->shot3 geometry seam.

Key change: every shot now has BOTH a real start frame and end frame
(Nano Banana Pro stills, the documented Veo "first and last frame" workflow),
and adjacent shots share the literal same connecting image -- so there is no
seam to hide, by construction, rather than something a transition has to
mask after the fact. Each shot's camera instruction is ONE simple movement,
written as a short standalone sentence, not bundled with a transformation
narrative (also per the doc: "write 'the camera pulls back' as a standalone
sentence rather than embedding the motion within a longer description").

Frame chain (4 stills, 3 shots):
  F0 wide_before  -- site.png equivalent: empty land, wide static framing
  F1 debris       -- edited from F0: same framing, mid construction-reveal
                     explosion, dust and debris frozen in the air
  F2 framing      -- edited from F3: same framing as the finished villa,
                     but under construction -- frame up, dust settling
  F3 after        -- the finished villa (existing brand-consistent render)

  Shot 1 (F0->F1): camera dives forward and down toward the ground.
  Shot 2 (F1->F2): camera pushes forward through the settling dust.
  Shot 3 (F2->F3): camera pulls back and rises.

Usage: python villa_reveal_montage_reel/generate_montage_v2.py <concept text> <out_dir>
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
from generate_concept_frames import NanoBanana  # noqa: E402

# Local replacements for architectural_assembly_reel's generate_after/generate_site --
# NOT reusing those directly: their shared CAMERA constant says "fixed tripod
# position", which gemini-3.8-flash's critique caught Nano Banana rendering as an
# actual visible tripod prop in frame. Same STYLE/prompt shape, corrected camera
# wording only. architectural_assembly_reel itself is left untouched.
STYLE = (
    "a warm-minimalist luxury villa built from dark timber, board-formed "
    "concrete and floor-to-ceiling glass, a flat cantilevered roofline, an "
    "infinity-edge pool, a sunken outdoor fire pit and understated modern "
    "landscaping"
)
CAMERA = "[Camera: static wide angle, ground level, locked-off frame, no camera equipment visible in shot]"


def generate_after(nb, concept):
    prompt = (
        f"Ultra-photorealistic architectural photograph, vertical 9:16 "
        f"composition, dusk / golden hour: {concept}. {STYLE.capitalize()} is "
        f"the centrepiece, fully finished and immaculately integrated into "
        f"the natural setting -- warm interior lights glowing from within, "
        f"the infinity pool filled and reflecting the sky, the fire pit lit, "
        f"landscaping mature and settled. {CAMERA} Cinematic, crisp, high "
        f"dynamic range, magazine real-estate quality. No text, no people, "
        f"no watermark, no tripod, no camera gear."
    )
    print("--- nano banana: AFTER (finished villa, dusk) ---")
    return nb.gen(prompt)


def generate_site(nb, after_img):
    prompt = (
        "Show this exact same landscape and scenery -- identical camera "
        "angle, identical terrain, horizon, mountains, sky, weather and "
        "light -- but COMPLETELY REMOVE the villa and every man-made trace: "
        "no building, no pool, no fire pit, no terraces, no driveway, no "
        "retaining walls, no landscaping, no construction, nothing built at "
        "all. Leave only raw untouched natural land where the house was -- "
        "bare earth, rock, native grass and the natural contour of the "
        f"ground. Pristine, empty site. {CAMERA} No tripod, no camera gear. "
        "Everything else in the frame stays exactly the same."
    )
    print("--- nano banana: SITE (empty land, edited from after) ---")
    return nb.gen([prompt, after_img])

PROJECT = "core-decor-657616"
LOCATION = "us-central1"
MODEL = "veo-3.1-generate-001"
POLL_INTERVAL_S = 15
POLL_TIMEOUT_S = 900
MAX_SUBMIT_RETRIES = 5
SUBMIT_RETRY_BASE_S = 20

NEGATIVE_DEFAULT = (
    "text, captions, subtitles, watermark, logo, timestamp, ui, letterboxing, "
    "black bars, "
    "speech, dialogue, talking, human voice, voices, whispering, singing, "
    "chanting, narration, vocals, people speaking, "
    "people, human hands, construction workers, faces, "
    "low quality, blurry, distorted architecture, warping, morphing, extra limbs"
)


def generate_debris_frame(nb, wide_before_img):
    prompt = (
        "Same exact camera framing and location as this image, same terrain and "
        "sky -- but replace the scene with a violent construction-reveal "
        "explosion moment: the ground bursting open, dense golden backlit dust, "
        "flying rebar and rock debris frozen mid-air. Dramatic, cinematic, no "
        "text, no people, no tripod, no camera gear visible."
    )
    print("--- nano banana: DEBRIS (edited from wide_before) ---")
    return nb.gen([prompt, wide_before_img])


def generate_framing_frame(nb, after_img):
    prompt = (
        "Same exact camera framing and location as this finished villa -- but "
        "show it mid-construction instead: dark timber and steel frame mostly "
        "assembled, a few glass panels in, dust settling in the golden light, "
        "no landscaping yet, no pool water yet, no fire lit yet. Photorealistic, "
        "no text, no people, no tripod, no camera gear visible."
    )
    print("--- nano banana: FRAMING (edited from after) ---")
    return nb.gen([prompt, after_img])


def _to_veo_image(pil_img_or_path):
    if isinstance(pil_img_or_path, (str, Path)):
        pil = Image.open(pil_img_or_path).convert("RGB")
    else:
        pil = pil_img_or_path
    buf = BytesIO()
    pil.save(buf, format="PNG")
    return types.Image(image_bytes=buf.getvalue(), mime_type="image/png")


def _submit(client, prompt, duration, image, last_frame):
    cfg = dict(
        aspect_ratio="9:16", duration_seconds=int(duration), generate_audio=True,
        number_of_videos=1, negative_prompt=NEGATIVE_DEFAULT, resolution="1080p",
        last_frame=last_frame,
    )
    for attempt in range(MAX_SUBMIT_RETRIES):
        try:
            return client.models.generate_videos(
                model=MODEL, prompt=prompt, image=image,
                config=types.GenerateVideosConfig(**cfg))
        except genai_errors.ClientError as e:
            msg = str(e)
            if ("429" in msg or "RESOURCE_EXHAUSTED" in msg) and attempt < MAX_SUBMIT_RETRIES - 1:
                d = SUBMIT_RETRY_BASE_S * (2 ** attempt)
                print(f"  429 on submit, retry in {d}s")
                time.sleep(d)
                continue
            raise


def generate_clip(client, name, prompt, duration, start_img, end_img, out_path):
    print(f"--- {name} ({duration}s) ---\n  {prompt}")
    op = _submit(client, prompt, duration, _to_veo_image(start_img), _to_veo_image(end_img))
    waited = 0
    while not op.done:
        if waited >= POLL_TIMEOUT_S:
            raise RuntimeError(f"timeout on {name}")
        time.sleep(POLL_INTERVAL_S)
        waited += POLL_INTERVAL_S
        op = client.operations.get(op)
        print(f"  ...{waited}s done={op.done}")
    if getattr(op, "error", None):
        raise RuntimeError(f"{name}: {op.error}")
    vids = getattr(op.response, "generated_videos", None) or []
    if not vids:
        raise RuntimeError(f"{name}: no video in response")
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
    nb = NanoBanana()

    after_path = out_dir / "F3_after.png"
    if after_path.exists():
        after_img = Image.open(after_path).convert("RGB")
    else:
        print("--- nano banana: F3 AFTER (finished villa, dusk) ---")
        after_img = generate_after(nb, concept)
        after_img.save(after_path)

    wide_before_path = out_dir / "F0_wide_before.png"
    if wide_before_path.exists():
        wide_before_img = Image.open(wide_before_path).convert("RGB")
    else:
        print("--- nano banana: F0 WIDE_BEFORE (empty land, edited from after) ---")
        wide_before_img = generate_site(nb, after_img)
        wide_before_img.save(wide_before_path)

    debris_path = out_dir / "F1_debris.png"
    if debris_path.exists():
        debris_img = Image.open(debris_path).convert("RGB")
    else:
        debris_img = generate_debris_frame(nb, wide_before_img)
        debris_img.save(debris_path)

    framing_path = out_dir / "F2_framing.png"
    if framing_path.exists():
        framing_img = Image.open(framing_path).convert("RGB")
    else:
        framing_img = generate_framing_frame(nb, after_img)
        framing_img.save(framing_path)

    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)

    shots = [
        ("dive", 4, "The camera dives forward and downward rapidly toward the "
                     "ground. Fast, dramatic motion. No music, no voice, no text.",
         wide_before_path, debris_path),
        ("push", 4, "The camera pushes forward steadily through the settling "
                     "dust toward the structure. No music, no voice, no text.",
         debris_path, framing_path),
        ("pullback", 8, "The camera pulls back and rises smoothly, revealing "
                          "the full property. No music, no voice, no text.",
         framing_path, after_path),
    ]

    clips = []
    for name, duration, prompt, start_img, end_img in shots:
        cp = out_dir / f"clip_{name}.mp4"
        if cp.exists():
            print(f"--- {name}: reusing existing {cp} ---")
        else:
            generate_clip(client, name, prompt, duration, start_img, end_img, cp)
        clips.append(cp)

    raw = out_dir / "raw.mp4"
    concat(clips, raw)
    return raw


def main():
    if len(sys.argv) != 3:
        print("Usage: generate_montage_v2.py <concept text> <out_dir>")
        raise SystemExit(1)
    concept, out_dir = sys.argv[1], Path(sys.argv[2])
    generate_all(concept, out_dir)


if __name__ == "__main__":
    main()
