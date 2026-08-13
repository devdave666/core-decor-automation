"""
Grades a room shot to the reference reel's measured mood, in code, deterministically.

WHY THIS EXISTS — AND WHY IT DOES NOT CONTRADICT THE PROMPT-VERSION HISTORY.

The room lighting prompt has now been through five versions. v1 (hard daylight)
and v2 (blanket underexposure) were rejected on look. v3/v4/v5 tried to pull the
overall level down by describing dawn, then dusk, then outright night with dark
windows and lamps as the only source, with the instruction moved to the front of
the prompt where FLUX weights it most heavily. Measured on d07, one sample each:

    v3 dawn   mean L 112.8   crushed  2.4%
    v4 dusk   mean L 108.0   crushed  6.9%
    v5 night  mean L 132.6   crushed  3.3%

against a reference-reel target of mean L 63-71 and crushed 15-26%. That is not a
trend, it is noise — and v5, the most extreme wording in the earliest position,
came back the BRIGHTEST of the three. The model is not disobeying a weak
instruction; it is returning the bright editorial interior its training
distribution is saturated with, and a concept whose own palette is cream boucle,
white ceiling and pale marble pins the histogram bright no matter what the text
says.

So: OVERALL EXPOSURE LEVEL IS NOT RELIABLY PROMPTABLE, and this module stops
paying per-image to re-roll for it.

This is the project's own established principle, not a new one. `band_swatch.py`
stacks the three bands in code because exact thirds are "precisely the geometry
image models render inconsistently", and labels are composited in code because
the model spells unreliably. Both follow the same rule: IF CODE CAN GUARANTEE IT,
DON'T ASK THE MODEL FOR IT. Overall luminance is the same class of problem.

THE SPLIT OF RESPONSIBILITY, which matters if editing either side:
  - The PROMPT still owns light QUALITY and DIRECTION — lamps lit, warm colour,
    and above all no hard sun shafts or blown highlights. Those are genuinely not
    fixable afterwards; a baked-in diagonal sun shaft stays a sun shaft at any
    exposure, which is exactly why v1 was a prompt failure and had to be fixed as
    one. llms.txt's line that the lighting failures were "all in the PROMPT, never
    in post-processing" is about that case and remains true for it.
  - This module owns LEVEL — mean luminance and shadow depth. That is a global
    monotonic transform, which is the one thing post-processing does perfectly and
    a generative model does not.

It also fixes a documented open finding for free: room exposure previously varied
with each concept's own palette reflectance (d01 84.5 against d02 111.6 under an
identical prompt), so the series had no consistent mood. Grading to a target
normalises across palettes by construction.

METHOD. A pure gamma curve on RGB, with the exponent solved by bisection to land
mean luminance on target. Gamma is chosen deliberately over a levels/black-point
adjustment because it COMPRESSES the shadows rather than clipping them: no pixel
is forced to 0, so shadow detail and texture survive, which is the exact failure
that got v2 rejected (34.1% crushed, sofa and floor lost). Deepening shadows and
destroying them are different operations and only one of them is wanted.
"""

import sys
from pathlib import Path

from PIL import Image

# Reference reel moody rooms measure mean L 63-71 with crushed 15-26%. Approved
# d01 sits just above at 84.5 / 16.8 and was Dev's benchmark for a long time, so
# the default target is the midpoint of "reference floor to approved d01" rather
# than the reference alone — going straight to 67 is a bigger jump than has ever
# been shown to him, and this is adjustable per run.
TARGET_MEAN = 78.0
BLOWN_LEVEL = 250
CRUSH_LEVEL = 20


def measure(path_or_img):
    img = path_or_img
    if not isinstance(img, Image.Image):
        img = Image.open(img)
    g = img.convert("L")
    px = g.tobytes()
    n = len(px)
    mean = sum(px) / n
    blown = 100.0 * sum(1 for v in px if v >= BLOWN_LEVEL) / n
    crushed = 100.0 * sum(1 for v in px if v <= CRUSH_LEVEL) / n
    return mean, blown, crushed


def _apply_gamma(img, gamma):
    lut = [min(255, max(0, round(255.0 * ((i / 255.0) ** gamma)))) for i in range(256)]
    return img.point(lut * len(img.getbands()))


def solve_gamma(img, target_mean=TARGET_MEAN, tol=0.4, max_iter=24):
    """
    Bisect gamma so the graded image's mean luminance hits target_mean.

    gamma > 1 darkens. The mean is monotonic decreasing in gamma, so plain
    bisection is enough — no need for anything cleverer, and a closed form would
    have to assume a histogram shape that varies per concept.
    """
    lo, hi = 1.0, 6.0
    if measure(img)[0] <= target_mean:
        return 1.0  # already at or below target; never brighten
    best = hi
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        m = measure(_apply_gamma(img, mid))[0]
        best = mid
        if abs(m - target_mean) <= tol:
            break
        if m > target_mean:
            lo = mid
        else:
            hi = mid
    return best


def grade(path, out_path=None, target_mean=TARGET_MEAN):
    img = Image.open(path).convert("RGB")
    before = measure(img)
    gamma = solve_gamma(img, target_mean)
    graded = _apply_gamma(img, gamma)
    after = measure(graded)
    out_path = Path(out_path or path)
    graded.save(out_path)
    return gamma, before, after, out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: python concept_tools/grade_room.py <image> [out] [target_mean]"
        )
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else None
    tgt = float(sys.argv[3]) if len(sys.argv) > 3 else TARGET_MEAN
    g, b, a, out = grade(src, dst, tgt)
    print(f"gamma {g:.3f}  ->  {out}")
    print(f"  before  meanL {b[0]:6.1f}  blown {b[1]:5.2f}%  crushed {b[2]:5.1f}%")
    print(f"  after   meanL {a[0]:6.1f}  blown {a[1]:5.2f}%  crushed {a[2]:5.1f}%")
    print("  target  meanL   70-85  blown <0.16%  crushed 15-25%")
