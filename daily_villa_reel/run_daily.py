"""
Daily "luxury villa builds itself" reel -- end to end.

Per Dev's spec (2026-08-30):
  1. Nano Banana Pro (gemini-3-pro-image, wif:global): render a finished luxury
     villa in good scenery -- the "after" frame.
  2. Nano Banana Pro again on that image: remove everything built, leave only
     barren natural land -- the "before" frame.
  3. The day's scene concept is dropped into a fixed structured Veo prompt
     (Dev's cinematic-prompt-engineer format) -- built in code, no LLM call.
  4. Veo 3.1 STANDARD (veo-3.1-generate-001, 8s, 1080p, 9:16, audio): the villa
     constructs itself from the "before" frame to the "after" frame, with
     visible construction machinery, ASMR sound design, NO music.
  5. Strip ALL metadata (ffmpeg -map_metadata -1 ...).
  6. Host + publish to Instagram + Facebook + TikTok + YouTube.
  7. Advance the concept/caption rotation counters.

Runs daily on a schedule (daily-villa-reel.yml) and on workflow_dispatch.
Auth: WIF/ADC + META_* / BUFFER_* / GOOGLE_OAUTH_* secrets.
"""
import json
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core_decor_reel_pipeline as core  # noqa: E402

HERE = Path(__file__).resolve().parent
PROJECT = "project-58f4f689-36b9-406b-bfa"

IMG_MODELS = ["gemini-3-pro-image", "gemini-3.1-flash-image"]
IMG_LOCATION = "global"
VEO_MODEL, VEO_LOCATION = "veo-3.1-generate-001", "us-central1"

MAX_RETRIES = 5
RETRY_BASE_S = 20

_SAFETY_OFF = [
    types.SafetySetting(category=c, threshold="OFF")
    for c in ("HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_DANGEROUS_CONTENT",
              "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_HARASSMENT")
]

# The structured Veo prompt (Dev's cinematic-prompt-engineer format), built
# directly -- no LLM call. Only [ENVIRONMENT & LIGHTING] varies per concept.
#
# NB: the word "ASMR" is DELIBERATELY not used -- to Veo, "ASMR" cues whispered
# human voice (ASMR = whisper videos), which produced garbled multilingual
# mumbling on the first run. The audio is specified purely as mechanical +
# environmental construction sound, with an explicit no-voice ban, and
# `enhance_prompt=False` so Veo doesn't rewrite it back toward voice.
VEO_PROMPT_TEMPLATE = """[SHOT TYPE / COMPOSITION]: High aerial drone establishing shot, very wide, 24mm deep-focus lens, vertical 9:16, the clifftop building site centred with the mountain range filling the background.
[SUBJECT & ACTION]: An entire vast modern luxury villa constructs itself from bare ground to a completely finished home in one continuous accelerated build -- excavation, poured foundation, structural frame raised, concrete floors and full-height glazing installed, roof and cantilevered terraces completed, the cliff-edge infinity pool filling with water, mature landscaping and the driveway set -- while multiple tall tower cranes, tracked excavators, diggers and a long-boom concrete pump work the site continuously throughout, ending locked on the pristine completed villa.
[ENVIRONMENT & LIGHTING]: {concept}. Natural volumetric light, rich cinematic colour, deep clean shadows, real high-altitude atmosphere and depth.
[CAMERA MOVEMENT]: Near-static locked-off aerial hold with an almost imperceptible slow push-in; absolutely no whip pans, no orbit, no shake.
[AUDIO / DIALOGUE]: Diegetic construction-site sound only, close and detailed: the groan and clank of crane cables, hydraulic hiss and reverse-beep of excavators, the heavy slap and surge of a concrete pump, rebar clinking, nail guns, large glass panels being suction-lifted and set into steel, gravel and grit underfoot, wind sweeping over the exposed ridge, and water rushing into the pool. This audio track contains ONLY mechanical and environmental sound. There is NO human voice, NO speech, NO whispering, NO singing, NO chanting, NO narration and NO spoken words of any language anywhere in the clip. No music, no score."""

VEO_NEGATIVE = (
    "speech, dialogue, talking, conversation, voiceover, narration, human voice, "
    "voices, whispering, whisper, ASMR whispering, singing, humming, chanting, "
    "mumbling, gibberish, foreign language, vocals, people speaking, crowd noise, "
    "radio chatter, "
    "music, musical score, soundtrack, song, melody, background music, lo-fi, "
    "text, captions, subtitles, watermark, logo, timestamp, ui, letterboxing, "
    "black bars, camera shake, jitter, low quality, blurry, distorted "
    "architecture, warping, morphing"
)


