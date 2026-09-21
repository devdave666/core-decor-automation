"""
v2 of the transition fix for villa_reveal_montage_reel. The first attempt
(xfade transition=hblur, a crossfade) made things WORSE per gemini-3.8-flash's
critique: blending two frames of mismatched camera geometry made the mismatch
MORE visible, not less. Gemini's own suggested fix was specific: a hard cut
disguised by motion blur, not a blend.

This does that literally: each clip's outgoing tail ramps a directional
Gaussian blur 0 -> peak (getting less readable as it approaches the cut),
the next clip's incoming head ramps peak -> 0 (resolving out of the blur).
The actual cut between them happens while both sides are near-unreadable, so
mismatched framing/geometry never appears sharp in the same frame -- unlike
a crossfade, nothing is ever blended together. No new Veo generations.

Usage: python villa_reveal_montage_reel/stitch_blurcut.py <clip1> <clip2> <clip3> <out.mp4>
"""
import subprocess
import sys
from pathlib import Path

W, H, FPS = 1080, 1920, 24
TD = 0.15       # blur ramp duration each side of a cut
PEAK_SIGMA = 45  # blur strength at the cut point -- high enough to be unreadable


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


def main_segment(src, ss, dur, dst):
    """Untouched middle of a clip (no blur)."""
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if ss is not None:
        cmd += ["-ss", f"{ss:.3f}"]
    cmd += ["-i", str(src)]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
            "-c:a", "aac", "-ar", "48000", str(dst)]
    run(cmd, f"main segment {Path(src).name} ss={ss} dur={dur}")


BLUR_STEPS = 4  # gblur's sigma expr doesn't expose t/n here -- stepped fixed-sigma
                 # sub-segments instead of a continuous per-frame ramp


def blur_ramp_segment(src, ss, dur, ramp_in, dst):
    """
    ramp_in=True  -> sigma steps 0 -> PEAK_SIGMA (approaching a cut, getting blurrier)
    ramp_in=False -> sigma steps PEAK_SIGMA -> 0 (leaving a cut, resolving into focus)
    Built as BLUR_STEPS short fixed-sigma sub-clips, concatenated.
    """
    step_dur = dur / BLUR_STEPS
    steps = []
    for i in range(BLUR_STEPS):
        level = (i + 1) if ramp_in else (BLUR_STEPS - i)
        sigma = PEAK_SIGMA * level / BLUR_STEPS
        step_dst = dst.with_name(f"{dst.stem}_s{i}.mp4")
        run(["ffmpeg", "-y", "-v", "error",
             "-ss", f"{ss + i * step_dur:.3f}", "-i", str(src), "-t", f"{step_dur:.3f}",
             "-vf", f"gblur=sigma={sigma:.2f}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
             "-c:a", "aac", "-ar", "48000", str(step_dst)],
            f"blur-step {i} sigma={sigma:.1f} {Path(src).name}")
        steps.append(step_dst)
    concat_segments(steps, dst)


def concat_segments(paths, dst):
    lst = dst.with_name("_concat_list.txt")
    lst.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in paths))
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         "-c:a", "aac", "-ar", "48000", str(dst)], "concat all segments")


def build_blurcut(clip_a, clip_b, work_dir, prefix):
    """Split a's tail and b's head into blur-ramp segments; return
    (a_main_end_time_unused, [a_tail_blur, b_head_blur], b_head_end)."""
    da = probe_dur(clip_a)
    a_tail = work_dir / f"{prefix}_a_tail.mp4"
    blur_ramp_segment(clip_a, max(da - TD, 0), TD, ramp_in=True, dst=a_tail)
    b_head = work_dir / f"{prefix}_b_head.mp4"
    blur_ramp_segment(clip_b, 0, TD, ramp_in=False, dst=b_head)
    return a_tail, b_head


def main():
    if len(sys.argv) != 5:
        print("Usage: stitch_blurcut.py <clip1> <clip2> <clip3> <out.mp4>")
        raise SystemExit(1)
    c1, c2, c3, out = (Path(p) for p in sys.argv[1:])
    wd = out.parent
    wd.mkdir(parents=True, exist_ok=True)

    n1, n2, n3 = wd / "bc_n1.mp4", wd / "bc_n2.mp4", wd / "bc_n3.mp4"
    normalize(c1, n1)
    normalize(c2, n2)
    normalize(c3, n3)

    d1, d2, d3 = probe_dur(n1), probe_dur(n2), probe_dur(n3)

    seg1_main = wd / "seg1_main.mp4"
    main_segment(n1, 0, d1 - TD, seg1_main)
    seg1_tail, seg2_head = build_blurcut(n1, n2, wd, "cut1")

    seg2_mid = wd / "seg2_mid.mp4"
    main_segment(n2, TD, d2 - 2 * TD, seg2_mid)
    seg2_tail, seg3_head = build_blurcut(n2, n3, wd, "cut2")

    seg3_main = wd / "seg3_main.mp4"
    main_segment(n3, TD, None, seg3_main)

    segments = [seg1_main, seg1_tail, seg2_head, seg2_mid, seg2_tail, seg3_head, seg3_main]
    concat_segments(segments, out)
    print(f"done -> {out} ({probe_dur(out):.2f}s)")


if __name__ == "__main__":
    main()
