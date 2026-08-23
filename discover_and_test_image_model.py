"""
One-off diagnostic for test-vertex-imagen.yml. Two guessed Vertex AI image model
names (imagen-4.0-generate-001, gemini-2.5-flash-image-preview) both 404'd in
real runs against this project -- see llms.txt for the full history. Rather than
guess a third name from search results, this queries Vertex's own publisher-model
catalog for this exact project/region, filters for anything image-related, and
tries generate_content() against each candidate until one actually returns image
bytes. Not part of any content pipeline -- throwaway connectivity/discovery tool.
"""
import google.auth
import google.auth.transport.requests
import requests
from google import genai

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "us-central1"


def list_image_model_candidates(headers):
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/publishers/google/models"
    candidates = []
    page_token = None
    while True:
        params = {"pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code != 200:
            print(f"Model list call failed: {r.status_code} {r.text[:500]}")
            break
        body = r.json()
        for m in body.get("publisherModels", body.get("models", [])):
            name = m.get("name", "")
            if "image" in name.lower() or "imagen" in name.lower():
                candidates.append(name)
        page_token = body.get("nextPageToken")
        if not page_token:
            break
    return candidates


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
    creds, _ = google.auth.default()
    creds.refresh(google.auth.transport.requests.Request())
    headers = {"Authorization": f"Bearer {creds.token}"}

    candidates = list_image_model_candidates(headers)
    print(f"Found {len(candidates)} image-related publisher models:")
    for c in candidates:
        print(f"  {c}")

    if not candidates:
        print("No image-related publisher models found via the catalog listing -- stopping here rather than guessing blind.")
        raise SystemExit(1)

    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)

    for model_path in candidates:
        model_id = model_path.split("/")[-1]
        if try_generate(client, model_id):
            return
    print("No candidate model produced an image.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
