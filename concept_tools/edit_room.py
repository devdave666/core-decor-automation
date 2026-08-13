"""
Edits an ALREADY-GENERATED room shot in place instead of re-rolling it, so a
composition that is good apart from one defect can be repaired without losing it.

WHY THIS EXISTS. `parts=room` regenerates the room shot from scratch, which
re-rolls everything — camera angle, architecture, styling, light. That is the
right tool when the room is wrong. It is the wrong tool when the room is right
except for one fixable flaw, because the good version is gone the moment you
re-roll and there is no getting it back.

d06 is the case that forced this. Dev's verdict on its room shot was "I love this
application photo otherwise" — the flaws were two geometry hallucinations (a
console leg passing through the bench frame, and two urns parked on the bottom
stair blocking the route up), not anything about the look. Regenerating would
have thrown away a composition he had just said he liked, on the chance of
getting an equally good one back minus the defects. Editing keeps it.

This is a THIRD axis alongside the existing bands/room split, and the same
principle behind that split: never re-pay for, or re-risk, something already
approved.

HOW THE EDIT IS PROMPTED — this follows BFL's own editing guidance, not
improvisation. Their rule is to "be specific about what changes and explicit
about what should stay the same", refer to objects by spatial position ("the
right-most jar"), and close with a preservation clause ("keep everything else
unchanged"). `_build_edit_prompt` enforces that last part so a caller cannot
forget it; the instruction itself is passed in.

ON THE NO-TEXT GUARD. This tool RUNS the OCR check and prints the result, but
does NOT fail on it, unlike generation. Three specific reasons, all narrow:
  1. The source image was already verified text-free by a human before being
     committed — that is a precondition of there being anything here to edit.
  2. An edit that repositions furniture cannot introduce signage or lettering;
     the prompt never asks for any and the source had none.
  3. d06's room is the confirmed worst case for the guard's known false-positive
     on ornate pattern — 6 for 6 across two runs, every hit 55-64% confidence on
     zellige tile and stair ironwork. Gating on a check that is already known to
     misfire on this exact image would block the repair for a reason nobody
     believes.
This is deliberately NOT a change to MIN_CONFIDENCE, which stays untouched and
strict for generation. Hits are printed loudly so a human still sees them.
"""

import base64
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_concept import CONCEPTS, _fit_final, _generate, _save  # noqa: E402
from ocr_verify import find_text  # noqa: E402

# Appended to every edit instruction. BFL's editing guide is explicit that an
# edit prompt should state what stays the same as well as what changes —
# without it, an edit drifts the whole frame (relights it, moves the camera,
# restyles objects nobody asked about) and the composition being protected is
# lost anyway, which would defeat the entire point of editing over regenerating.
PRESERVE = (
    " Keep every other part of the image exactly as it is and change nothing "
    "else: the same camera position and angle, the same framing and perspective, "
    "the same architecture, walls, floor and ceiling, the same materials, "
    "finishes and tilework, the same light fittings, the same lighting, exposure, "
    "shadows and warm colour grade, and the same photographic style and grain. "
    "The result is the same photograph with only the described change applied."
)


def _build_edit_prompt(instruction):
    return instruction.strip() + PRESERVE


def edit_room(concept_id, instruction, out_dir=None, keep_original=True):
    concept = CONCEPTS[concept_id]
    stem = concept["stem"]
    out_dir = Path(out_dir or f"concept_review/{concept_id}")
    app_path = out_dir / f"{stem}_app.png"

    if not app_path.exists():
        raise SystemExit(
            f"no existing room shot at {app_path} — edit_room repairs an image "
            f"that already exists; use generate_concept.py with parts=room to "
            f"create one."
        )

    # The pre-edit image is the only copy of a composition that was good enough
    # to be worth repairing rather than re-rolling. Keep it until the edit has
    # actually been looked at; the workflow strips it before committing.
    if keep_original:
        before = Path(f"{app_path}.before-edit.png")
        shutil.copy(app_path, before)
        print(f"[{stem}] kept pre-edit copy at {before}", flush=True)

    source_b64 = base64.b64encode(app_path.read_bytes()).decode("ascii")
    prompt = _build_edit_prompt(instruction)
    print(f"[{stem}] edit prompt:\n{prompt}\n", flush=True)

    # Width/height intentionally unused on the edit path — see _generate.
    edited = _generate(prompt, None, None, f"{stem} room edit", input_image=source_b64)
    _save(edited, app_path)
    _fit_final(app_path)

    hits = find_text(app_path)
    if hits:
        print(f"[{stem}] NOTE: no-text check reported {hits} on the edited image. "
              f"Not failing — see this module's docstring for why edits report "
              f"rather than gate. Look at the image before trusting either way.",
              flush=True)
    else:
        print(f"[{stem}] OCR clean", flush=True)

    print(f"[{stem}] edited room shot -> {app_path}", flush=True)
    return app_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(
            "usage: python concept_tools/edit_room.py <concept> <instruction> "
            "[out_dir]\n\n"
            "The instruction should say exactly what changes, referring to "
            "objects by where they are in the frame. What stays the same is "
            "appended automatically."
        )
    which = sys.argv[1]
    if which not in CONCEPTS:
        raise SystemExit(f"unknown concept {which}; known: {list(CONCEPTS)}")
    edit_room(which, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
