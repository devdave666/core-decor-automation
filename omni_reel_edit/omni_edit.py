"""
Video-to-video reel editing via Gemini "omni" (client.interactions.create).

Dev supplied the API shape (Colab snippet): the `interactions` namespace with
`gemini-omni-1.1-flash-preview`, an `Api-Revision` header, and steps[] output
carrying text/video parts. This runs it through our existing WIF/ADC auth on
project ...bfa, location="global" (same place the Gemini 3 image family lives).

The `input` type alias is `Union[str, List[Step], List[Content], Content]`; we
pass a list of Content items: one text instruction + one video
(`{"type": "video", "data": <b64>, "mime_type": "video/mp4"}`). Output video
comes back on a `model_output` step as a `video` content part -- inline base64
`data`, or a `gs://` `uri` if the service delivered to Cloud Storage (this
project has no bucket, so we request `delivery="inline"`).

Modes:
  --probe                     tiny reachability check, no video in/out
  --in V --instruction T --out O   real edit

Auth: WIF/ADC in GitHub Actions (google-github-actions/auth@v2).
"""
import argparse
import base64
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

PROJECT = "project-58f4f689-36b9-406b-bfa"
LOCATION = "global"
API_REVISION = "2026-05-20"

# The GCP console shows a real quota only for base_model "gemini-omni-flash-
# preview" (value 3/min, not raisable right now) -- "gemini-omni-1.1-flash-
# preview" from Dev's snippet returns a hard 429 (0 quota). So call the
# un-versioned name first.
MODEL_CANDIDATES = [
    "gemini-omni-flash-preview",
    "gemini-omni-1.1-flash-preview",
]

POLL_INTERVAL_S = 15
POLL_TIMEOUT_S = 1200

# Quota is only ~3 requests/min -- back off and retry on 429 rather than fail.
RL_RETRIES = 5
RL_BASE_DELAY_S = 25


def _client():
    return genai.Client(
        vertexai=True, project=PROJECT, location=LOCATION,
        http_options=types.HttpOptions(headers={"Api-Revision": API_REVISION}),
    )


