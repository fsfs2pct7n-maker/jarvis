"""Google Drive integration."""
import pickle
from pathlib import Path
from typing import List, Dict, Optional

TOKEN_PATH = Path(__file__).parent.parent.parent / "gmail_token.pickle"


def get_drive_service():
    """Get authenticated Google Drive service."""
    try:
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        if not TOKEN_PATH.exists():
            return None

        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, 'wb') as token:
                pickle.dump(creds, token)

        if not creds or not creds.valid:
            return None

        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"[DRIVE] Service error: {e}")
        return None


def handle_drive_request(action: str = "search", query: str = "",
                          limit: int = 10) -> str:
    """Handle Drive requests."""
    service = get_drive_service()
    if not service:
        return "Google Drive not connected. Visit http://localhost:8000/auth/google to connect."

    try:
        if action == "search":
            return search_files(service, query, limit)
        elif action == "recent":
            return get_recent_files(service, limit)
        else:
            return "Unknown Drive action."
    except Exception as e:
        return f"Drive error: {e}"


def search_files(service, query: str, limit: int = 10) -> str:
    if not query:
        return "Please provide a search query."

    # Escape single quotes in query
    safe_query = query.replace("'", "\\'")
    results = service.files().list(
        q=f"name contains '{safe_query}' and trashed=false",
        spaces='drive',
        fields='files(id,name,mimeType,modifiedTime,webViewLink,size)',
        pageSize=limit,
        orderBy='modifiedTime desc',
    ).execute()

    files = results.get('files', [])
    if not files:
        return f"No files found matching '{query}'."

    lines = [f"Found {len(files)} file(s) matching '{query}':"]
    for f in files:
        mime = _friendly_type(f.get('mimeType', ''))
        modified = f.get('modifiedTime', '')[:10]
        lines.append(f"• {f['name']} ({mime}) — modified {modified}")
    return "\n".join(lines)


def get_recent_files(service, limit: int = 10) -> str:
    results = service.files().list(
        spaces='drive',
        fields='files(id,name,mimeType,modifiedTime)',
        orderBy='modifiedTime desc',
        pageSize=limit,
    ).execute()

    files = results.get('files', [])
    if not files:
        return "No recent files found."

    lines = ["Recent Drive files:"]
    for f in files:
        mime = _friendly_type(f.get('mimeType', ''))
        modified = f.get('modifiedTime', '')[:10]
        lines.append(f"• {f['name']} ({mime}) — {modified}")
    return "\n".join(lines)


def get_recent_files_raw(limit: int = 10) -> List[Dict]:
    """Return raw file dicts for use by other modules."""
    service = get_drive_service()
    if not service:
        return []
    try:
        results = service.files().list(
            spaces='drive',
            fields='files(id,name,mimeType,modifiedTime,webViewLink)',
            orderBy='modifiedTime desc',
            pageSize=limit,
        ).execute()
        return results.get('files', [])
    except Exception:
        return []


def _friendly_type(mime: str) -> str:
    types = {
        'application/vnd.google-apps.document': 'Doc',
        'application/vnd.google-apps.spreadsheet': 'Sheet',
        'application/vnd.google-apps.presentation': 'Slides',
        'application/vnd.google-apps.folder': 'Folder',
        'application/pdf': 'PDF',
        'image/jpeg': 'Image',
        'image/png': 'Image',
    }
    return types.get(mime, mime.split('/')[-1] if '/' in mime else 'File')
