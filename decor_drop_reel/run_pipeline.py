"""
Decor Drop Reel -- full pipeline driver, steps 1-2 (generation). Step 3
(shop listing) is deliberately NOT automated here -- see add_to_shop.py's
docstring: hotspot placement needs a look at the actual generated photo,
same as every other concept in this shop ever added.

Usage: python decor_drop_reel/run_pipeline.py <out_dir>
Produces <out_dir>/room.png and <out_dir>/reveal.mp4.
"""
import sys
from pathlib import Path

from generate_room import generate_room
from generate_omni_reveal import generate_reveal


def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("decor_drop_reel/output")
    out_dir.mkdir(parents=True, exist_ok=True)

    room_path = generate_room(out_dir / "room.png")
    reveal_path = generate_reveal(room_path, out_dir / "reveal.mp4")
    print(f"ROOM={room_path}")
    print(f"REVEAL={reveal_path}")


if __name__ == "__main__":
    main()