def _as_dict(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return {}


def _iter_steps(interaction):
    steps = getattr(interaction, "steps", None)
    if steps is None and isinstance(interaction, dict):
        steps = interaction.get("steps")
    return steps or []


def _collect(interaction):
    """Return (texts, video_bytes_list) from an interaction's model_output steps."""
    texts, videos = [], []
    for step in _iter_steps(interaction):
        d = _as_dict(step)
        if d.get("type") != "model_output":
            continue
        for part in d.get("content") or []:
            pd = _as_dict(part) if not isinstance(part, dict) else part
            if pd.get("type") == "text" and pd.get("text"):
                texts.append(pd["text"])
            elif pd.get("type") == "video":
                data = pd.get("data")
                uri = pd.get("uri")
                if data:
                    videos.append(base64.b64decode(data))
                elif uri and uri.startswith("gs://"):
                    from google.cloud import storage
                    bkt, blob = uri[5:].split("/", 1)
                    videos.append(storage.Client().bucket(bkt).blob(blob).download_as_bytes())
    return texts, videos


def _create(client, model, input_, **kw):
    for attempt in range(RL_RETRIES):
        try:
            interaction = client.interactions.create(model=model, input=input_, **kw)
            break
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if ("429" in msg or "too_many_requests" in msg or "RESOURCE_EXHAUSTED" in msg) \
                    and attempt < RL_RETRIES - 1:
                delay = RL_BASE_DELAY_S * (attempt + 1)
                print(f"  429 (quota ~3/min), waiting {delay}s "
                      f"(attempt {attempt + 1}/{RL_RETRIES})...")
                time.sleep(delay)
                continue
            raise
    # poll if the service returned something still running
    waited = 0
    while True:
        d = _as_dict(interaction)
        status = (d.get("status") or getattr(interaction, "status", None) or "")
        status = str(status).lower()
        if status in ("", "completed", "succeeded", "done", "failed", "cancelled", "error"):
            return interaction, status
        if waited >= POLL_TIMEOUT_S:
            return interaction, f"timeout({status})"
        time.sleep(POLL_INTERVAL_S)
        waited += POLL_INTERVAL_S
        iid = d.get("id") or getattr(interaction, "id", None)
        interaction = client.interactions.get(interaction_id=iid)


def probe(in_path=None):
    """
    A text-only request to gemini-omni-flash-preview 400s ("invalid argument")
    -- the model wants video I/O. So the probe does a REAL minimal round-trip on
    a short clip (--in required) and dumps the response structure so we learn
    how the edited video comes back.
    """
    if not in_path:
        print("probe needs --in <short mp4>")
        sys.exit(2)
    client = _client()
    b64 = base64.b64encode(Path(in_path).read_bytes()).decode()
    text = {"type": "text", "text": "Slightly increase the contrast and warmth of this clip. Keep everything else identical."}
    vid = {"type": "video", "data": b64, "mime_type": "video/mp4"}
    model = MODEL_CANDIDATES[0]

    variants = [
        ("modalities-only", dict(response_modalities=["video"])),
        ("rf-minimal", dict(response_format={"type": "video"})),
        ("rf-inline", dict(response_modalities=["video"],
                           response_format={"type": "video", "delivery": "inline"})),
        ("rf-720", dict(response_format={"type": "video", "delivery": "inline",
                                         "resolution": "720p", "aspect_ratio": "9:16"})),
        ("bare", dict()),
        ("text-first-video", dict(response_modalities=["video"], _order="tv")),
    ]
    for label, kw in variants:
        order_tv = kw.pop("_order", None) == "tv"
        inp = [text, vid] if not order_tv else [vid, text]
        print(f"--- {model} / variant={label} kw={list(kw)} ---")
        try:
            interaction, status = _create(client, model, input_=inp, store=False, **kw)
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {str(e)[:500]}")
            continue
        d = _as_dict(interaction)
        print(f"  OK status={status!r} keys={list(d.keys())}")
        for i, step in enumerate(_iter_steps(interaction)):
            sd = _as_dict(step)
            ct = [(_as_dict(p) if not isinstance(p, dict) else p).get("type")
                  for p in (sd.get("content") or [])]
            print(f"    step[{i}] type={sd.get('type')} content={ct} err={sd.get('error')}")
        texts, videos = _collect(interaction)
        if texts:
            print(f"  text: {' '.join(texts)[:400]}")
        if videos:
            out = Path(in_path).with_name("probe_out.mp4")
            out.write_bytes(videos[0])
            print(f"  *** VIDEO OK ({label}): {len(videos[0])} bytes -> {out} ***")
        return model
    print("no request variant worked")
    sys.exit(1)


def edit(in_path, instruction, out_path):
    client = _client()
    b64 = base64.b64encode(Path(in_path).read_bytes()).decode()
    last_err = None
    for model in MODEL_CANDIDATES:
        print(f"--- edit via {model} ---")
        try:
            interaction, status = _create(
                client, model,
                input_=[
                    {"type": "text", "text": instruction},
                    {"type": "video", "data": b64, "mime_type": "video/mp4"},
                ],
                response_modalities=["video"],
                response_format={
                    "type": "video", "delivery": "inline",
                    "resolution": "1080p", "aspect_ratio": "9:16",
                },
                store=False,
            )
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {str(e)[:500]}")
            last_err = e
            continue
        texts, videos = _collect(interaction)
        if texts:
            print(f"  model said: {' '.join(texts)[:500]}")
        if not videos:
            print(f"  status={status!r} but no video in output; keys={list(_as_dict(interaction).keys())}")
            last_err = RuntimeError("no video part in model_output")
            continue
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(videos[0])
        print(f"  wrote {out_path} ({len(videos[0])} bytes) via {model}")
        return
    raise RuntimeError(f"omni edit produced no video. last error: {last_err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--in", dest="in_path")
    ap.add_argument("--instruction")
    ap.add_argument("--instruction-file")
    ap.add_argument("--out", dest="out_path")
    args = ap.parse_args()

    if args.probe:
        probe(args.in_path)
        return
    instruction = args.instruction
    if args.instruction_file:
        instruction = Path(args.instruction_file).read_text().strip()
    if not (args.in_path and instruction and args.out_path):
        ap.error("need --in, --instruction/--instruction-file and --out (or --probe)")
    edit(args.in_path, instruction, args.out_path)


if __name__ == "__main__":
    main()
