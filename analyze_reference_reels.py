"""
One-off analysis tool for analyze-eseries-reference.yml. Downloads every video
in a given Drive folder and extracts what's actually needed to understand a
viral reel's format: real cut timing (reusing extract_template_cut_timestamps()
from core_decor_reel_pipeline.py -- the SAME scene-detection already trusted
for the main pipeline/Dolly Reel/Hot Takes, not a new guess), basic ffprobe
metadata, and a handful of evenly-spaced frames per video. Writes everything
to analysis_output/ for the workflow to upload as a build artifact. Read-only
against Drive; not part of any content pipeline.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core_decor_reel_pipeline as core  # noqa: E402
from drive_upload import list_files_in_folder, download_file  # noqa: E402

FOLDER_ID = os.environ["FOLDER_ID"]
FRAMES_PER_VIDEO = int(os.environ.get("FRAMES_PER_VIDEO", "8"))
OUT_DIR = Path("analysis_output")


def ffprobe_json(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(r.stdout)


def extract_frames(video_path, out_prefix, duration, count):
    paths = []
    for i in range(count):
        t = duration * (i + 0.5) / count  # evenly spaced, centered in each slice
        out_path = OUT_DIR / f"{out_prefix}_frame{i:02d}_t{t:.2f}s.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(t), "-i", str(video_path), "-frames:v", "1", "-q:v", "2", str(out_path)],
            capture_output=True, check=True,
        )
        paths.append(str(out_path))
    return paths


def main():
    OUT_DIR.mkdir(exist_ok=True)
    files = [f for f in list_files_in_folder(FOLDER_ID) if f["name"].lower().endswith((".mp4", ".mov", ".m4v"))]
    print(f"Found {len(files)} video files in folder {FOLDER_ID}")

    summary = {}
    for f in files:
        name = f["name"]
        local_path = OUT_DIR / name
        print(f"--- {name} ---")
        download_file(f["id"], local_path)

        probe = ffprobe_json(local_path)
        v_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), {})
        a_streams = [s for s in probe["streams"] if s["codec_type"] == "audio"]
        duration = float(probe["format"]["duration"])

        try:
            cuts = core.extract_template_cut_timestamps(local_path)
            boundaries = sorted(set(t for t in cuts if 0 < t < duration))
        except core.PipelineError:
            # No hard cuts detected -- a continuous shot (e.g. a single dolly/pan)
            # is a real, valid format, not a failure. Record it as such.
            boundaries = []
        segment_lengths = []
        prev = 0.0
        for b in boundaries + [duration]:
            segment_lengths.append(round(b - prev, 2))
            prev = b

        frame_paths = extract_frames(local_path, name.rsplit(".", 1)[0], duration, FRAMES_PER_VIDEO)

        summary[name] = {
            "duration_s": round(duration, 2),
            "resolution": f"{v_stream.get('width')}x{v_stream.get('height')}",
            "fps": v_stream.get("r_frame_rate"),
            "has_audio": len(a_streams) > 0,
            "audio_codec": a_streams[0]["codec_name"] if a_streams else None,
            "num_cuts_detected": len(boundaries),
            "cut_timestamps_s": [round(b, 2) for b in boundaries],
            "segment_lengths_s": segment_lengths,
            "extracted_frames": [Path(p).name for p in frame_paths],
        }
        print(json.dumps(summary[name], indent=2))

        # Don't keep the raw downloaded video in the artifact -- frames + metadata
        # are what's needed for format analysis, and keeping full videos would
        # make the artifact unnecessarily large.
        local_path.unlink()

    with open(OUT_DIR / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("\nWrote analysis_output/summary.json")


if __name__ == "__main__":
    main()
