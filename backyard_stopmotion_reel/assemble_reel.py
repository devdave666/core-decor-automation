"""
Backyard landscape stop-motion reel -- assembly (no publishing).

Takes the 16 frames from generate_frames.py and assembles a TRUE stop-motion
reel: each frame held ~1s (first and last held longer), hard cuts only (stop
motion is not a cross-fade slideshow), 30fps, with a small deterministic
per-frame position jitter so the locked-off camera still reads as hand-made.

Audio: reuses the daily pipeline's Drive "Template Reels" rotation for a music
bed only (core.fetch_next_template + extract_and_master_audio), looped/trimmed
to length. Does NOT advance the template counter -- this is a one-off.

Publishing is a separate step (publish_reel.py) so the expensive frame
generation never has to run twice -- same split as the repo's
generate-transformation-* / publish-existing-* workflows.

Usage: python backyard_stopmotion_reel/assemble_reel.py <frames_dir> <out_mp4>
Env: GITHUB_WORKSPACE (repo root) + GOOGLE_OAUTH_* (for the Drive music bed).
"""
import argparse
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core_decor_reel_pipeline as core  # noqa: E402

W, H = 1080, 1920
FPS = 30
OVERSCAN = 1.10
JITTER_FRAC = 0.015

HOLD_S = [2.2] + [1.05] * 14 + [2.6]


def _frame_clip(src_png, out_mp4, hold_s, seed):
    scaled_w, scaled_h = round(W * OVERSCAN), round(H * OVERSCAN)
    d = hashlib.sha256(seed.encode()).digest()
    fx = (d[0] / 255) * 2 - 1
    fy = (d[1] / 255) * 2 - 1
    x = min(scaled_w - W, max(0, (scaled_w - W) / 2 + fx * JITTER_FRAC * W))
    y = min(scaled_h - H, max(0, (scaled_h - H) / 2 + fy * JITTER_FRAC * H))
    n_frames = max(round(hold_s * FPS), 1)
    core._run_ffmpeg(
        ["-loop", "1", "-framerate", str(FPS), "-i", str(src_png),
         "-vf", (f"scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=increase,"
                 f"crop={scaled_w}:{scaled_h},crop={W}:{H}:{x:.0f}:{y:.0f}"),
         "-frames:v", str(n_frames), "-r", str(FPS),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out_mp4)],
        f"stop-motion frame clip {Path(src_png).name} ({hold_s:.2f}s)",
    )
    return out_mp4


def build_silent_video(frames_dir, work_dir):
    frames = sorted(frames_dir.glob("frame_*.png"))
    if len(frames) != 16:
        raise core.PipelineError(f"expected 16 frames, found {len(frames)} in {frames_dir}")
    clips = []
    for i, f in enumerate(frames):
        clips.append(_frame_clip(f, work_dir / f"clip_{i:02d}.mp4", HOLD_S[i], f"bstm-{i}"))
    concat_list = work_dir / "concat.txt"
    concat_list.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips))
    silent = work_dir / "silent.mp4"
    core._run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
         "-level", "4.0", "-r", str(FPS), "-movflags", "+faststart", str(silent)],
        "concatenate stop-motion frame clips",
    )
    return silent


def mux_audio(silent_video, wav_path, out_path):
    core._run_ffmpeg(
        ["-i", str(silent_video), "-stream_loop", "-1", "-i", str(wav_path),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
         "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out_path)],
        "mux looped music bed onto stop-motion video",
    )
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir", type=Path)
    ap.add_argument("out_mp4", type=Path)
    args = ap.parse_args()
    args.out_mp4.parent.mkdir(parents=True, exist_ok=True)

    repo_root = os.environ.get("GITHUB_WORKSPACE") or os.environ.get("REPO_ROOT", ".")
    work = args.out_mp4.parent
    template_path, t_idx, n_templates = core.fetch_next_template(repo_root, work)
    print(f"music bed: template {t_idx + 1}/{n_templates} (counter NOT advanced)")
    wav = core.extract_and_master_audio(template_path, work / "music.wav")

    silent = build_silent_video(args.frames_dir, work)
    mux_audio(silent, wav, args.out_mp4)

    duration = core.get_audio_duration_seconds(args.out_mp4)
    core.validate_reel_for_meta(args.out_mp4, duration)
    print(f"assembled {args.out_mp4} ({duration:.1f}s) -- publishable as a Reel")


if __name__ == "__main__":
    main()
