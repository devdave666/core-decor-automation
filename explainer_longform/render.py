"""
Render stage: composites every frame in Python (camera moves on 4K stills, before/after
wipes, word-highlight captions, badges) and pipes raw frames into ffmpeg, muxed with a
synthesized audio bed: voice + ducked music + cut sounds.

Sharpness rule: a crop is never narrower than the output width in source pixels, so
a zoomed shot is at worst 1:1 -- never upscaled. Camera zoom is capped at src_w / W.
"""
import bisect
import math
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
SR = 44100
MAX_SHOT_S = 3.2
PAD_S, HOOK_PAD_S, END_PAD_S = 0.28, 0.45, 1.2
CUT_PUNCH = 0.05            # zoom kick on every cut
TITLE_S = 1.9

SANS = [r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
SERIF = Path(__file__).resolve().parent.parent / "hot_takes" / "fonts" / "PlayfairDisplay-Bold.ttf"
YELLOW, WHITE = (255, 214, 10), (255, 255, 255)


def _font(candidates, size, variation=None):
    for c in candidates:
        if Path(c).exists():
            f = ImageFont.truetype(str(c), size)
            if variation:
                try:
                    f.set_variation_by_name(variation)
                except Exception:  # noqa: BLE001
                    pass
            return f
    return ImageFont.load_default()


def _ease_out(u):
    return 1 - (1 - u) ** 3


def _ease_io(u):
    return u * u * (3 - 2 * u)


# ---------------------------------------------------------------- timeline

def _expand(template, L):
    n = max(len(template), math.ceil(L / MAX_SHOT_S))
    counts = [1] * len(template)
    rep = [i for i, s in enumerate(template) if "reveal" not in s]
    extra, k = n - len(template), 0
    while extra > 0 and rep:
        counts[rep[k % len(rep)]] += 1
        k += 1
        extra -= 1
    out = []
    for s, c in zip(template, counts):
        for v in range(c):
            out.append({**s, "variant": v})
    return out


def build_timeline(spec, voice):
    t, shots, words, beats = 0.0, [], [], []
    last = len(spec["beats"]) - 1
    for bi, b in enumerate(spec["beats"]):
        v = voice[b["id"]]
        pad = END_PAD_S if bi == last else (HOOK_PAD_S if bi == 0 else PAD_S)
        L = v["duration"] + pad
        beats.append({"id": b["id"], "start": t, "end": t + L, "wav": v["wav"],
                      "badge": b.get("badge"), "title": b.get("title"),
                      "upgrade": b.get("upgrade")})
        for w in v["words"]:
            words.append((t + w["s"], t + w["e"], w["w"]))
        sh = _expand(b["shots"], L)
        weights = [1.7 if "reveal" in s else 1.0 for s in sh]
        acc = t
        for s, w in zip(sh, weights):
            d = L * w / sum(weights)
            shots.append({**s, "start": acc, "end": acc + d, "beat": bi})
            acc += d
        t += L
    return shots, words, beats, t


# ------------------------------------------------------------------ camera

class Images:
    def __init__(self, paths, limit=8):
        self.paths, self.cache, self.limit = paths, {}, limit

    def get(self, key):
        if key not in self.cache:
            if len(self.cache) >= self.limit:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = np.array(Image.open(self.paths[key]).convert("RGB"))
        return self.cache[key]


def _camera(shot, u, src_w, locate):
    zmax = max(1.0, src_w / W)
    move, v = shot.get("move", "push"), shot.get("variant", 0)
    cx = cy = 0.5
    if move == "detail":
        fx, fy, size = locate.get(f"{shot['image']}|{shot['focus']}", [0.5, 0.5, 0.4])
        z1 = min(zmax, max(1.5, 0.55 / max(size, 0.05)))
        z0 = z1 * 0.82
        if v % 2:
            z0, z1 = z1, z1 * 0.9
        z = z0 + (z1 - z0) * _ease_out(u)
        cx, cy = fx, fy
    elif move in ("push", "pull") or "reveal" in shot:
        a, b = (1.0, 1.15) if move == "push" or "reveal" in shot else (1.17, 1.0)
        if v % 2:
            a, b = b, a
        z = a + (b - a) * _ease_io(u)
    else:  # pan
        direction = 1 if move == "pan_r" else -1
        if v % 2:
            direction = -direction
        z = min(1.22, zmax)
        cx = 0.5 + direction * (-0.5 + u) * (0.5 - 0.5 / z) * 1.9
    z = min(zmax, z)
    return cx, cy, z


def _crop(arr, cx, cy, z):
    sh, sw = arr.shape[:2]
    cw = sw / z
    ch = cw * H / W
    x0 = int(round(min(max(cx * sw - cw / 2, 0), sw - cw)))
    y0 = int(round(min(max(cy * sh - ch / 2, 0), sh - ch)))
    x1, y1 = min(sw, x0 + int(round(cw))), min(sh, y0 + int(round(ch)))
    return cv2.resize(arr[y0:y1, x0:x1], (W, H), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------- overlays

class Overlays:
    def __init__(self, words):
        self.cap_font = _font(SANS, 96)
        self.title_font = _font([SERIF], 150, "Bold")
        self.small = _font(SANS, 44)
        self.tag_font = _font(SANS, 56)
        self.cache = {}
        self.chunks = self._chunk(words)
        self.starts = [c["start"] for c in self.chunks]

    @staticmethod
    def _chunk(words):
        chunks, cur = [], []
        for w in words:
            cur.append(w)
            ends = w[2][-1] in ".,?!"
            if len(cur) >= 3 or ends or sum(len(x[2]) for x in cur) > 20:
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
        out = []
        for i, c in enumerate(chunks):
            nxt = chunks[i + 1][0][0] if i + 1 < len(chunks) else c[-1][1] + 0.4
            out.append({"words": c, "start": c[0][0], "end": min(nxt, c[-1][1] + 0.5)})
        return out

    def caption(self, t):
        i = bisect.bisect_right(self.starts, t) - 1
        if i < 0 or t > self.chunks[i]["end"]:
            return None
        ws = self.chunks[i]["words"]
        active = max(j for j, w in enumerate(ws) if w[0] <= t)
        key = ("cap", i, active)
        if key not in self.cache:
            self.cache[key] = self._draw_caption(ws, active)
        return self.cache[key]

    def _draw_caption(self, ws, active):
        texts = [w[2].upper() for w in ws]
        space = self.cap_font.getlength(" ")
        widths = [self.cap_font.getlength(x) for x in texts]
        total = int(sum(widths) + space * (len(ws) - 1)) + 80
        img = Image.new("RGBA", (total, 170), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = 40
        for j, (txt, wd) in enumerate(zip(texts, widths)):
            d.text((x, 30), txt, font=self.cap_font, fill=YELLOW if j == active else WHITE,
                   stroke_width=9, stroke_fill=(0, 0, 0))
            x += wd + space
        return img, ((W - total) // 2, H - 250)

    def badge(self, text):
        key = ("badge", text)
        if key not in self.cache:
            w = int(self.small.getlength(text)) + 56
            img = Image.new("RGBA", (w, 76), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((0, 0, w - 1, 75), 38, fill=(0, 0, 0, 170))
            d.text((28, 12), text, font=self.small, fill=YELLOW)
            self.cache[key] = img
        return self.cache[key]

    def title(self, text, since):
        key = ("title", text)
        if key not in self.cache:
            w = int(self.title_font.getlength(text)) + 100
            img = Image.new("RGBA", (w, 230), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.text((50, 30), text, font=self.title_font, fill=WHITE,
                   stroke_width=10, stroke_fill=(0, 0, 0))
            self.cache[key] = img
        img = self.cache[key]
        a_in = _ease_out(min(1, since / 0.28))
        a_out = min(1, max(0, (TITLE_S - since) / 0.28))
        alpha = a_in * a_out
        if alpha <= 0:
            return None
        layer = img.copy()
        layer.putalpha(layer.getchannel("A").point(lambda p: int(p * alpha)))
        x = (W - img.width) // 2 + int((1 - a_in) * -90)
        return layer, (x, int(H * 0.26))

    def tag(self, text):
        key = ("tag", text)
        if key not in self.cache:
            w = int(self.tag_font.getlength(text)) + 60
            img = Image.new("RGBA", (w, 90), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((0, 0, w - 1, 89), 20, fill=(0, 0, 0, 185))
            d.text((30, 14), text, font=self.tag_font, fill=WHITE)
            self.cache[key] = img
        return self.cache[key]


# ------------------------------------------------------------------- audio

def _whoosh(dur=0.45):
    n = int(dur * SR)
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n)
    env = np.sin(np.linspace(0, math.pi, n)) ** 2
    out, y = np.zeros(n), 0.0
    for i in range(n):
        a = 0.02 + 0.4 * math.sin(math.pi * i / n)   # cutoff sweeps up then down
        y += a * (noise[i] - y)
        out[i] = y
    out *= env
    return out / (np.abs(out).max() + 1e-9)


def _tick(dur=0.02):
    n = int(dur * SR)
    rng = np.random.default_rng(3)
    return rng.standard_normal(n) * np.exp(-np.linspace(0, 9, n))


def synth_music(dur):
    bpm = 84
    beat = 60 / bpm
    chords = [([220.00, 261.63, 329.63, 392.00], 110.00),
              ([174.61, 220.00, 261.63, 329.63], 87.31),
              ([261.63, 329.63, 392.00, 493.88], 130.81),
              ([196.00, 246.94, 293.66, 329.63], 98.00)]
    n = int(dur * SR)
    out = np.zeros(n)
    clen = beat * 8
    i = 0
    while i * clen < dur:
        notes, bass = chords[i % len(chords)]
        s = int(i * clen * SR)
        ln = int((clen + 1.2) * SR)
        t = np.arange(ln) / SR
        env = np.minimum(1, t / 1.0) * np.minimum(1, (ln / SR - t) / 1.2)
        buf = np.zeros(ln)
        for f in notes:
            buf += np.sin(2 * np.pi * f * t) + np.sin(2 * np.pi * f * 1.004 * t) \
                + 0.25 * np.sin(2 * np.pi * 2 * f * t)
        buf += 1.6 * np.sin(2 * np.pi * bass * t)
        buf *= env * (0.85 + 0.15 * np.sin(2 * np.pi * 0.2 * t))
        e = min(n, s + ln)
        out[s:e] += buf[: e - s]
        i += 1
    out /= np.abs(out).max() + 1e-9
    kick_t = np.arange(int(0.22 * SR)) / SR
    kick_f = 45 + 90 * np.exp(-kick_t * 25)
    kick = np.sin(2 * np.pi * np.cumsum(kick_f) / SR) * np.exp(-kick_t * 14)
    hat = _tick(0.03)
    k = 0
    while k * beat < dur - 0.3:
        s = int(k * beat * SR)
        if k % 2 == 0:
            out[s:s + len(kick)] += 0.55 * kick[: n - s]
        else:
            out[s:s + len(hat)] += 0.12 * hat[: n - s]
        k += 1
    return out / (np.abs(out).max() + 1e-9)


def _read_wav(path):
    with wave.open(str(path)) as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768


def build_audio(shots, beats, total, out_wav, music_path=None):
    n = int(total * SR) + SR
    voice = np.zeros(n)
    for b in beats:
        a = _read_wav(b["wav"])
        s = int((b["start"] + 0.03) * SR)
        if s >= n:
            continue
        voice[s:s + len(a)] += a[: n - s]
    if music_path and Path(music_path).exists():
        import subprocess as sp
        raw = sp.run(["ffmpeg", "-loglevel", "error", "-i", str(music_path), "-f", "s16le",
                      "-ar", str(SR), "-ac", "1", "-"], capture_output=True, check=True).stdout
        m = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768
        music = np.resize(m, n)
    else:
        music = np.resize(synth_music(total + 1), n)
    win = int(0.18 * SR)
    env = np.convolve(np.abs(voice), np.ones(win) / win, mode="same")
    duck = 1 - 0.65 * np.clip(env / 0.04, 0, 1)
    duck = np.convolve(duck, np.ones(win) / win, mode="same")
    mix = voice + 0.17 * music * duck
    sfx = np.zeros(n)
    whoosh, tick = _whoosh(), _tick()
    seen = set()
    for s in shots:
        i = int(s["start"] * SR)
        if i >= n - len(whoosh):
            continue
        sfx[i:i + len(tick)] += 0.05 * tick[: n - i]
        if "reveal" in s:
            j = int((s["start"] + 0.30 * (s["end"] - s["start"])) * SR)
            sfx[j:j + len(whoosh)] += 0.22 * whoosh[: n - j]
        up = beats[s["beat"]].get("upgrade")
        if up and up not in seen:
            seen.add(up)
            sfx[i:i + len(whoosh)] += 0.20 * whoosh[: n - i]
    mix += sfx
    mix /= max(1.0, np.abs(mix).max() / 0.95)
    st = np.repeat((mix * 32767).astype(np.int16)[:, None], 2, axis=1)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(st.tobytes())


# ------------------------------------------------------------------ render

def render(spec, voice, paths, locate, out_mp4, limit_s=None, music_path=None):
    out_mp4 = Path(out_mp4)
    shots, words, beats, total = build_timeline(spec, voice)
    print(f"timeline: {len(shots)} shots, {len(beats)} beats, {total:.1f}s "
          f"(avg cut {total / max(1, len(shots)):.2f}s)")
    if limit_s:
        total = min(total, limit_s)
    wav = out_mp4.with_suffix(".mix.wav")
    build_audio(shots, beats, total, wav, music_path)

    imgs, ov = Images(paths), Overlays(words)
    nframes = int(total * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(wav),
           "-map", "0:v", "-map", "1:a", "-t", f"{total:.3f}",
           "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-c:v", "libx264", "-preset", "medium", "-crf", "16",
           "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
           "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(out_mp4)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    p = 0
    for fi in range(nframes):
        t = fi / FPS
        while p < len(shots) - 1 and t >= shots[p]["end"]:
            p += 1
        s = shots[p]
        u = min(1, max(0, (t - s["start"]) / (s["end"] - s["start"])))
        since = t - s["start"]
        punch = 1 + CUT_PUNCH * math.exp(-since / 0.09)

        if "reveal" in s:
            a, b = (imgs.get(k) for k in s["reveal"])
            cx, cy, z = _camera(s, u, a.shape[1], locate)
            z = min(z * punch, a.shape[1] / W)
            arr = _crop(a, cx, cy, z)
            wp = min(1, max(0, (u - 0.30) / 0.32))
            x = int(W * _ease_io(wp))
            if x > 0:
                arr[:, :x] = _crop(b, cx, cy, z)[:, :x]
            if 0 < x < W:
                arr[:, max(0, x - 3):x + 3] = 255
            frame = Image.fromarray(arr)
            label = "BEFORE" if u < 0.30 else ("AFTER" if u > 0.62 else None)
            if label:
                tg = ov.tag(label)
                frame.paste(tg, (W - tg.width - 60, 60), tg)
        else:
            img = imgs.get(s["image"])
            cx, cy, z = _camera(s, u, img.shape[1], locate)
            frame = Image.fromarray(_crop(img, cx, cy, min(z * punch, img.shape[1] / W)))

        bt = beats[s["beat"]]
        if bt["badge"]:
            bg = ov.badge(bt["badge"])
            frame.paste(bg, (60, 60), bg)
        if bt["title"] and t - bt["start"] < TITLE_S:
            r = ov.title(bt["title"], t - bt["start"])
            if r:
                frame.paste(r[0], r[1], r[0])
        cap = ov.caption(t)
        if cap:
            frame.paste(cap[0], cap[1], cap[0])

        if t > total - 0.8:
            f = max(0.0, (total - t) / 0.8)
            frame = Image.fromarray((np.asarray(frame) * f).astype(np.uint8))
        proc.stdin.write(frame.tobytes())
        if fi % 600 == 0:
            print(f"  frame {fi}/{nframes}")
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    wav.unlink(missing_ok=True)
    return total
