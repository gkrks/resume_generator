"""Google Drive uploader — uploads generated resume files preserving folder structure.

Uses OAuth2 (user consent) for personal Google accounts.
First run opens a browser for auth, then saves a refresh token for future use.

Folder structure on Drive mirrors local:
  KS_Resumes/{Strong|Maybe|DontWasteTime}/{Company}/{Role}/{date}/

Setup (one-time):
  1. Google Cloud Console → enable Drive API
  2. Create OAuth2 credentials (Desktop app type) → download client_secret.json
     to config/google-client-secret.json
  3. Run: python drive_uploader.py --auth
     (opens browser, you log in, token saved to config/google-token.json)
  4. Set GOOGLE_DRIVE_FOLDER_ID in .env

For GitHub Actions (CI):
  Store the token JSON as GOOGLE_TOKEN_JSON secret.
"""

import json
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

CONFIG_DIR = Path(__file__).resolve().parent / "config"
CLIENT_SECRET_PATH = CONFIG_DIR / "google-client-secret.json"
TOKEN_PATH = CONFIG_DIR / "google-token.json"

MIME_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".json": "application/json",
    ".txt": "text/plain",
}

FOLDER_MIME = "application/vnd.google-apps.folder"


def _get_credentials() -> Credentials:
    """Load OAuth2 credentials, refreshing or prompting as needed."""
    creds = None

    # Option 1: Token JSON from env (for CI / GitHub Actions)
    token_json = os.environ.get("GOOGLE_TOKEN_JSON")
    if token_json:
        info = json.loads(token_json)
        creds = Credentials.from_authorized_user_info(info, SCOPES)

    # Option 2: Token file on disk (for local)
    if not creds and TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save refreshed token back to disk
        TOKEN_PATH.write_text(creds.to_json())
        return creds

    if creds and creds.valid:
        return creds

    # No valid credentials — need interactive auth
    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError(
            f"No credentials found. Download OAuth2 client secret from Google Cloud Console "
            f"and save to {CLIENT_SECRET_PATH}, then run: python drive_uploader.py --auth"
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0)

    # Save for next time
    TOKEN_PATH.write_text(creds.to_json())
    print(f"Token saved to {TOKEN_PATH}")

    return creds


def _get_service():
    """Build the Drive API service."""
    creds = _get_credentials()
    return build("drive", "v3", credentials=creds)


def _find_or_create_folder(service, name: str, parent_id: str) -> str:
    """Find a subfolder by name under parent_id, or create it."""
    query = (
        f"name = '{name}' and "
        f"'{parent_id}' in parents and "
        f"mimeType = '{FOLDER_MIME}' and "
        f"trashed = false"
    )
    results = service.files().list(
        q=query, fields="files(id, name)", spaces="drive"
    ).execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    metadata = {
        "name": name,
        "mimeType": FOLDER_MIME,
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def _ensure_folder_path(service, root_folder_id: str, path_parts: list[str]) -> str:
    """Create nested folder structure under root, return leaf folder ID."""
    current_id = root_folder_id
    for part in path_parts:
        current_id = _find_or_create_folder(service, part, current_id)
    return current_id


def _upload_file(service, file_path: str, folder_id: str) -> dict:
    """Upload a single file to a Drive folder."""
    name = os.path.basename(file_path)
    ext = os.path.splitext(name)[1].lower()
    mime = MIME_MAP.get(ext, "application/octet-stream")

    metadata = {"name": name, "parents": [folder_id]}
    media = MediaFileUpload(file_path, mimetype=mime)

    uploaded = service.files().create(
        body=metadata, media_body=media, fields="id, name, webViewLink"
    ).execute()

    return uploaded


def upload_output_dir(output_dir: str, root_folder_id: str | None = None) -> dict:
    """Upload all files from an output directory to Google Drive.

    Args:
        output_dir: Local path like /tmp/resumes/Strong/Stripe/Product_Manager/2026-05-08/
        root_folder_id: Google Drive folder ID for the root folder.
                        Falls back to GOOGLE_DRIVE_FOLDER_ID env var.

    Returns:
        dict with uploaded file names and their Drive links.
    """
    root_id = root_folder_id or os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not root_id:
        raise EnvironmentError("Set GOOGLE_DRIVE_FOLDER_ID env var or pass root_folder_id")

    service = _get_service()
    output_path = Path(output_dir)

    # Extract role_type/date/tier/company/role path components
    # Local path: .../SWE/9 May/Strong/Meta/Software_Engineer
    parts = output_path.parts
    role_types = {"SWE", "PM", "TPM", "APM", "PLM"}

    # Find the role_type layer (SWE/PM/TPM) — it's the top-level grouping
    role_idx = None
    for i, p in enumerate(parts):
        if p in role_types:
            role_idx = i
            break

    if role_idx is not None:
        folder_parts = list(parts[role_idx:])
    else:
        # Fallback: use last 5 components
        folder_parts = list(parts[-5:]) if len(parts) >= 5 else list(parts[-2:])

    leaf_folder_id = _ensure_folder_path(service, root_id, folder_parts)

    # Check existing files to avoid duplicates
    existing = service.files().list(
        q=f"'{leaf_folder_id}' in parents and trashed = false",
        fields="files(name)",
    ).execute()
    existing_names = {f["name"] for f in existing.get("files", [])}

    results = {}
    for file_path in output_path.iterdir():
        if file_path.is_file():
            name = file_path.name
            if name in existing_names:
                print(f"  Skipped (already exists): {name}")
                continue
            uploaded = _upload_file(service, str(file_path), leaf_folder_id)
            link = uploaded.get("webViewLink", "")
            results[uploaded["name"]] = link
            print(f"  Uploaded: {uploaded['name']} -> {link}")

    return results


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    if "--auth" in sys.argv:
        print("Authenticating with Google Drive...")
        creds = _get_credentials()
        print(f"Authenticated! Token saved to {TOKEN_PATH}")
        print(f"\nFor GitHub Actions, add this as GOOGLE_TOKEN_JSON secret:")
        print(TOKEN_PATH.read_text())
    else:
        print("Usage: python drive_uploader.py --auth")
