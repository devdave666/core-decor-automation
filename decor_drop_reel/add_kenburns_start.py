"""
Decor Drop Reel -- optional Ken Burns zoom-out over the clip's first ~1.4s,
to give the brief static empty-room opening a little motion as a hook.
Zoom starts at 1.10x and eases out to 1.0x (full frame) by the time the
furniture starts falling in. Rest of the clip is untouched.

Usage: python decor_drop_reel/add_kenburns_start.py <in.mp4> <out.mp4>
"""
import subprocess
import sys
from pathlib import Path

W, H, FPS = 720, 1280, 24
KB_SECONDS = 1.4
KB_FRAMES = int(KB_SECONDS * FPS)
START_ZOOM = 1.10


def run(cmd, desc):
    print(f"ffmpeg: {desc}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-3000:])
        raise SystemExit(f"failed: {desc}")


def probe_dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nk=1:nw=1", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())


def add_kenburns(src, dst):
    src, dst = Path(src), Path(dst)
    wd = dst.parent
    wd.mkdir(parents=True, exist_ok=True)

    head_v = wd / "_kb_head_v.mp4"
    zoom_expr = f"max(1.0,{START_ZOOM}-{START_ZOOM - 1.0}*on/{KB_FRAMES - 1})"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-t", f"{KB_SECONDS}",
         "-vf", f"zoompan=z='{zoom_expr}':d=1:s={W}x{H}:fps={FPS}",
         "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(head_v)],
        "zoompan on first 1.4s")

    head = wd / "_kb_head.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(head_v), "-i", str(src),
         "-t", f"{KB_SECONDS}", "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-c:a", "aac", "-ar", "48000", str(head)],
        "mux head video with original audio slice")

    tail = wd / "_kb_tail.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{KB_SECONDS}", "-i", str(src),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         "-c:a", "aac", "-ar", "48000", str(tail)],
        "re-encode tail from 1.4s")

    run(["ffmpeg", "-y", "-v", "error", "-i", str(head), "-i", str(tail),
         "-filter_complex", "[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[v][a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-profile:v", "high", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(dst)],
        "concat kenburns head + tail")

    for f in (head_v, head, tail):
        f.unlink(missing_ok=True)

    print(f"done -> {dst} ({probe_dur(dst):.2f}s)")
    return dst


def main():
    add_kenburns(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
