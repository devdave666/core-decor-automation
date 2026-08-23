"""
One-off diagnostic for test-vertex-imagen.yml. Two guessed Vertex AI image model
names (imagen-4.0-generate-001, gemini-2.5-flash-image-preview) both 404'd in
real runs against this project -- see llms.txt for the full history. A first
attempt at listing the catalog via a hand-rolled google.auth credential refresh
also failed (a separate scope issue, unrelated to Vertex access itself -- the
genai client's own auth was already proven working by that point, since it had
reached the real API and gotten real 404s, not auth errors).

Fixed by reusing the SAME already-authenticated genai client to list models
instead of building a second parallel auth path: client.models.list(config=
{'query_base': True}) returns Vertex's base/publisher models, not just
project-tuned ones. Filters for anything image-related, then tries
generate_content() against each candidate until one actually returns image
bytes. Not part of any content pipeline -- throwaway connectivity/discovery tool.

CONFIRMED WORKING (2026-08-22, real generated image verified): gemini-2.5-flash-
image, no "-preview" suffix -- that suffix was the actual bug in the second
attempt, not a missing/retired model. Tried first below so a normal run skips
straight past the ~13 unrelated classification/detection/segmentation models
this project's catalog also returns for any name containing "image". Falls back
to trying the rest of the discovered list if that specific model ever stops
working, so this stays useful if Google renames/replaces it again later.
"""
from google import genai

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "us-central1"
KNOWN_WORKING_MODEL = "gemini-2.5-flash-image"


def try_generate(client, model_id):
    print(f"--- trying {model_id} ---")
    try:
        response = client.models.generate_content(
            model=model_id,
            contents="A minimalist modern living room interior, soft natural light, photorealistic, 9:16 vertical composition",
        )
    except Exception as e:
        print(f"  failed: {e}")
        return False

    for candidate in response.candidates:
        for part in candidate.content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                with open("test_output_0.png", "wb") as f:
                    f.write(inline.data)
                print(f"  SUCCESS -- saved test_output_0.png using model {model_id}")
                return True
    print(f"  {model_id} responded but no inline image data in the parts -- raw response:")
    print(f"  {response!r}"[:1000])
    return False


def main():
    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)

    print("Listing base/publisher models via client.models.list(query_base=True)...")
    candidates = []
    for m in client.models.list(config={"query_base": True}):
        name = getattr(m, "name", "") or ""
        if "image" in name.lower() or "imagen" in name.lower():
            candidates.append(name)

    print(f"Found {len(candidates)} image-related base models:")
    for c in candidates:
        print(f"  {c}")

    if not candidates:
        print("No image-related base models found via the listing -- stopping here rather than guessing blind.")
        raise SystemExit(1)

    model_ids = [c.split("/")[-1] for c in candidates]
    if KNOWN_WORKING_MODEL in model_ids:
        model_ids.remove(KNOWN_WORKING_MODEL)
        model_ids.insert(0, KNOWN_WORKING_MODEL)

    for model_id in model_ids:
        if try_generate(client, model_id):
            return
    print("No candidate model produced an image.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