def _img_config(model):
    cfg = dict(response_modalities=["IMAGE"],
               image_config=types.ImageConfig(aspect_ratio="9:16", image_size="2K"),
               safety_settings=_SAFETY_OFF)
    if "flash" in model:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_level="MINIMAL")
    return types.GenerateContentConfig(**cfg)


def _first_image(resp):
    for cand in resp.candidates or []:
        for part in cand.content.parts or []:
            inl = getattr(part, "inline_data", None)
            if inl and getattr(inl, "data", None):
                return Image.open(BytesIO(inl.data)).convert("RGB")
    raise RuntimeError(f"no image in response: {resp!r}"[:600])


def _img_call(client, model, contents):
    for attempt in range(MAX_RETRIES):
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=_img_config(model))
        except genai_errors.ClientError as e:
            msg = str(e)
            if ("429" in msg or "RESOURCE_EXHAUSTED" in msg) and attempt < MAX_RETRIES - 1:
                d = RETRY_BASE_S * (2 ** attempt)
                print(f"  429, retry in {d}s")
                time.sleep(d)
                continue
            raise


class NanoBanana:
    def __init__(self):
        self.client = genai.Client(vertexai=True, project=PROJECT, location=IMG_LOCATION)
        self.model = None

    def _gen(self, contents):
        if self.model:
            return _first_image(_img_call(self.client, self.model, contents))
        last = None
        for m in IMG_MODELS:
            try:
                img = _first_image(_img_call(self.client, m, contents))
                print(f"  image model: {m} ({img.width}x{img.height})")
                self.model = m
                return img
            except Exception as e:  # noqa: BLE001
                print(f"  [{m}] failed: {str(e)[:200]}")
                last = e
        raise RuntimeError(f"no image model worked: {last}")

    def after(self, concept):
        prompt = (
            "Ultra-photorealistic aerial architectural photograph, vertical 9:16 "
            f"composition: {concept}. An enormous, fully finished luxury villa is "
            "the centrepiece -- expansive, architecturally striking, with an "
            "infinity pool, landscaped grounds, terraces, glazing and a driveway, "
            "immaculately integrated into the natural setting. Cinematic, crisp, "
            "high dynamic range, magazine real-estate quality. No text, no people, "
            "no watermark."
        )
        print("--- nano banana: AFTER (finished villa) ---")
        return self._gen(prompt)

    def before(self, after_img):
        prompt = (
            "Show this exact same landscape and scenery -- identical camera angle, "
            "identical terrain, horizon, mountains, trees, sky, weather and light "
            "-- but COMPLETELY REMOVE the villa and everything man-made: no "
            "building, no pool, no terraces, no driveway, no walls, no "
            "landscaping, no construction, nothing built at all. Leave only raw "
            "untouched natural land where the house was -- bare earth, rock, "
            "native scrub and the natural contour of the ground. Pristine "
            "wilderness. Everything else in the frame stays exactly the same."
        )
        print("--- nano banana: BEFORE (barren land) ---")
        return self._gen([prompt, after_img])


def veo_prompt_for(concept):
    p = VEO_PROMPT_TEMPLATE.format(concept=concept.rstrip(". "))
    print(f"--- structured Veo prompt ---\n{p}\n")
    return p


def _to_veo_image(pil):
    buf = BytesIO()
    pil.save(buf, format="PNG")
    return types.Image(image_bytes=buf.getvalue(), mime_type="image/png")


def has_speech(video_path):
    """Cheap Gemini audio check -- Veo sometimes injects garbled multilingual
    voice despite the no-dialogue prompt/negative. Returns True if any human
    voice is present."""
    try:
        client = genai.Client(vertexai=True, project=PROJECT, location=VEO_LOCATION)
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=video_path.read_bytes(), mime_type="video/mp4"),
                "Listen to the ENTIRE audio track of this clip. Does it contain any "
                "human voice at all -- speech, talking, whispering, singing, chanting, "
                "narration or spoken words in ANY language? Answer with a single word: "
                "YES or NO.",
            ],
        )
        verdict = (resp.text or "").strip().upper()
        print(f"  speech check: {verdict!r}")
        return verdict.startswith("YES")
    except Exception as e:  # noqa: BLE001
        print(f"  speech check failed ({str(e)[:150]}) -- assuming clean")
        return False


