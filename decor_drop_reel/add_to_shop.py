"""
Decor Drop Reel -- lists a room image on the shop (shop/products.json), same
mechanism used for the one-off `kf01` kitchen entry: webp conversion,
auto-numbered id (prefix "dd"), git-plumbing commit straight to origin/main
(no working-tree branch switch -- GitHub Pages and raw.githubusercontent.com
both serve shop assets from main, and this avoids disturbing whatever branch
is currently checked out).

Hotspot identification (which products are in the photo, and where) is NOT
automated here -- there's no object-detection step in this repo, matching
how the original 57 concepts were seeded ("AI-drafted first pass" per
shop/README.md): whoever's generating the entry looks at the photo and
supplies hotspot specs. This module only handles the mechanical add-to-
catalog part: link generation, id assignment, and the commit.
"""
import json
import os
import random
import re
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_JSON = REPO_ROOT / "shop" / "products.json"
WEBP_DIR = REPO_ROOT / "assets" / "application_web"
ID_PREFIX = "dd"  # decor drop


def _run(args, index_file=None):
    env = os.environ.copy()
    if index_file:
        env["GIT_INDEX_FILE"] = index_file
    return subprocess.run(args, cwd=str(REPO_ROOT), env=env, check=True,
                           capture_output=True, text=True).stdout.strip()


def gen_amazon_link(keywords, market="us"):
    host = {"us": "www.amazon.com", "ca": "www.amazon.ca"}[market]
    tag = {"us": "dev0f7d00-20", "ca": "dev0f7d-20"}[market]
    link_id = "".join(random.choice("0123456789abcdef") for _ in range(32))
    k = urllib.parse.quote_plus(keywords)
    url = f"https://{host}/s?k={k}&linkCode=ll2&tag={tag}&linkId={link_id}"
    if market == "us":
        url += "&language=en_US"
    return url + "&ref_=as_li_ss_tl"


def build_hotspots(entry_id, specs):
    """specs: list of (x, y, label, productName, searchKeywords[, marketplace])"""
    out = []
    for i, spec in enumerate(specs, 1):
        x, y, label, product_name, keywords = spec[:5]
        market = spec[5] if len(spec) > 5 else "us"
        out.append({
            "id": f"{entry_id}-h{i}", "x": x, "y": y, "label": label,
            "productName": product_name,
            "productUrl": gen_amazon_link(keywords, market),
            "marketplace": market,
            "searchKeywords": keywords,
            "auto": True,
        })
    return out


def add_entry(image_path, room, style, hotspot_specs):
    """Returns (entry_id, shop_url)."""
    _run(["git", "fetch", "origin", "main"])
    base = _run(["git", "rev-parse", "origin/main"])

    products_json_text = _run(["git", "show", f"{base}:shop/products.json"])
    products = json.loads(products_json_text)

    nums = [int(p["id"][len(ID_PREFIX):]) for p in products
            if p["id"].startswith(ID_PREFIX) and p["id"][len(ID_PREFIX):].isdigit()]
    entry_id = f"{ID_PREFIX}{(max(nums) + 1) if nums else 1:02d}"

    hotspots = build_hotspots(entry_id, hotspot_specs)

    def _slugify(s):
        return re.sub(r"[^a-z0-9]+", "", s.lower())

    slug = f"{_slugify(room)}_{_slugify(style)}"
    webp_name = f"{entry_id}_{slug}_app.webp"
    webp_path = WEBP_DIR / webp_name
    WEBP_DIR.mkdir(parents=True, exist_ok=True)
    Image.open(image_path).convert("RGB").save(webp_path, "WEBP", quality=85)

    entry = {
        "id": entry_id,
        "image": f"https://raw.githubusercontent.com/devdave666/core-decor-automation/main/assets/application_web/{webp_name}",
        "room": room, "style": style, "hotspots": hotspots,
    }
    products.append(entry)
    PRODUCTS_JSON.write_text(json.dumps(products, indent=2, ensure_ascii=False), encoding="utf-8")

    tmpidx = tempfile.mktemp()
    try:
        _run(["git", "read-tree", base], index_file=tmpidx)
        rel_webp = str(webp_path.relative_to(REPO_ROOT)).replace("\\", "/")
        _run(["git", "add", "shop/products.json", rel_webp], index_file=tmpidx)
        tree = _run(["git", "write-tree"], index_file=tmpidx)
        commit = _run(["git", "commit-tree", tree, "-p", base, "-m",
                       f"shop: add {entry_id} ({room}, {style})\n\n"
                       "Auto-generated via decor_drop_reel pipeline."])
        _run(["git", "push", "origin", f"{commit}:main"])
    finally:
        if os.path.exists(tmpidx):
            os.remove(tmpidx)

    return entry_id, "https://devdave666.github.io/core-decor-automation/shop/"
