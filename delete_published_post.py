"""
Best-effort takedown of an already-published cross-post: Instagram media,
Facebook video, and the TikTok / YouTube posts made via Buffer.

Reality check on what's actually removable via API:
  - Facebook video: DELETE /{video_id}  -> supported.
  - Buffer post: deletePost mutation -> removes the Buffer record; for a
    post already sent it also asks the platform to retract where Buffer
    supports it (YouTube yes, TikTok best-effort).
  - Instagram: the Graph API has NO delete for published media. Reported
    here so it can be removed by hand in the app.

Usage:
  python delete_published_post.py --ig <id> --fb <video_id> \
      --buffer <tiktok_post_id> --buffer <youtube_post_id>
Env: META_SYSTEM_USER_TOKEN, BUFFER_API_KEY
"""
import argparse
import os

import requests

GRAPH = "https://graph.facebook.com/v22.0"


def del_fb(video_id, token):
    r = requests.delete(f"{GRAPH}/{video_id}", params={"access_token": token}, timeout=60)
    print(f"[facebook] {video_id}: {r.status_code} {r.text[:300]}")


def try_del_ig(media_id, token):
    r = requests.delete(f"{GRAPH}/{media_id}", params={"access_token": token}, timeout=60)
    print(f"[instagram] {media_id}: {r.status_code} {r.text[:300]}")
    if r.status_code != 200:
        print(f"[instagram] {media_id}: API delete not supported -- REMOVE THIS "
              f"POST BY HAND in the Instagram app.")


def del_buffer(post_id, token):
    for mutation in (
        "mutation D($id: ID!){ deletePost(input:{id:$id}){ __typename } }",
        "mutation D($id: ID!){ deletePost(input:{id:$id}){ id } }",
        "mutation D($id: ID!){ deletePost(id:$id){ __typename } }",
    ):
        r = requests.post(
            "https://api.buffer.com/graphql",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": mutation, "variables": {"id": post_id}},
            timeout=60,
        )
        body = r.json()
        if not body.get("errors"):
            print(f"[buffer] {post_id}: OK {body}")
            return
        print(f"[buffer] {post_id}: try failed -> {str(body['errors'])[:200]}")
    print(f"[buffer] {post_id}: all delete attempts failed -- remove this "
          f"post BY HAND in Buffer (and on TikTok/YouTube if it already sent).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ig")
    ap.add_argument("--fb")
    ap.add_argument("--buffer", action="append", default=[])
    args = ap.parse_args()

    meta = os.environ.get("META_SYSTEM_USER_TOKEN")
    buf = os.environ.get("BUFFER_API_KEY")

    if args.fb and meta:
        del_fb(args.fb, meta)
    if args.ig and meta:
        try_del_ig(args.ig, meta)
    for pid in args.buffer:
        if buf:
            del_buffer(pid, buf)


if __name__ == "__main__":
    main()
