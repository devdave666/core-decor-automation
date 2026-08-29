"""
Reverse-engineer a viral short-form video with real Gemini multimodal analysis
(whole-video, not still-frame sampling -- same standard as
loft_reveal_reel/_forensic_qa.py), and emit a Veo 3.1 shot plan.

Usage: python mansion_reel/analyze.py <video.mp4> [out.json]
Auth: WIF/ADC. Model: gemini-2.5-pro @ us-central1 (proven for video), falls
back to gemini-3.6-flash @ global.
"""
import json
import re
import sys
from pathlib import Path

from google import genai
from google.genai import types

PROJECT = "project-58f4f689-36b9-406b-bfa"
MODELS = [("us-central1", "gemini-2.5-pro"), ("global", "gemini-3.6-flash")]

SYSTEM = (
    "You are a short-form video strategist and an AI video director. You "
    "reverse-engineer viral vertical videos: what makes them stop the scroll, "
    "the exact visual style, the camera language, the edit structure, the "
    "sound design -- then you translate that into precise text-to-video "
    "prompts for Google Veo 3.1. Be concrete and specific; no vague adjectives "
    "without the visual detail behind them."
)

PROMPT = """Analyse this vertical video shot by shot, then reverse-engineer it.

Return ONLY a JSON object with these keys:
- "hook": what happens in the first ~1.5s and why it stops the scroll
- "genre": the content genre / trend this belongs to
- "why_viral": array of specific reasons this performs (save-rate, watch-time, shareability drivers)
- "visual_style": a detailed spec (architecture style, materials, palette, time of day, lighting, level of symmetry, lens feel, grade)
- "camera": the specific drone/camera moves used, in order
- "structure": array of {t, beat} objects -- the edit beats with approximate timestamps
- "audio": the sound design (ambient, sfx, music character)
- "veo_prompts": array of exactly 3 objects, each {clip, duration_s, prompt, negative_prompt}
    covering a similar ~24s video as three 8s Veo 3.1 shots. Each "prompt" must be a
    single rich paragraph in Veo's style: [camera move] + [subject] + [action/mood] +
    [setting detail] + [lighting/time] + [style], and include an "Ambient:"/"SFX:" audio
    cue at the end. Keep it the same genre and style as this video but an original estate,
    vertical 9:16.

No prose outside the JSON."""


def _extract_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else None


def main():
    video = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else video.with_suffix(".analysis.json")
    data = video.read_bytes()
    print(f"loaded {video} ({len(data)} bytes)")

    last_err = None
    for loc, model in MODELS:
        try:
            client = genai.Client(vertexai=True, project=PROJECT, location=loc)
            resp = client.models.generate_content(
                model=model,
                contents=[types.Part.from_bytes(data=data, mime_type="video/mp4"), PROMPT],
                config=types.GenerateContentConfig(system_instruction=SYSTEM),
            )
            text = resp.text
            print(f"\n=== {model} @ {loc} ===\n{text}\n")
            parsed = _extract_json(text)
            if parsed:
                out.write_text(json.dumps(parsed, indent=2))
                print(f"wrote {out}")
                return
            print("  (could not parse JSON, trying next model)")
        except Exception as e:  # noqa: BLE001
            print(f"  [{model}@{loc}] failed: {str(e)[:300]}")
            last_err = e
    raise SystemExit(f"analysis failed: {last_err}")


if __name__ == "__main__":
    main()
