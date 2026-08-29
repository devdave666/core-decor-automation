"""
Editorial punch-up for the omni-graded zen-garden reel (run LOCALLY -- pure
ffmpeg + PIL, no cloud). Takes the two omni-graded halves and produces the
finished vertical reel:

  1. stitch  head (omni pass 1, source 0-10s) + tail (omni pass 2, source 9s->)
             with a short crossfade
  2. cold-open  ~0.7s of the finished lit reveal, hard cut to the build
  3. text hook  bold Playfair overlay, top third, holds then fades
  4. push-in    slow zoom on the final frame as the last beat
  5. finish     upscale to 1080x1920, loudnorm audio, web-compatible encode

Usage:
  python omni_reel_edit/finish.py --head HEAD.mp4 --tail TAIL.mp4 \
      --hook "the space under your stairs|is worth $15,000" --out FINAL.mp4
(the hook '|' splits lines; omit to use the default)
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core_decor_reel_pipeline import render_pushin_clip  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

W, H, FPS = 1080, 1920, 30
FONT = str(Path(__file__).resolve().parent.parent / "hot_takes" / "fonts" / "PlayfairDisplay-Bold.ttf")
XFADE = 1.0   # a longer dissolve eases the day->night seam
COLD_OPEN = 0.7
HOOK_IN, HOOK_HOLD, HOOK_FADE = 0.7, 4.0, 0.6
PUSHIN_S = 2.6
DEFAULT_HOOK = "the space under your stairs|is worth $15,000"


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


def norm(src, dst):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         "-c:a", "aac", "-ar", "48000", str(dst)], f"normalize {Path(src).name}")


def stitch(head, tail, dst, mode="cut", overlap=1.0):
    """
    mode="cut": hard concat, with `overlap` seconds trimmed off the front of the
    tail so its content lines up with where the head ends (the two omni segments
    are cut from overlapping source ranges).
    mode="xfade": crossfade dissolve over XFADE seconds.
    """
    if mode == "xfade":
        hd = probe_dur(head)
        off = max(hd - XFADE, 0.1)
        run(["ffmpeg", "-y", "-v", "error", "-i", str(head), "-i", str(tail),
             "-filter_complex",
             f"[0:v][1:v]xfade=transition=fade:duration={XFADE}:offset={off}[v];"
             f"[0:a][1:a]acrossfade=d={XFADE}[a]",
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-crf", "18", "-c:a", "aac", str(dst)], "stitch head+tail (xfade)")
        return
    tail_cut = dst.with_name("tail_cut.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{overlap}", "-i", str(tail),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         "-c:a", "aac", "-ar", "48000", str(tail_cut)], f"trim {overlap}s off tail front")
    lst = dst.with_name("stitch_list.txt")
    lst.write_text(f"file '{Path(head).name}'\nfile '{tail_cut.name}'\n")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac",
         str(dst)], "stitch head+tail (hard cut)")


def make_hook_png(text, dst):
    lines = text.split("|")
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # soft top gradient (not a box)
    grad = Image.new("L", (1, H), 0)
    gpx = int(H * 0.5)
    for y in range(gpx):
        grad.putpixel((0, y), int(175 * (1 - y / gpx)))
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    ov.putalpha(grad.resize((W, H)))
    img.alpha_composite(ov)
    # shrink font until the widest line fits inside a safe margin
    margin = 70
    size = 72
    while size > 40:
        font = ImageFont.truetype(FONT, size)
        try:
            font.set_variation_by_name("Bold")
        except Exception:
            pass
        if max(d.textlength(ln, font=font) for ln in lines) <= W - 2 * margin:
            break
        size -= 3
    lh = int(size * 1.22)
    top = int(H * 0.15)
    for i, ln in enumerate(lines):
        w = d.textlength(ln, font=font)
        d.text(((W - w) / 2, top + i * lh), ln, font=font, fill="white",
               stroke_width=4, stroke_fill=(0, 0, 0, 230))
    img.save(dst)


def add_hook(src, hook_png, dst):
    end = HOOK_IN + HOOK_HOLD
    # -loop 1 so the still PNG is a continuous stream the fades/enable can act on
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-loop", "1", "-i", str(hook_png),
         "-filter_complex",
         f"[1:v]format=rgba,fade=t=in:st={HOOK_IN}:d=0.4:alpha=1,"
         f"fade=t=out:st={end}:d={HOOK_FADE}:alpha=1[hk];"
         f"[0:v][hk]overlay=0:0:shortest=1[v]",
         "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "18", "-c:a", "copy", str(dst)], "overlay hook text")


def cold_open(body, dst):
    """Prepend a short clip of the finished reveal (body's own last COLD_OPEN s)."""
    bd = probe_dur(body)
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{bd - COLD_OPEN - 0.4:.2f}", "-i", str(body),
         "-t", f"{COLD_OPEN}", "-an",
         "-vf", f"fps={FPS},scale={W}:{H}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "18", str(dst.with_name("co_clip.mp4"))], "grab reveal for cold-open")
    # give the cold-open a silent track then concat
    run(["ffmpeg", "-y", "-v", "error", "-i", str(dst.with_name("co_clip.mp4")),
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
         "-c:v", "copy", "-c:a", "aac", str(dst.with_name("co_a.mp4"))], "mux silent audio")
    lst = dst.with_name("co_list.txt")
    lst.write_text(f"file '{dst.with_name('co_a.mp4').name}'\nfile '{Path(body).name}'\n")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac",
         str(dst)], "concat cold-open + body")


