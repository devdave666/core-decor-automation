"""Ad hoc forensic QA run for the l01 loft reveal reel. Real Gemini
multimodal video analysis (not sparse still-frame sampling) -- see llms.txt
for why that's the mandatory standard now."""
import sys
from pathlib import Path

from google import genai
from google.genai import types

PROJECT = "project-58f4f689-36b9-406b-bfa"

FORENSIC_SYSTEM_INSTRUCTION = (
    "You are an expert AI video forensic examiner. You are reviewing an "
    "AI-generated video for hallucination artifacts: objects or people "
    "appearing/disappearing without cause, identity drift (a person's face, "
    "hair, build or clothing changing between shots), duplicated or doubled "
    "objects/people, geometry errors (intersecting solids, floating "
    "objects, impossible architecture), unrequested material changes on "
    "surfaces nobody is touching, and any live animals appearing. Watch the "
    "entire video carefully, including the cut points between segments. "
    "Report every issue you find with an approximate timestamp, in order of "
    "severity. If truly nothing is wrong, say so plainly -- but do not "
    "hedge or soften real issues."
)

PROMPT = (
    "This is a 28-second, 7-clip video of a single woman single-handedly "
    "renovating a mice-infested loft into a finished modern loft. Focus "
    "especially on: (1) whether she is recognizably the SAME woman (face, "
    "hair, build, clothing) throughout all 7 clips and at every cut point, "
    "(2) whether any second person ever appears, (3) whether any live "
    "rodents/animals appear, (4) whether furniture/walls/flooring change "
    "without her touching them, (5) any geometry or continuity errors at "
    "the cuts between clips."
)


def main():
    video_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output/l01/clips/l01_loft.mp4")
    video_bytes = video_path.read_bytes()
    print(f"Loaded {video_path} ({len(video_bytes)} bytes)")

    client = genai.Client(vertexai=True, project=PROJECT, location="us-central1")
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=[
            types.Part.from_bytes(data=video_bytes, mime_type="video/mp4"),
            PROMPT,
        ],
        config=types.GenerateContentConfig(
            system_instruction=FORENSIC_SYSTEM_INSTRUCTION,
            thinking_config=types.ThinkingConfig(thinking_budget=1024),
        ),
    )
    print("\n=== gemini-2.5-pro forensic verdict ===\n")
    print(response.text)


if __name__ == "__main__":
    main()
