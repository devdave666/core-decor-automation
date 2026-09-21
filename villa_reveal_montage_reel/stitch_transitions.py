"""
Post-process stitch for villa_reveal_montage_reel: replaces the hard-cut
concat in generate_montage.py with short xfade(transition=hblur) whip-blur
transitions at each cut, per gemini-3.8-flash's full-video critique of the
first montage attempt ("needs speed-ramping, directional motion blur, or
whip-pan transitions to bridge the edits and mask the hard seam"). Operates
on already-generated clips -- no new Veo calls, no extra generation cost.

Usage: python villa_reveal_montage_reel/stitch_transitions.py <clip1> <clip2> <clip3> <out.mp4>
"""
import subprocess
import sys
from pathlib import Path

W, H, FPS = 1080, 1920, 24
TD = 0.25  # whip-blur transition duration -- short/snappy, not a slow dissolve


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


def normalize(src, dst):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-vf", f"scale={W}:{H}:flags=lanczos,setsar=1,fps={FPS}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         "-c:a", "aac", "-ar", "48000", str(dst)], f"normalize {Path(src).name}")


def xfade_pair(a, b, dst):
    """hblur transition + audio crossfade, `a` and `b` already normalized."""
    da = probe_dur(a)
    offset = max(da - TD, 0.05)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(a), "-i", str(b),
         "-filter_complex",
         f"[0:v][1:v]xfade=transition=hblur:duration={TD}:offset={offset:.3f}[v];"
         f"[0:a][1:a]acrossfade=d={TD}[a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "18", "-c:a", "aac", "-ar", "48000", str(dst)],
        f"xfade(hblur) {Path(a).name} -> {Path(b).name}")


def main():
    if len(sys.argv) != 5:
        print("Usage: stitch_transitions.py <clip1> <clip2> <clip3> <out.mp4>")
        raise SystemExit(1)
    c1, c2, c3, out = (Path(p) for p in sys.argv[1:])
    wd = out.parent
    wd.mkdir(parents=True, exist_ok=True)

    n1, n2, n3 = wd / "n1.mp4", wd / "n2.mp4", wd / "n3.mp4"
    normalize(c1, n1)
    normalize(c2, n2)
    normalize(c3, n3)

    stitched1 = wd / "stitched1.mp4"
    xfade_pair(n1, n2, stitched1)

    xfade_pair(stitched1, n3, out)
    print(f"done -> {out} ({probe_dur(out):.2f}s)")


if __name__ == "__main__":
    main()