def veo_build(before_img, after_img, prompt, out_path, max_attempts=2):
    client = genai.Client(vertexai=True, project=PROJECT, location=VEO_LOCATION)
    start, end = _to_veo_image(before_img), _to_veo_image(after_img)

    def submit(res):
        cfg = dict(aspect_ratio="9:16", duration_seconds=8, generate_audio=True,
                   number_of_videos=1, last_frame=end, negative_prompt=VEO_NEGATIVE,
                   enhance_prompt=False)  # don't let Veo rewrite the audio spec
        if res:
            cfg["resolution"] = res
        return client.models.generate_videos(
            model=VEO_MODEL, prompt=prompt, image=start,
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

    print("--- veo 3.1 standard: build (8s) ---")
    for gen in range(1, max_attempts + 1):
        data = one_generation("1080p")
        out_path.write_bytes(data)
        print(f"  saved {out_path} ({len(data)} bytes)  [generation {gen}/{max_attempts}]")
        if not has_speech(out_path):
            return True
        if gen < max_attempts:
            print("  -> voice detected, regenerating once")
    print("  voice still present after retries -- audio will be muted")
    return False


def strip_metadata(src, dst, mute=False):
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src),
           "-map_metadata", "-1", "-map_metadata:s:v", "-1", "-map_metadata:s:a", "-1"]
    if mute:
        # last-resort: Veo kept injecting garbled voice -- replace the track
        # with silence rather than ship gibberish.
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                "-shortest"]
    else:
        cmd += ["-c:v", "copy", "-c:a", "copy"]
    cmd += ["-movflags", "+faststart", str(dst)]
    subprocess.run(cmd, check=True)
    print(f"  {'muted + ' if mute else ''}stripped metadata -> {dst}")


def _counter(name, default=0):
    p = HERE / name
    return int(p.read_text().strip()) if p.exists() else default


def _advance(name, value, repo_root):
    p = HERE / name
    p.write_text(str(value))
    rel = p.relative_to(Path(repo_root)).as_posix()
    subprocess.run(["git", "-C", str(repo_root), "add", rel], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-m",
                    f"daily-villa-reel: advance {name} to {value}"], check=True)
    core._git_push_with_retry(repo_root)


def main():
    import os
    repo_root = os.environ.get("GITHUB_WORKSPACE") or os.environ.get("REPO_ROOT", ".")
    out = HERE / "output"
    out.mkdir(exist_ok=True)

    concepts = json.loads((HERE / "concepts.json").read_text())
    captions = json.loads((HERE / "captions.json").read_text())
    ci = _counter("concept_index") % len(concepts)
    capi = _counter("caption_index") % len(captions)
    concept = concepts[ci]
    caption = captions[capi]
    print(f"concept {ci + 1}/{len(concepts)}: {concept[:90]}...")

    nb = NanoBanana()
    after_img = nb.after(concept)
    after_img.save(out / "after.png")
    before_img = nb.before(after_img)
    before_img.save(out / "before.png")

    prompt = veo_prompt_for(concept)
    raw = out / "raw.mp4"
    audio_ok = veo_build(before_img, after_img, prompt, raw)

    clean = out / "villa_reel.mp4"
    strip_metadata(raw, clean, mute=not audio_ok)

    duration = core.get_audio_duration_seconds(clean)
    core.validate_reel_for_meta(clean, duration)

    public_url = core.upload_video_to_public_host(clean, repo_root)
    print(f"hosted: {public_url}")

    ig = core.publish_to_instagram(public_url, caption)
    fb = core.publish_to_facebook(public_url, caption, expected_duration_s=duration)
    tk = core.publish_to_buffer(public_url, caption, os.environ["BUFFER_TIKTOK_CHANNEL_ID"], "tiktok")
    yt = core.publish_to_buffer(public_url, caption, os.environ["BUFFER_YOUTUBE_CHANNEL_ID"], "youtube",
                                youtube_title=caption.split("\n")[0][:100])
    print(f"Done. IG={ig} FB={fb} TikTok={tk} YouTube={yt}")

    _advance("concept_index", (ci + 1) % len(concepts), repo_root)
    _advance("caption_index", (capi + 1) % len(captions), repo_root)


if __name__ == "__main__":
    main()
