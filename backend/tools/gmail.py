"""Gmail integration via Google API."""
import os
import json
import pickle
from pathlib import Path
from typing import List, Dict, Optional


TOKEN_PATH = Path(__file__).parent.parent.parent / "gmail_token.pickle"
CREDENTIALS_PATH = Path(__file__).parent.parent.parent / "google_credentials.json"
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events'
]


def get_gmail_service():
    """Get authenticated Gmail service."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = None
        if TOKEN_PATH.exists():
            with open(TOKEN_PATH, 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                return None  # Need OAuth flow

        return build('gmail', 'v1', credentials=creds)
    except Exception as e:
        print(f"[GMAIL] Service error: {e}")
        return None


def handle_email_request(action: str, query: str = "", limit: int = 5) -> str:
    """Handle email requests."""
    service = get_gmail_service()

    if not service:
        client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        if not client_id:
            return "Gmail not connected. Google OAuth credentials not configured yet."
        return "Gmail not connected. Visit http://localhost:8000/auth/google to connect your account."

    try:
        if action == "latest":
            return _get_latest_emails(service, limit)
        elif action == "search":
            return _search_emails(service, query, limit)
        elif action == "unread_summary":
            return _get_unread_summary(service, limit)
        else:
            return "Unknown email action."
    except Exception as e:
        return f"Gmail error: {e}"


def _get_latest_emails(service, limit: int = 5) -> str:
    """Get the latest emails."""
    results = service.users().messages().list(
        userId='me', maxResults=limit, labelIds=['INBOX']
    ).execute()

    messages = results.get('messages', [])
    if not messages:
        return "No emails in inbox."

    summaries = []
    for msg in messages:
        details = _get_email_details(service, msg['id'])
        if details:
            summaries.append(details)

    return "\n\n".join(summaries)


def _search_emails(service, query: str, limit: int = 5) -> str:
    """Search emails by query."""
    results = service.users().messages().list(
        userId='me', maxResults=limit, q=query
    ).execute()

    messages = results.get('messages', [])
    if not messages:
        return f"No emails found matching '{query}'."

    summaries = []
    for msg in messages:
        details = _get_email_details(service, msg['id'])
        if details:
            summaries.append(details)

    return "\n\n".join(summaries)


def _get_unread_summary(service, limit: int = 10) -> str:
    """Get unread email summary."""
    results = service.users().messages().list(
        userId='me', maxResults=limit, labelIds=['INBOX', 'UNREAD']
    ).execute()

    messages = results.get('messages', [])
    if not messages:
        return "No unread emails."

    count = results.get('resultSizeEstimate', len(messages))
    summaries = []
    for msg in messages[:5]:  # Summarize first 5
        details = _get_email_details(service, msg['id'])
        if details:
            summaries.append(details)

    result = f"You have approximately {count} unread emails. Here are the most recent:\n\n"
    result += "\n\n".join(summaries)
    return result


def _get_email_details(service, msg_id: str) -> Optional[str]:
    """Get email details as formatted string."""
    try:
        msg = service.users().messages().get(
            userId='me', id=msg_id, format='metadata',
            metadataHeaders=['From', 'Subject', 'Date']
        ).execute()

        headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
        snippet = msg.get('snippet', '')

        sender = headers.get('From', 'Unknown')
        # Clean up sender format
        if '<' in sender:
            name_part = sender.split('<')[0].strip().strip('"')
            sender = name_part if name_part else sender

        subject = headers.get('Subject', 'No subject')
        date = headers.get('Date', '')

        return f"From: {sender}\nSubject: {subject}\nPreview: {snippet}"
    except Exception:
        return None


def get_recent_emails_for_briefing(limit: int = 5) -> List[Dict]:
    """Get emails for morning briefing."""
    service = get_gmail_service()
    if not service:
        return []

    try:
        results = service.users().messages().list(
            userId='me', maxResults=limit, labelIds=['INBOX', 'UNREAD']
        ).execute()

        emails = []
        for msg in results.get('messages', []):
            details = service.users().messages().get(
                userId='me', id=msg['id'], format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']
            ).execute()

            headers = {h['name']: h['value'] for h in details['payload'].get('headers', [])}
            emails.append({
                'from': headers.get('From', 'Unknown'),
                'subject': headers.get('Subject', 'No subject'),
                'snippet': details.get('snippet', '')
            })

        return emails
    except Exception:
        return []
