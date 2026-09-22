"""
Decor Drop Reel -- fully automated daily pipeline, seventh content type.

Per run:
  1. generate_room.generate_furnished_and_bare(): Nano Banana Pro generates
     ONE bold, fully-furnished room, then edits FROM it to produce a bare
     (no furniture/decor) version of the same room -- same site/after
     technique architectural_assembly_reel uses. No fixed concept list --
     room type and style are left to the model's own judgment each run, so
     this format doesn't need a concept_index rotation the way every other
     content type in this repo does.
  2. generate_omni_reveal.generate_reveal(): the bare room goes in as the
     explicit START frame and the furnished room as the explicit END frame
     via Gemini omni's two_frame_to_video(). v1 (end-frame-only, leaving
     the starting state to the model's own judgment) worked but Gemini QA
     caught a real issue -- a ~1.2s static shot of the FINISHED room before
     it reset to empty and did the actual build (see llms.txt). Giving it
     an explicit bare start frame instead fixed that outright (confirmed by
     a second full-video Gemini QA pass). Prompt stays deliberately simple
     either way, per Dev's standing instruction.
  3. add_kenburns_start.add_kenburns(): even with the fix above, the clip
     still opens on ~1.3s of static (now correctly EMPTY, not finished)
     room before motion starts. Per Dev's explicit fallback instruction, a
     simple Ken Burns zoom-out (1.10x -> 1.0x) is applied over just that
     opening beat, unconditionally, to give it a hook from frame one.
  4. finalize(): strip metadata; reuses architectural_assembly_reel's
     gemini-2.5-flash speech check + local de-voice repair verbatim --
     same project-wide Veo/omni risk, not specific to this format.
  5. Host + publish to Instagram, Facebook, TikTok (via Buffer), YouTube
     (via Buffer).
  6. generate_hotspots.identify(): Gemini vision looks at the SAME
     furnished room photo and proposes room/style/hotspots -- no human
     review step, unlike the original 57 shop concepts' "AI-drafted first
     pass" (this format has no human in the loop by design, so the
     auto-identification has to be trusted, not just used as a draft).
  7. add_to_shop.add_entry(): lists the room on the shop with those
     hotspots, auto-numbered "dd" id.
  8. Advance caption_index (own counter, own file, never shared with
     another pipeline's -- per this repo's standing convention).

Runs daily via decor-drop-reel.yml, 8:00 PM EST (01:00 UTC, fixed offset --
drifts to 9PM local during EDT, same known limitation as every other cron
schedule in this repo) and on workflow_dispatch. Auth: WIF/ADC +
META_*/BUFFER_* secrets, same as every other daily pipeline; the shop-listing
step additionally needs a `git push` to main, which just works the same way
`upload_video_to_public_host` already does in Actions (persist-credentials).
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT_PATH = HERE.parent
sys.path.insert(0, str(REPO_ROOT_PATH))
sys.path.insert(0, str(HERE))

import core_decor_reel_pipeline as core  # noqa: E402
from generate_room import generate_furnished_and_bare  # noqa: E402
from generate_omni_reveal import generate_reveal  # noqa: E402
from add_kenburns_start import add_kenburns  # noqa: E402
from generate_hotspots import identify as identify_hotspots  # noqa: E402
from add_to_shop import add_entry  # noqa: E402


def _import_from_path(module_name, file_path):
    # architectural_assembly_reel/run_daily.py has the SAME module name as
    # this file -- a plain `sys.path` import would resolve "run_daily" back
    # to whichever of the two is first on the path (this file, since it's
    # the one currently running), not the intended one. Load it by explicit
    # file path instead so the name collision can't bite.
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AAR_DIR = REPO_ROOT_PATH / "architectural_assembly_reel"
sys.path.insert(0, str(AAR_DIR))  # its own run_daily.py assumes this dir is
                                    # on sys.path (true when run directly,
                                    # not when loaded via importlib below)
finalize = _import_from_path("aar_run_daily", AAR_DIR / "run_daily.py").finalize  # reused verbatim (speech check + de-voice)


def _counter(name, default=0):
    p = HERE / f"{name}.txt"
    return int(p.read_text().strip()) if p.exists() else default


def _advance(name, value, repo_root):
    p = HERE / f"{name}.txt"
    p.write_text(str(value))
    rel = p.relative_to(Path(repo_root)).as_posix()
    import subprocess
    subprocess.run(["git", "-C", str(repo_root), "add", rel], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-m",
                    f"decor-drop-reel: advance {name} to {value}"], check=True)
    core._git_push_with_retry(repo_root)


def main():
    import os
    repo_root = os.environ.get("GITHUB_WORKSPACE") or os.environ.get("REPO_ROOT", ".")
    out = HERE / "output"
    out.mkdir(exist_ok=True)

    captions = json.loads((HERE / "captions.json").read_text())
    capi = _counter("caption_index") % len(captions)
    caption = captions[capi]

    furnished_path, bare_path = generate_furnished_and_bare(out)
    raw = generate_reveal(bare_path, furnished_path, out / "raw.mp4")

    kb = out / "raw_kb.mp4"
    add_kenburns(raw, kb)

    clean = out / "decor_drop_reel.mp4"
    finalize(kb, clean)

    duration = core.get_audio_duration_seconds(clean)
    core.validate_reel_for_meta(clean, duration)

    public_url = core.upload_video_to_public_host(clean, repo_root)
    print(f"hosted: {public_url}")

    ig = core.publish_to_instagram(public_url, caption)
    fb = core.publish_to_facebook(public_url, caption, expected_duration_s=duration)
    tk = core.publish_to_buffer(public_url, caption, os.environ["BUFFER_TIKTOK_CHANNEL_ID"], "tiktok")
    yt = core.publish_to_buffer(public_url, caption, os.environ["BUFFER_YOUTUBE_CHANNEL_ID"], "youtube",
                                youtube_title=caption.split("\n")[0][:100])
    print(f"Done. IG={ig} FB={fb} TikTok={tk} YouTube={yt}")

    room, style, hotspot_specs = identify_hotspots(furnished_path)
    entry_id, shop_url = add_entry(furnished_path, room, style, hotspot_specs)
    print(f"Shop: {entry_id} ({room}, {style}) -> {shop_url}")

    _advance("caption_index", (capi + 1) % len(captions), repo_root)


if __name__ == "__main__":
    main()
