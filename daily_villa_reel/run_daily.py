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
     visible construction machinery, tactile construction sound, NO music.
  5. Strip ALL metadata (ffmpeg -map_metadata -1 ...). A gemini-2.5-flash
     speech check runs here -- if Veo slipped a human voice in, the audio is
     repaired LOCALLY (hard low-pass + synthesised ambience bed), not by
     re-rendering the clip (~$6 for a sound-only problem).
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
# The audio is ASMR-style construction sound -- crisp, close, tactile MACHINERY
# and MATERIAL sound, which is the whole appeal. The one thing to exclude is
# ASMR *whispering* / any human voice: the first run's "ASMR sound design"
# produced garbled multilingual mumbling, so "ASMR" is now tightly bound to a
# no-voice ban, backed by the negative_prompt + the post-gen speech check +
# local audio repair.
VEO_PROMPT_TEMPLATE = """[SHOT TYPE / COMPOSITION]: High aerial drone establishing shot, very wide, 24mm deep-focus lens, vertical 9:16, the clifftop building site centred with the mountain range filling the background.
[SUBJECT & ACTION]: An entire vast modern luxury villa constructs itself from bare ground to a completely finished home in one continuous accelerated build -- excavation, poured foundation, structural frame raised, concrete floors and full-height glazing installed, roof and cantilevered terraces completed, the cliff-edge infinity pool filling with water, mature landscaping and the driveway set -- while multiple tall tower cranes, tracked excavators, diggers and a long-boom concrete pump work the site continuously throughout, ending locked on the pristine completed villa.
[ENVIRONMENT & LIGHTING]: {concept}. Natural volumetric light, rich cinematic colour, deep clean shadows, real high-altitude atmosphere and depth.
[CAMERA MOVEMENT]: Near-static locked-off aerial hold with an almost imperceptible slow push-in; absolutely no whip pans, no orbit, no shake.
[AUDIO / DIALOGUE]: Crisp, close-miked, deeply tactile ASMR-style construction sound design -- every sound sharp, detailed and satisfyingly up close: the groan and clank of crane cables, hydraulic hiss and reverse-beep of excavators, the heavy slap and surge of a concrete pump, rebar clinking, nail guns firing, large glass panels suction-lifted and set into steel, gravel and grit crunching underfoot, wind sweeping over the exposed ridge, water rushing into the pool. This track contains ONLY mechanical and environmental sound. There is NO human voice, NO speech, NO ASMR whispering, NO whispering, NO singing, NO chanting, NO narration and NO spoken words of any language anywhere in the clip. No music, no score."""

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


def veo_build(before_img, after_img, prompt, out_path):
    client = genai.Client(vertexai=True, project=PROJECT, location=VEO_LOCATION)
    start, end = _to_veo_image(before_img), _to_veo_image(after_img)

    def submit(res):
        # NB: Veo 3 rejects enhance_prompt=False ("cannot be disabled"), so the
        # no-voice enforcement is: prompt wording + negative_prompt + a
        # post-generation speech check that repairs the AUDIO locally (not a
        # full re-render -- a whole re-gen is ~$6 for a sound-track problem).
        cfg = dict(aspect_ratio="9:16", duration_seconds=8, generate_audio=True,
                   number_of_videos=1, last_frame=end, negative_prompt=VEO_NEGATIVE)
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
    data = one_generation("1080p")
    out_path.write_bytes(data)
    print(f"  saved {out_path} ({len(data)} bytes)")


# 8s construction-ambience bed, synthesised -- brown-noise machinery rumble +
# a shaped pink-noise wind layer. Used to mask the audio when Veo slips a voice
# in; keeps the vibe without another paid render.
_AMBIENCE = (
    "anoisesrc=c=brown:d=9:a=0.9,lowpass=f=170,volume=2.0[rumble];"
    "anoisesrc=c=pink:d=9:a=0.5,highpass=f=220,lowpass=f=2600,"
    "tremolo=f=0.13:d=0.85,volume=0.9[wind];"
    "[rumble][wind]amix=inputs=2:duration=longest[amb]"
)


def finalize(src, dst):
    """Strip all metadata (Dev's exact -map_metadata flags). If the Gemini
    speech check hears a voice, rebuild the audio: hard low-pass the Veo track
    to kill speech intelligibility (real machinery low-end survives) and mix in
    the synthesised construction ambience bed."""
    voice = has_speech(src)
    meta = ["-map_metadata", "-1", "-map_metadata:s:v", "-1", "-map_metadata:s:a", "-1"]
    if not voice:
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), *meta,
               "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart", str(dst)]
        subprocess.run(cmd, check=True)
        print(f"  clean audio -- stripped metadata -> {dst}")
        return
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), *meta,
           "-filter_complex",
           f"[0:a]lowpass=f=260,volume=2.2[dv];{_AMBIENCE};"
           "[dv][amb]amix=inputs=2:duration=first:weights=1 0.9,"
           "loudnorm=I=-14:TP=-1.5:LRA=11[a]",
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
           "-shortest", "-movflags", "+faststart", str(dst)]
    subprocess.run(cmd, check=True)
    print(f"  VOICE DETECTED -- de-voiced + ambience bed, metadata stripped -> {dst}")


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
    veo_build(before_img, after_img, prompt, raw)

    clean = out / "villa_reel.mp4"
    finalize(raw, clean)

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
