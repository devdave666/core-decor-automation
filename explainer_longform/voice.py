"""
Voice stage: one ElevenLabs v4 generation per beat, with character-level timestamps
so the renderer can highlight the spoken word. Audio tags like [excited] are
directions, not speech; they are stripped from the caption words.

Free-plan output carries no commercial license; subscribe before publishing.
"""
import base64
import json
import os
import subprocess
import wave
from pathlib import Path

import requests

API = "https://api.elevenlabs.io/v1"
MODEL_ID = "eleven_v4"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"   # premade "Rachel"; override via ELEVENLABS_VOICE_ID
SR = 44100


def list_voices():
    r = requests.get(f"{API}/voices", headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]})
    r.raise_for_status()
    for v in r.json()["voices"]:
        print(f"{v['voice_id']}  {v['name']}  [{v.get('category')}]  "
              f"{(v.get('labels') or {})}")


def _words_from_alignment(al):
    chars = al["characters"]
    starts = al["character_start_times_seconds"]
    ends = al["character_end_times_seconds"]
    words, cur, in_tag = [], None, False
    for ch, s, e in zip(chars, starts, ends):
        if ch == "[":
            in_tag = True
            continue
        if in_tag:
            if ch == "]":
                in_tag = False
            continue
        if ch.isspace():
            if cur:
                words.append(cur)
                cur = None
            continue
        if cur is None:
            cur = {"w": ch, "s": s, "e": e}
        else:
            cur["w"] += ch
            cur["e"] = e
    if cur:
        words.append(cur)
    return words


def _synth(text, voice_id, key, prev_text, next_text, prev_ids):
    body = {"text": text, "model_id": MODEL_ID}
    if prev_text:
        body["previous_text"] = prev_text
    if next_text:
        body["next_text"] = next_text
    if prev_ids:
        body["previous_request_ids"] = prev_ids[-3:]
    url = f"{API}/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128"
    headers = {"xi-api-key": key, "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json=body, timeout=180)
    if r.status_code in (400, 422) and len(body) > 2:
        print(f"  context fields rejected ({r.text[:160]}); retrying without them")
        r = requests.post(url, headers=headers, json={"text": text, "model_id": MODEL_ID},
                          timeout=180)
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:400]}")
    return r.json(), r.headers.get("request-id")


def _to_wav(src, dst):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                    "-ar", str(SR), "-ac", "1", str(dst)], check=True)


def _wav_duration(path):
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def _mock(text, wav_path):
    import re
    words = [w for w in re.sub(r"\[[^\]]*\]", " ", text).split()]
    dur, t, out = 0.0, 0.0, []
    for w in words:
        d = 0.18 + 0.045 * len(w)
        out.append({"w": w, "s": t, "e": t + d})
        t += d + 0.04
    dur = t + 0.2
    with wave.open(str(wav_path), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR)
        f.writeframes(b"\x00\x00" * int(dur * SR))
    return out


def generate_voice(spec, out_dir, mock=False):
    """Returns {beat_id: {"wav": path, "duration": s, "words": [{w,s,e}]}}, cached."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = out_dir / "voice.json"
    cache = json.loads(index.read_text()) if index.exists() else {}
    key = None if mock else os.environ["ELEVENLABS_API_KEY"]
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
    beats, ids = spec["beats"], []
    for i, b in enumerate(beats):
        wav = out_dir / f"{b['id']}.wav"
        if b["id"] in cache and wav.exists():
            continue
        print(f"--- voice {b['id']} ---")
        if mock:
            words = _mock(b["text"], wav)
        else:
            prev_t = beats[i - 1]["text"] if i else None
            next_t = beats[i + 1]["text"] if i + 1 < len(beats) else None
            data, rid = _synth(b["text"], voice_id, key, prev_t, next_t, ids)
            if rid:
                ids.append(rid)
            mp3 = out_dir / f"{b['id']}.mp3"
            mp3.write_bytes(base64.b64decode(data["audio_base64"]))
            _to_wav(mp3, wav)
            words = _words_from_alignment(data["alignment"])
        cache[b["id"]] = {"wav": str(wav), "duration": _wav_duration(wav), "words": words}
        index.write_text(json.dumps(cache, indent=1))
    return cache


if __name__ == "__main__":
    list_voices()
