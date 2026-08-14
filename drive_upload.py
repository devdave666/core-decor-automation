"""
Direct sandbox-to-Drive upload/download. Bypasses the chat entirely for uploads, so
there's no file-size ceiling the way there was going through the Drive tool's base64
parameter.

Uses OAuth as the user (not a service account) because service accounts have zero
storage quota on personal Google Drive and cannot create files there — confirmed via
a live 403 storageQuotaExceeded from the API. User OAuth uploads against real quota.

Credentials load from environment variables (GOOGLE_OAUTH_CLIENT_ID/SECRET/
REFRESH_TOKEN) first, since that's how this runs in GitHub Actions — those exist as
repo secrets. Falls back to a local .credentials/oauth.json file for sandbox testing,
chmod 600, never copied anywhere chat-visible.
"""
import json
import os

import requests

_CRED_PATH = os.path.join(os.path.dirname(__file__), ".credentials", "oauth.json")

ROOT_FOLDER_ID = "1ApO60R02Ed5bqt7Xfuh6fsWVKEn5QIf8"  # Interior Design Reels
TEMPLATE_REELS_FOLDER_ID = "1eiAccCmI7KD1iAEa1D9QeZTKecMiGZqs"
FOLDER_IDS = {
    "batch01": "1gVk3FgJUiZ1DEBKng8lpDU2VCNx2xnCj",
    "batch02": "11dhFLOBL0gTXg06yom3THQIGOcrn2dCO",
}

_token_cache = {"access_token": None}


def _load_credentials():
    if os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN"):
        return {
            "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"],
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    with open(_CRED_PATH) as f:
        return json.load(f)


def _get_access_token():
    # Access tokens expire hourly; refresh_token does not (app is Published, not in
    # Testing, so it won't rot after 7 days). Cheap to just refresh every call rather
    # than track expiry — one extra request per upload, not worth the complexity.
    cfg = _load_credentials()
    r = requests.post(cfg["token_uri"], data={
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "refresh_token": cfg["refresh_token"],
        "grant_type": "refresh_token",
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def get_or_create_folder(name, parent_id):
    """Returns an existing folder's id if one with this name already lives under
    parent_id, otherwise creates it. Avoids duplicate 'batch03' folders on reruns."""
    token = _get_access_token()
    q = (f"name = '{name}' and '{parent_id}' in parents "
         f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    r = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        params={"q": q, "fields": "files(id,name)"},
        headers={"Authorization": f"Bearer {token}"}, timeout=30,
    )
    r.raise_for_status()
    hits = r.json().get("files", [])
    if hits:
        return hits[0]["id"]

    r = requests.post(
        "https://www.googleapis.com/drive/v3/files",
        params={"fields": "id"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"name": name, "mimeType": "application/vnd.google-apps.folder",
              "parents": [parent_id]},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def upload_file(local_path, folder_id, remote_name=None, mime_type="image/png"):
    """Uploads local_path into folder_id. Returns the Drive file id and webViewLink."""
    token = _get_access_token()
    name = remote_name or os.path.basename(local_path)
    metadata = {"name": name, "parents": [folder_id]}
    with open(local_path, "rb") as f:
        files = {
            "metadata": ("metadata", json.dumps(metadata), "application/json"),
            "file": (name, f, mime_type),
        }
        r = requests.post(
            "https://www.googleapis.com/upload/drive/v3/files"
            "?uploadType=multipart&fields=id,name,webViewLink",
            headers={"Authorization": f"Bearer {token}"},
            files=files, timeout=120,
        )
    r.raise_for_status()
    return r.json()


def get_folder_name(folder_id):
    """Returns a Drive folder's own display name — used to derive a product name
    from a one-off product folder without requiring it be typed in by hand."""
    token = _get_access_token()
    r = requests.get(
        f"https://www.googleapis.com/drive/v3/files/{folder_id}",
        params={"fields": "name"},
        headers={"Authorization": f"Bearer {token}"}, timeout=30,
    )
    r.raise_for_status()
    return r.json()["name"]


def list_files_in_folder(folder_id):
    """Returns [{'id':..., 'name':...}, ...] for all non-trashed files in a folder,
    sorted by name for deterministic rotation ordering."""
    token = _get_access_token()
    r = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        params={"q": f"'{folder_id}' in parents and trashed = false",
                "fields": "files(id,name)", "pageSize": 100},
        headers={"Authorization": f"Bearer {token}"}, timeout=30,
    )
    r.raise_for_status()
    return sorted(r.json().get("files", []), key=lambda f: f["name"])


def download_file(file_id, dest_path):
    """Downloads a Drive file's raw content to dest_path."""
    token = _get_access_token()
    r = requests.get(
        f"https://www.googleapis.com/drive/v3/files/{file_id}",
        params={"alt": "media"},
        headers={"Authorization": f"Bearer {token}"}, timeout=120,
    )
    r.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(r.content)
    return dest_path


def upload_batch_folder(local_dir, batch_name):
    """Uploads every file in local_dir into (creating if needed) a same-named folder
    under ROOT_FOLDER_ID. Returns list of {local, id, webViewLink}."""
    folder_id = FOLDER_IDS.get(batch_name) or get_or_create_folder(batch_name, ROOT_FOLDER_ID)
    results = []
    for fname in sorted(os.listdir(local_dir)):
        path = os.path.join(local_dir, fname)
        if not os.path.isfile(path):
            continue
        mime = "text/csv" if fname.endswith(".csv") else "image/png"
        info = upload_file(path, folder_id, remote_name=fname, mime_type=mime)
        results.append({"local": fname, **info})
        print(f"  uploaded {fname} -> {info['webViewLink']}", flush=True)
    return results