def add_pushin(body, dst):
    bd = probe_dur(body)
    last = dst.with_name("last.png")
    run(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.1", "-i", str(body),
         "-frames:v", "1", str(last)], "grab last frame")
    silent = dst.with_name("push_silent.mp4")
    render_pushin_clip(last, PUSHIN_S, silent, width=W, height=H, fps=FPS)
    push = dst.with_name("push.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(silent),
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
         "-c:v", "copy", "-c:a", "aac", str(push)], "mux silent audio on push-in")
    lst = dst.with_name("push_list.txt")
    lst.write_text(f"file '{Path(body).name}'\nfile '{push.name}'\n")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac",
         str(dst)], "append push-in")


def finalize(src, dst):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-vf", f"scale={W}:{H}:flags=lanczos,fps={FPS}",
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
         "-crf", "19", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
         str(dst)], "finalize (upscale + loudnorm + web encode)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--head", required=True)
    ap.add_argument("--tail", required=True)
    ap.add_argument("--hook", default=DEFAULT_HOOK)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--no-coldopen", action="store_true")
    ap.add_argument("--no-hook", action="store_true")
    ap.add_argument("--no-pushin", action="store_true")
    ap.add_argument("--stitch", choices=("cut", "xfade"), default="cut")
    args = ap.parse_args()

    wd = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="finish_"))
    wd.mkdir(parents=True, exist_ok=True)
    print(f"workdir: {wd}")

    hn, tn = wd / "head_n.mp4", wd / "tail_n.mp4"
    norm(args.head, hn)
    norm(args.tail, tn)

    cur = wd / "stitched.mp4"
    stitch(hn, tn, cur, mode=args.stitch)

    if not args.no_coldopen:
        nxt = wd / "withco.mp4"
        cold_open(cur, nxt)
        cur = nxt

    if not args.no_hook:
        hook_png = wd / "hook.png"
        make_hook_png(args.hook, hook_png)
        nxt = wd / "withhook.mp4"
        add_hook(cur, hook_png, nxt)
        cur = nxt

    if not args.no_pushin:
        nxt = wd / "withpush.mp4"
        add_pushin(cur, nxt)
        cur = nxt

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    finalize(cur, args.out)
    print(f"done -> {args.out} ({probe_dur(args.out):.1f}s)")


if __name__ == "__main__":
    main()
