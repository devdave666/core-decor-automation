"""
Decor Drop Reel -- furniture/decor flow-in via omni, end-frame only.

Reuses villa_reveal_montage_reel/generate_omni_build.py's image_to_video()
as-is (the validated end-frame-only omni technique -- see llms.txt for why
this beat every multi-clip Veo attempt). Deliberately simple prompt per
Dev's explicit instruction: no structured shot breakdown, just "furniture
and decor falls into place" -- keep it simple, don't over-complicate.

Usage: python decor_drop_reel/generate_omni_reveal.py <room.png> <out.mp4>
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "villa_reveal_montage_reel"))
from generate_omni_build import image_to_video  # noqa: E402

PROMPT = (
    "Use the uploaded reference image as the final state only, not the starting "
    "state. At 00:00 the room is completely empty -- no furniture, no decor, no "
    "rugs. Keep the camera and the room itself (walls, floor, windows, built-in "
    "lighting) completely static and unchanged. Over the clip, all the furniture "
    "and decor from the reference image simply falls into place naturally and "
    "settles, ending exactly on the reference image."
)


def generate_reveal(image_path, out_path):
    return image_to_video(image_path, out_path, prompt=PROMPT)


def main():
    generate_reveal(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
