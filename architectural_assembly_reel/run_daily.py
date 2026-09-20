"""
Daily "architectural assembly" reel -- end to end.

Sixth content type, sibling to daily_villa_reel/ -- same shape, in fact:
ONE 8s Veo generation from a "site" (empty land) start frame to an "after"
(finished villa, dusk) end frame, no multi-clip concatenation. The only
difference from daily_villa_reel is the build aesthetic: a stylised,
workerless/machineless "snap-assembly" (elements descending from above and
locking into place) instead of visible construction machinery. See
generate_concept_frames.py and generate_veo_clips.py module docstrings for
the full design rationale.

Per run:
  1. generate_concept_frames.generate_all(): 2 Nano Banana Pro frames
     (site, after).
  2. generate_veo_clips.generate_all(): ONE Veo 3.1 Standard 8s generation,
     image=site / last_frame=after, 9:16, audio, single continuous
     snap-assembly build.
  3. finalize(): strip all metadata; a gemini-2.5-flash speech check repairs
     the audio locally (not a re-render) if Veo slipped in a human voice --
     same fix as daily_villa_reel, reused verbatim since it's a project-wide
     Veo risk, not specific to that format.
  4. Host + publish to Instagram, Facebook, TikTok (via Buffer), YouTube
     (via Buffer).
  5. Advance the concept/caption rotation counters (own to this folder, per
     project convention -- never shared with another pipeline's counters).

Runs daily on a schedule (architectural-assembly-reel.yml) and on
workflow_dispatch. Auth: WIF/ADC + META_*/BUFFER_* secrets, same as
daily_villa_reel.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core_decor_reel_pipeline as core  # noqa: E402

from generate_concept_frames import generate_all as generate_frames
from generate_veo_clips import generate_all as generate_clips

HERE = Path(__file__).resolve().parent
PROJECT = "core-decor-657616"
VEO_LOCATION = "us-central1"

# Reused verbatim from daily_villa_reel/run_daily.py -- 8s ambience bed,
# synthesised brown-noise rumble + shaped pink-noise wind. Masks the audio
# if Veo slips a voice in, without paying for a re-render.
_AMBIENCE = (
    "anoisesrc=c=brown:d=9:a=0.9,lowpass=f=170,volume=2.0[rumble];"
    "anoisesrc=c=pink:d=9:a=0.5,highpass=f=220,lowpass=f=2600,"
    "tremolo=f=0.13:d=0.85,volume=0.9[wind];"
    "[rumble][wind]amix=inputs=2:duration=longest[amb]"
)


def has_speech(video_path):
    """Cheap Gemini audio check -- same as daily_villa_reel. Returns True if
    any human voice is present anywhere in the clip."""
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


def finalize(src, dst):
    """Strip all metadata. If the speech check hears a voice, de-voice the
    track locally (hard low-pass + synthesised ambience bed) instead of
    re-rendering 4 paid Veo clips over a sound-only problem."""
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
    p = HERE / f"{name}.txt"
    return int(p.read_text().strip()) if p.exists() else default


def _advance(name, value, repo_root):
    p = HERE / f"{name}.txt"
    p.write_text(str(value))
    rel = p.relative_to(Path(repo_root)).as_posix()
    subprocess.run(["git", "-C", str(repo_root), "add", rel], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-m",
                    f"architectural-assembly-reel: advance {name} to {value}"], check=True)
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

    frames = generate_frames(concept, out / "frames")
    raw = generate_clips(frames, concept, out / "raw.mp4")

    clean = out / "assembly_reel.mp4"
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
