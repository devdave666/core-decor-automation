"""
Decor Drop Reel -- room image generation.

Generates ONE striking, fully-furnished single-room interior photo via Nano
Banana Pro. Deliberately no fixed concept list: the prompt itself asks for a
bold, aspirational room type + style choice each run, so repeated runs
naturally vary rather than needing a rotation counter.

Usage: python decor_drop_reel/generate_room.py <out_path.png>
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "architectural_assembly_reel"))
from generate_concept_frames import NanoBanana  # noqa: E402 -- reused as-is, generic image-gen wrapper

PROMPT = (
    "Ultra-photorealistic interior design photograph, vertical 9:16 composition, "
    "magazine real-estate quality. ONE single room only -- your choice of room type "
    "(living room, bedroom, kitchen, bathroom, home office, dining room) and design "
    "style -- go genuinely bold and mind-blowing: a striking color palette, statement "
    "furniture, dramatic lighting, luxurious materials. Fully furnished and decorated "
    "to an aspirational, high-end standard. Natural daylight or warm evening light, "
    "crisp detail, no people, no text, no watermark."
)


BARE_PROMPT = (
    "Show this exact same room -- identical camera angle, identical walls, "
    "windows, flooring, ceiling and built-in lighting -- but COMPLETELY "
    "REMOVE every piece of furniture, all decor, rugs, plants, art and "
    "accessories. Leave only the bare, empty room: bare walls, bare floor, "
    "empty space, nothing placed in it. No text, no people, no watermark. "
    "Everything about the room itself (architecture, materials, windows, "
    "light) stays exactly the same -- only remove what's freestanding in it."
)


def generate_room(out_path: Path):
    nb = NanoBanana()
    img = nb.gen(PROMPT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"Saved {out_path} ({img.width}x{img.height}) via {nb.model}")
    return out_path


def generate_furnished_and_bare(out_dir: Path):
    """Generates the furnished room, then edits FROM it to produce a bare
    (no furniture/decor) version of the same room -- same technique as
    architectural_assembly_reel's site/after pair. Returns
    (furnished_path, bare_path)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    nb = NanoBanana()

    furnished_img = nb.gen(PROMPT)
    furnished_path = out_dir / "furnished.png"
    furnished_img.save(furnished_path)
    print(f"Saved {furnished_path} ({furnished_img.width}x{furnished_img.height}) via {nb.model}")

    bare_img = nb.gen([BARE_PROMPT, furnished_img])
    bare_path = out_dir / "bare.png"
    bare_img.save(bare_path)
    print(f"Saved {bare_path} ({bare_img.width}x{bare_img.height})")

    return furnished_path, bare_path


def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("decor_drop_reel/output")
    generate_furnished_and_bare(out_dir)


if __name__ == "__main__":
    main()
