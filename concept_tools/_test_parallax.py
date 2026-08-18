"""
One-off local test comparing a plain Ken Burns push-in against a true
depth-based 2.5D parallax push-in, on the same static application photo.
Not part of any pipeline -- throwaway script for a side-by-side demo.
"""
import sys
import time

import cv2
import numpy as np
import torch
from PIL import Image
from transformers import pipeline

SRC = "assets/application/c01_kit_modlux_app.png"
OUT_DIR = r"C:\Users\Dev\AppData\Local\Temp\reel_test"
DURATION_S = 5.0
FPS = 25
MAX_ZOOM = 1.35          # matches test_a's ffmpeg zoompan target
PARALLAX_STRENGTH = 0.55  # how much MORE the nearest pixels zoom vs the farthest


def main():
    print("Loading image...", flush=True)
    img = Image.open(SRC).convert("RGB")
    w, h = img.size
    rgb = np.array(img)

    print("Loading depth model (Depth Anything V2 Small)...", flush=True)
    t0 = time.time()
    try:
        depth_pipe = pipeline(
            task="depth-estimation",
            model="depth-anything/Depth-Anything-V2-Small-hf",
            device=-1,
        )
    except Exception as e:
        print(f"Depth-Anything load failed ({e}), falling back to Intel/dpt-hybrid-midas", flush=True)
        depth_pipe = pipeline(task="depth-estimation", model="Intel/dpt-hybrid-midas", device=-1)
    print(f"Model loaded in {time.time() - t0:.1f}s", flush=True)

    print("Running depth estimation...", flush=True)
    t0 = time.time()
    result = depth_pipe(img)
    depth = np.array(result["depth"].resize((w, h), Image.BICUBIC), dtype=np.float32)
    print(f"Depth estimated in {time.time() - t0:.1f}s, raw range [{depth.min():.2f}, {depth.max():.2f}]", flush=True)

    # This pipeline's "depth" output is actually inverse-depth / disparity for
    # both DPT and Depth-Anything (bigger value = CLOSER to camera) -- confirmed
    # by construction below, not assumed: sample the bottom-center of frame
    # (where the near foreground table/floor sits in this project's app shots)
    # against the top strip (where the far window/wall sits).
    near_sample = depth[int(h * 0.85):, int(w * 0.35):int(w * 0.65)].mean()
    far_sample = depth[:int(h * 0.15), int(w * 0.35):int(w * 0.65)].mean()
    print(f"near-region depth-signal={near_sample:.2f} far-region depth-signal={far_sample:.2f}", flush=True)
    if near_sample < far_sample:
        print("Polarity looks inverted vs expectation -- flipping.", flush=True)
        depth = depth.max() - depth

    d_min, d_max = depth.min(), depth.max()
    depth_norm = (depth - d_min) / max(d_max - d_min, 1e-6)  # 0=far, 1=near

    np.save(fr"{OUT_DIR}\depth_debug.npy", depth_norm)
    depth_vis = (depth_norm * 255).astype(np.uint8)
    cv2.imwrite(fr"{OUT_DIR}\depth_debug.png", depth_vis)

    cx, cy = w / 2.0, h / 2.0
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    dx = xs - cx
    dy = ys - cy

    n_frames = int(DURATION_S * FPS)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(fr"{OUT_DIR}\_raw_parallax.mp4", fourcc, FPS, (w, h))

    print(f"Rendering {n_frames} frames...", flush=True)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    for i in range(n_frames):
        t = i / max(n_frames - 1, 1)
        ease = t * t * (3 - 2 * t)  # smoothstep, matches a real dolly's accel/decel
        base_zoom = 1.0 + ease * (MAX_ZOOM - 1.0)
        # per-pixel zoom: near pixels (depth_norm near 1) zoom MORE than far ones
        local_zoom = base_zoom * (1.0 + ease * PARALLAX_STRENGTH * (depth_norm - 0.5))
        local_zoom = np.clip(local_zoom, 1.0, None)

        src_x = cx + dx / local_zoom
        src_y = cy + dy / local_zoom

        frame = cv2.remap(
            bgr, src_x, src_y, interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )
        writer.write(frame)
        if i % 25 == 0:
            print(f"  frame {i}/{n_frames}", flush=True)

    writer.release()
    print("Raw frames written, muxing with ffmpeg for compatibility...", flush=True)


if __name__ == "__main__":
    main()
