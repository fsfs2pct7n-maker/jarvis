"""Unified search — query Gmail, Drive, Files, and Notes in parallel."""
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict


def unified_search(query: str, sources: List[str] = None) -> str:
    """
    Search across all connected services simultaneously.
    sources: list of 'gmail', 'drive', 'files', 'notes' — defaults to all.
    """
    if not query:
        return "Please provide a search query."

    all_sources = sources or ['gmail', 'drive', 'files', 'notes']
    results = {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}

        if 'gmail' in all_sources:
            futures[pool.submit(_search_gmail, query)] = 'Gmail'
        if 'drive' in all_sources:
            futures[pool.submit(_search_drive, query)] = 'Drive'
        if 'files' in all_sources:
            futures[pool.submit(_search_files, query)] = 'Files'
        if 'notes' in all_sources:
            futures[pool.submit(_search_notes, query)] = 'Notes'

        for future in as_completed(futures, timeout=10):
            source = futures[future]
            try:
                results[source] = future.result()
            except Exception as e:
                results[source] = f"Error: {e}"

    # Format combined results
    sections = []
    total_hits = 0

    for source in ['Gmail', 'Drive', 'Files', 'Notes']:
        if source in results and results[source]:
            items = results[source]
            if items:
                total_hits += len(items)
                sections.append(f"── {source} ({len(items)}) ──")
                for item in items[:5]:
                    sections.append(f"  • {item}")

    if not sections:
        return f"Nothing found for '{query}' across Gmail, Drive, Files, or Notes."

    header = f"Search results for '{query}' — {total_hits} total hits:\n"
    return header + "\n".join(sections)


def _search_gmail(query: str) -> List[str]:
    try:
        from backend.tools.gmail import get_gmail_service
        service = get_gmail_service()
        if not service:
            return []
        results = service.users().messages().list(
            userId='me', maxResults=5, q=query
        ).execute()
        messages = results.get('messages', [])
        items = []
        for msg in messages:
            details = service.users().messages().get(
                userId='me', id=msg['id'], format='metadata',
                metadataHeaders=['From', 'Subject']
            ).execute()
            headers = {h['name']: h['value'] for h in details['payload'].get('headers', [])}
            sender = headers.get('From', 'Unknown')
            if '<' in sender:
                sender = sender.split('<')[0].strip().strip('"')
            subject = headers.get('Subject', 'No subject')
            items.append(f"{subject} — from {sender}")
        return items
    except Exception:
        return []


def _search_drive(query: str) -> List[str]:
    try:
        from backend.tools.drive import get_drive_service, _friendly_type
        service = get_drive_service()
        if not service:
            return []
        safe_query = query.replace("'", "\\'")
        results = service.files().list(
            q=f"name contains '{safe_query}' and trashed=false",
            spaces='drive',
            fields='files(name,mimeType,modifiedTime)',
            pageSize=5,
        ).execute()
        files = results.get('files', [])
        return [f"{f['name']} ({_friendly_type(f.get('mimeType', ''))})" for f in files]
    except Exception:
        return []


def _search_files(query: str) -> List[str]:
    try:
        import subprocess
        result = subprocess.run(
            ['find', '/Users/owenmedley', '-iname', f'*{query}*',
             '-not', '-path', '*/.*', '-not', '-path', '*/Library/*'],
            capture_output=True, text=True, timeout=5
        )
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        # Return just filenames with short paths
        return [l.replace('/Users/owenmedley/', '~/') for l in lines[:5]]
    except Exception:
        return []


def _search_notes(query: str) -> List[str]:
    try:
        import subprocess
        script = f'''
tell application "Notes"
    set matchingNotes to every note whose name contains "{query}" or body contains "{query}"
    set results to {{}}
    repeat with n in matchingNotes
        set end of results to name of n
    end repeat
    return results
end tell
'''
        result = subprocess.run(['osascript', '-e', script],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            titles = [t.strip() for t in result.stdout.strip().split(',') if t.strip()]
            return titles[:5]
        return []
    except Exception:
        return []
