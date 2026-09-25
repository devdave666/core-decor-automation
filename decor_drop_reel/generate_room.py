"""
Decor Drop Reel -- room image generation.

Generates ONE striking, fully-furnished single-room interior photo via Nano
Banana Pro, driven by an explicit concept rotation (concepts.json +
concept_index.txt, same convention every other content type in this repo
already uses). v1 left room type AND style entirely to the model's own
"your choice, go bold" judgment -- real output (dd01-dd04) converged hard on
the same jewel-tone/brass glam look every single run despite that framing.
An explicit rotation is the fix, matching this repo's own standing lesson
(architectural_assembly_reel's llms.txt entry: leaving "creative" choices
fully open causes convergence; an explicit list is what actually produces
variety) -- not a new lesson, a re-learned one.

Usage: python decor_drop_reel/generate_room.py <out_path.png>
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "architectural_assembly_reel"))
from generate_concept_frames import NanoBanana  # noqa: E402 -- reused as-is, generic image-gen wrapper

HERE = Path(__file__).resolve().parent


def load_concepts():
    return json.loads((HERE / "concepts.json").read_text(encoding="utf-8"))


def prompt_for(concept):
    return (
        f"Ultra-photorealistic interior design photograph, vertical 9:16 "
        f"composition, magazine real-estate quality. ONE single room only: a "
        f"{concept['room'].lower()} in a {concept['style']} style -- "
        f"{concept['description']}. Fully furnished and decorated to an "
        f"aspirational, high-end standard, true to this specific style and "
        f"palette (not a generic luxury glam look). Crisp detail, no people, "
        f"no text, no watermark."
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


def generate_room(out_path: Path, concept):
    nb = NanoBanana()
    img = nb.gen(prompt_for(concept))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"Saved {out_path} ({img.width}x{img.height}) via {nb.model}")
    return out_path


def generate_furnished_and_bare(out_dir: Path, concept):
    """Generates the furnished room for the given concept, then edits FROM
    it to produce a bare (no furniture/decor) version of the same room --
    same technique as architectural_assembly_reel's site/after pair.
    Returns (furnished_path, bare_path)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    nb = NanoBanana()

    furnished_img = nb.gen(prompt_for(concept))
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
    concepts = load_concepts()
    idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    generate_furnished_and_bare(out_dir, concepts[idx % len(concepts)])


if __name__ == "__main__":
    main()
