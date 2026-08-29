"""
Assemble the final mansion reel: concat the (style-consistent) Veo clips and
lay a music bed under them, keeping the Veo ambient (water, wind) low for
texture. Loudnorm, 1080x1920, web-compatible encode.

Usage: python mansion_reel/finish_mansion.py <clip1> <clip2> <clip3> <music.wav> <out.mp4>
"""
import subprocess
import sys
from pathlib import Path

W, H, FPS = 1080, 1920, 24


def run(cmd, desc):
    print(f"ffmpeg: {desc}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-3000:])
        raise SystemExit(desc)


def main():
    *clips, music, out = sys.argv[1:]
    clips = [Path(c) for c in clips]
    music, out = Path(music), Path(out)
    wd = out.parent
    wd.mkdir(parents=True, exist_ok=True)

    silent_concat = wd / "_v.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for c in clips:
        cmd += ["-i", str(c)]
    n = len(clips)
    fin = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
    cmd += ["-filter_complex", f"{fin}concat=n={n}:v=1:a=1[v][a]",
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-crf", "18", "-c:a", "aac", str(silent_concat)]
    run(cmd, "concat clips")

    # music bed on top, Veo ambient ducked to ~15% for texture
    run(["ffmpeg", "-y", "-v", "error", "-i", str(silent_concat),
         "-stream_loop", "-1", "-i", str(music),
         "-filter_complex",
         "[0:a]volume=0.18[amb];[1:a]volume=1.0[mus];"
         "[amb][mus]amix=inputs=2:duration=first:dropout_transition=0,"
         "loudnorm=I=-14:TP=-1.5:LRA=11[a]",
         "-map", "0:v", "-map", "[a]", "-shortest",
         "-vf", f"scale={W}:{H}:flags=lanczos,fps={FPS}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
         "-level", "4.2", "-crf", "19", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(out)], "mix music bed + finalize")
    print(f"done -> {out}")


if __name__ == "__main__":
    main()
