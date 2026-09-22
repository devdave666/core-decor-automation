"""
Decor Drop Reel -- auto-identifies room/style/shoppable-hotspots from the
generated room photo via Gemini vision. Closes the loop for the fully
unattended daily pipeline: the original 57 shop concepts got an "AI-drafted
first pass" that a human then reviewed (per shop/README.md); a daily cron
job has no human in the loop, so this step has to be trustworthy enough to
publish straight through. Output feeds directly into add_to_shop.add_entry().

Usage: python decor_drop_reel/generate_hotspots.py <room.png>
"""
import json
import re
import sys
from pathlib import Path

from google import genai
from google.genai import types

PROJECT = "core-decor-657616"

PROMPT = """Look at this interior design photograph (vertical 9:16). Identify:
1. The room type (e.g. "Living Room", "Bedroom", "Kitchen", "Home Office", "Bathroom", "Dining Room").
2. A short, punchy 2-4 word style label for this room's look (e.g. "Emerald & Brass", "Warm Minimalist", "Coastal Boho").
3. Between 5 and 7 distinct, individually purchasable furniture or decor items visible in it (e.g. a sofa, a chair, a coffee table, a rug, a light fixture, a vase -- NOT built-in architecture like walls, windows, flooring or fixed cabinetry).

For each item, give its position in the image as x/y PERCENTAGES (0-100, where 0,0 is the top-left corner and 100,100 is the bottom-right corner, landing ON the actual object), a short label, a descriptive product name, and a concrete Amazon search phrase (material, color, shape -- specific enough to find a similar real product, not just the room/style name).

Return ONLY a JSON object, no other text, no markdown fencing, in this exact shape:
{
  "room": "Living Room",
  "style": "Emerald & Brass",
  "items": [
    {"x": 34.5, "y": 60.0, "label": "Sofa", "productName": "Curved Emerald Velvet Sofa", "searchKeywords": "curved emerald green velvet sofa brass base"}
  ]
}"""


def identify(image_path):
    client = genai.Client(vertexai=True, project=PROJECT, location="global")
    resp = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[
            types.Part.from_bytes(data=Path(image_path).read_bytes(), mime_type="image/png"),
            PROMPT,
        ],
    )
    text = resp.text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    data = json.loads(text)
    specs = [(it["x"], it["y"], it["label"], it["productName"], it["searchKeywords"])
              for it in data["items"]]
    return data["room"], data["style"], specs


def main():
    room, style, specs = identify(sys.argv[1])
    print(json.dumps({"room": room, "style": style, "hotspots": specs}, indent=2))


if __name__ == "__main__":
    main()
