"""
Second parallax test: LAYERED 2.5D instead of continuous per-pixel warp.
Splits the depth map into 3 bands (background / midground / foreground),
each rendered as a RIGID center-zoom of the full photo (so straight lines
stay straight within a layer), blended with depth-driven soft weights.
Classic multiplane-camera trick. Not part of any pipeline -- throwaway.
"""
import time

import cv2
import numpy as np
from PIL import Image

SRC = "assets/application/c01_kit_modlux_app.png"
OUT_DIR = r"C:\Users\Dev\AppData\Local\Temp\reel_test"
DEPTH_CACHE = OUT_DIR + r"\depth_debug.npy"  # reuse depth map from the first test
DURATION_S = 5.0
FPS = 25
MAX_ZOOM = 1.35
PARALLAX_STRENGTH = 0.55  # same knob as test B, now applied per-LAYER not per-pixel
FEATHER = 0.10  # depth-space feather width between bands


def layer_weights(depth_norm):
    d = depth_norm
    t1, t2 = 1.0 / 3.0, 2.0 / 3.0
    fw = FEATHER

    def smoothstep(edge0, edge1, x):
        x = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
        return x * x * (3 - 2 * x)

    w_bg = 1.0 - smoothstep(t1 - fw / 2, t1 + fw / 2, d)
    w_fg = smoothstep(t2 - fw / 2, t2 + fw / 2, d)
    w_mid = np.clip(1.0 - w_bg - w_fg, 0.0, None)

    total = w_bg + w_mid + w_fg
    return w_bg / total, w_mid / total, w_fg / total


def rigid_zoom_crop(img, zoom, out_w, out_h):
    """Scale the WHOLE image by `zoom` around its own center, then crop back
    to (out_w, out_h) -- a pure rigid scale, so straight lines stay straight."""
    h, w = img.shape[:2]
    new_w, new_h = round(w * zoom), round(h * zoom)
    scaled = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    x0 = (new_w - out_w) // 2
    y0 = (new_h - out_h) // 2
    return scaled[y0:y0 + out_h, x0:x0 + out_w]


def main():
    print("Loading image + cached depth map...", flush=True)
    img = Image.open(SRC).convert("RGB")
    w, h = img.size
    rgb = np.array(img)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    depth_norm = np.load(DEPTH_CACHE)  # 0=far, 1=near, from the first test run

    print("Building layer weight maps...", flush=True)
    w_bg, w_mid, w_fg = layer_weights(depth_norm)
    # sanity dump so the layer split is inspectable, not just assumed correct
    vis = np.stack([w_bg, w_mid, w_fg], axis=-1)
    cv2.imwrite(OUT_DIR + r"\layers_debug.png", (vis * 255).astype(np.uint8))

    avg_bg = float((depth_norm * w_bg).sum() / max(w_bg.sum(), 1e-6))
    avg_mid = float((depth_norm * w_mid).sum() / max(w_mid.sum(), 1e-6))
    avg_fg = float((depth_norm * w_fg).sum() / max(w_fg.sum(), 1e-6))
    print(f"avg depth per layer: bg={avg_bg:.2f} mid={avg_mid:.2f} fg={avg_fg:.2f}", flush=True)

    n_frames = int(DURATION_S * FPS)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(fr"{OUT_DIR}\_raw_layered.mp4", fourcc, FPS, (w, h))

    print(f"Rendering {n_frames} frames...", flush=True)
    t0 = time.time()
    for i in range(n_frames):
        t = i / max(n_frames - 1, 1)
        ease = t * t * (3 - 2 * t)
        zoom_bg = 1.0 + ease * (MAX_ZOOM - 1.0) * (1.0 + PARALLAX_STRENGTH * (avg_bg - 0.5))
        zoom_mid = 1.0 + ease * (MAX_ZOOM - 1.0) * (1.0 + PARALLAX_STRENGTH * (avg_mid - 0.5))
        zoom_fg = 1.0 + ease * (MAX_ZOOM - 1.0) * (1.0 + PARALLAX_STRENGTH * (avg_fg - 0.5))
        zoom_bg, zoom_mid, zoom_fg = (max(z, 1.0) for z in (zoom_bg, zoom_mid, zoom_fg))

        layer_bg = rigid_zoom_crop(bgr, zoom_bg, w, h).astype(np.float32)
        layer_mid = rigid_zoom_crop(bgr, zoom_mid, w, h).astype(np.float32)
        layer_fg = rigid_zoom_crop(bgr, zoom_fg, w, h).astype(np.float32)

        mask_bg = rigid_zoom_crop(w_bg, zoom_bg, w, h)[..., None]
        mask_mid = rigid_zoom_crop(w_mid, zoom_mid, w, h)[..., None]
        mask_fg = rigid_zoom_crop(w_fg, zoom_fg, w, h)[..., None]
        total_mask = mask_bg + mask_mid + mask_fg
        total_mask = np.clip(total_mask, 1e-6, None)

        composite = (
            layer_bg * mask_bg + layer_mid * mask_mid + layer_fg * mask_fg
        ) / total_mask
        frame = np.clip(composite, 0, 255).astype(np.uint8)

        writer.write(frame)
        if i % 25 == 0:
            print(f"  frame {i}/{n_frames}", flush=True)

    writer.release()
    print(f"Done rendering in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
