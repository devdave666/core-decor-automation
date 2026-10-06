"""
Image stage: generate every unique image at native 4K with Nano Banana Pro, and
locate each "detail" crop target with Gemini so zooms land on the right object.

Pro only, no flash fallback: a silent downgrade would make zoomed shots soft.
"""
import json
import time
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT = "core-decor-657616"
IMG_MODEL = "gemini-3-pro-image"
LOCATE_MODEL = "gemini-2.5-flash"
LOCATION = "global"
MIN_WIDTH = 3500          # warn if the model returns less than ~4K
REF_WIDTH = 2048          # edit reference is downscaled; the output is still native 4K
MAX_RETRIES = 5
RETRY_BASE_S = 20


def _client():
    from google import genai
    return genai.Client(vertexai=True, project=PROJECT, location=LOCATION)


def _config():
    from google.genai import types
    return types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio="16:9", image_size="4K"),
        safety_settings=[types.SafetySetting(category=c, threshold="OFF") for c in (
            "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_DANGEROUS_CONTENT",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_HARASSMENT")],
    )


def _generate(client, contents):
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.models.generate_content(
                model=IMG_MODEL, contents=contents, config=_config())
            for cand in resp.candidates or []:
                for part in (cand.content.parts if cand.content else None) or []:
                    inl = getattr(part, "inline_data", None)
                    if inl and getattr(inl, "data", None):
                        return Image.open(BytesIO(inl.data)).convert("RGB")
            reasons = [str(getattr(c, "finish_reason", None)) for c in resp.candidates or []]
            feedback = getattr(resp, "prompt_feedback", None)
            raise RuntimeError(f"EMPTY no image returned; finish_reason={reasons} "
                               f"prompt_feedback={feedback}")
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            empty = msg.startswith("EMPTY")
            if empty:
                print(f"  attempt {attempt + 1}: {msg[:300]}")
            if (("429" in msg or "RESOURCE_EXHAUSTED" in msg or "503" in msg or empty)
                    and attempt < MAX_RETRIES - 1):
                if empty:
                    time.sleep(5)
                    continue
                d = RETRY_BASE_S * (2 ** attempt)
                print(f"  retryable error, waiting {d}s: {msg[:120]}")
                time.sleep(d)
                continue
            raise


FALLBACK_FOCUS = (0.5, 0.5, 0.4)


def _find_box(x):
    """First flat list of 4 numbers anywhere in a JSON structure (Gemini varies the shape)."""
    if isinstance(x, (list, tuple)):
        if len(x) == 4 and all(isinstance(v, (int, float)) for v in x):
            return x
        for item in x:
            r = _find_box(item)
            if r:
                return r
    elif isinstance(x, dict):
        for v in x.values():
            r = _find_box(v)
            if r:
                return r
    return None


def _reference(img):
    if img.width <= REF_WIDTH:
        return img
    return img.resize((REF_WIDTH, round(img.height * REF_WIDTH / img.width)),
                      Image.LANCZOS)


def _mock_image(key, w=3840, h=2160):
    seed = sum(map(ord, key))
    img = Image.new("RGB", (w, h))
    px = Image.linear_gradient("L").resize((w, h))
    tint = Image.new("RGB", (w, h), ((seed * 53) % 200 + 30, (seed * 97) % 200 + 30,
                                     (seed * 29) % 200 + 30))
    img = Image.composite(tint, Image.new("RGB", (w, h), (20, 20, 25)), px)
    d = ImageDraw.Draw(img)
    for gx in range(0, w, 240):
        d.line([(gx, 0), (gx, h)], fill=(255, 255, 255), width=2)
    for gy in range(0, h, 240):
        d.line([(0, gy), (w, gy)], fill=(255, 255, 255), width=2)
    d.text((w // 2 - 200, h // 2), key, fill=(255, 255, 255))
    return img


def generate_images(spec, out_dir, mock=False):
    """Returns {key: Path}. Skips images already on disk (resumable)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    client = None if mock else _client()
    paths = {}
    # dict order is dependency order: a base, then each edit after its source
    for key, s in spec["images"].items():
        path = out_dir / f"{key}.png"
        paths[key] = path
        if path.exists():
            continue
        print(f"--- image {key} ---")
        if mock:
            img = _mock_image(key)
        elif "edit_of" in s:
            src = Image.open(paths[s["edit_of"]]).convert("RGB")
            img = _generate(client, [s["prompt"], _reference(src)])
        else:
            img = _generate(client, [s["prompt"]])
        print(f"  {key}: {img.width}x{img.height}")
        if img.width < MIN_WIDTH:
            print(f"  WARNING: {key} is only {img.width}px wide; zoomed shots will be soft")
        img.save(path, format="PNG")
    return paths


def locate_focuses(spec, paths, out_json, mock=False):
    """Maps "<image>|<focus text>" -> [cx, cy, size] (normalised 0-1), cached."""
    out_json = Path(out_json)
    cache = json.loads(out_json.read_text()) if out_json.exists() else {}
    need = {(sh["image"], sh["focus"]) for b in spec["beats"] for sh in b["shots"]
            if sh.get("move") == "detail"}
    client = None
    for image, focus in sorted(need):
        k = f"{image}|{focus}"
        if k in cache and cache[k] != list(FALLBACK_FOCUS):
            continue
        if mock:
            cache[k] = [0.3 + (len(focus) % 5) * 0.1, 0.45, 0.25]
            continue
        client = client or _client()
        from google.genai import types
        img = _reference(Image.open(paths[image]).convert("RGB"))
        try:
            resp = client.models.generate_content(
                model=LOCATE_MODEL,
                contents=[img, "Return JSON {\"box_2d\": [ymin, xmin, ymax, xmax]} with "
                          "coordinates normalised to 0-1000, tightly bounding: " + focus],
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            box = _find_box(json.loads(resp.text))
            if box is None:
                raise ValueError(f"no box in {resp.text[:120]!r}")
            ymin, xmin, ymax, xmax = [v / 1000 for v in box]
            if not (0 <= xmin < xmax <= 1 and 0 <= ymin < ymax <= 1):
                raise ValueError(f"bad box {box}")
            cache[k] = [(xmin + xmax) / 2, (ymin + ymax) / 2,
                        max(xmax - xmin, ymax - ymin)]
        except Exception as e:  # noqa: BLE001
            print(f"  locate failed for {k!r} ({str(e)[:100]}); using centre")
            cache[k] = list(FALLBACK_FOCUS)
    out_json.write_text(json.dumps(cache, indent=1))
    return cache
