"""
Decor Drop Reel -- furniture/decor flow-in via omni, explicit start (bare
room) + end (furnished room) frames.

v2: the end-frame-only approach (image_to_video()) worked but Gemini QA
confirmed a real issue -- the clip opens on a ~1.2s STATIC shot of the
already-furnished room before resetting to empty and doing the actual
build (see llms.txt). Giving omni an explicit bare-room start frame
(generate_room.generate_furnished_and_bare()) instead of leaving the
starting state to the model's own judgment is the fix being tried here.
Reuses villa_reveal_montage_reel/generate_omni_build.py's
two_frame_to_video() as-is. Prompt kept deliberately simple per Dev's
explicit instruction either way -- same "furniture just falls into place"
framing as before, not a structured shot breakdown.

Usage: python decor_drop_reel/generate_omni_reveal.py <bare.png> <furnished.png> <out.mp4>
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "villa_reveal_montage_reel"))
from generate_omni_build import image_to_video, two_frame_to_video  # noqa: E402

PROMPT = (
    "Use the FIRST uploaded reference image as the starting state and the "
    "SECOND uploaded reference image as the final state. Keep the camera and "
    "the room itself (walls, floor, windows, built-in lighting) completely "
    "static and unchanged. Over the clip, all the furniture and decor from "
    "the second image simply falls into place naturally and settles, ending "
    "exactly on the second reference image."
)

# Kept for backward compatibility / the old end-frame-only path.
LEGACY_PROMPT = (
    "Use the uploaded reference image as the final state only, not the starting "
    "state. At 00:00 the room is completely empty -- no furniture, no decor, no "
    "rugs. Keep the camera and the room itself (walls, floor, windows, built-in "
    "lighting) completely static and unchanged. Over the clip, all the furniture "
    "and decor from the reference image simply falls into place naturally and "
    "settles, ending exactly on the reference image."
)


def generate_reveal(bare_path, furnished_path, out_path):
    return two_frame_to_video(bare_path, furnished_path, out_path, prompt=PROMPT)


def generate_reveal_legacy(furnished_path, out_path):
    return image_to_video(furnished_path, out_path, prompt=LEGACY_PROMPT)


def main():
    generate_reveal(sys.argv[1], sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    main()
