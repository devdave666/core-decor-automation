"""
Long-form faceless explainer, end to end:
  episode table -> 4K Nano Banana Pro images -> ElevenLabs v4 voice -> rendered MP4
  + thumbnail. Every stage is cached under output/<slug>/, so a failed run resumes.

  python explainer_longform/run.py                 # real run (needs GCP auth + ELEVENLABS_API_KEY)
  python explainer_longform/run.py --mock          # placeholder images + silent voice
  python explainer_longform/run.py --mock --limit 30   # render only the first 30 s
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import episodes  # noqa: E402
from images import generate_images, locate_focuses  # noqa: E402
from render import render  # noqa: E402
from thumbnail import make_thumbnail  # noqa: E402
from voice import generate_voice  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", default="ep01")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--limit", type=float, default=None, help="render only first N seconds")
    ap.add_argument("--music", default=None, help="optional licensed music file")
    args = ap.parse_args()

    spec = episodes.build()
    out = HERE / "output" / (spec["slug"] + ("_mock" if args.mock else ""))
    out.mkdir(parents=True, exist_ok=True)
    (out / "script.json").write_text(json.dumps(spec, indent=1))

    t0 = time.time()
    paths = generate_images(spec, out / "images", mock=args.mock)
    locate = locate_focuses(spec, paths, out / "locate.json", mock=args.mock)
    voice = generate_voice(spec, out / "voice", mock=args.mock)
    mp4 = out / "video.mp4"
    dur = render(spec, voice, paths, locate, mp4, limit_s=args.limit, music_path=args.music)
    make_thumbnail(spec, paths, out / "thumbnail.jpg")
    (out / "meta.json").write_text(json.dumps(
        {"title": spec["title"], "description": spec["description"],
         "duration_s": round(dur, 1)}, indent=1))
    print(f"done in {time.time() - t0:.0f}s -> {mp4} ({dur:.1f}s)")


if __name__ == "__main__":
    main()
