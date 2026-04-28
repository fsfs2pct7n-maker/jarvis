"""Gmail integration via Google API."""
import os
import base64
import pickle
import email.mime.text
import email.mime.multipart
from pathlib import Path
from typing import List, Dict, Optional


TOKEN_PATH = Path(__file__).parent.parent.parent / "gmail_token.pickle"

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/drive.readonly',
]


def get_gmail_service():
    """Get authenticated Gmail service."""
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

        return build('gmail', 'v1', credentials=creds)
    except Exception as e:
        print(f"[GMAIL] Service error: {e}")
        return None


def handle_email_request(action: str, query: str = "", limit: int = 5,
                          to: str = "", subject: str = "", body: str = "",
                          message_id: str = "") -> str:
    """Handle all email requests."""
    if action == "send":
        return send_email(to=to, subject=subject, body=body)

    service = get_gmail_service()
    if not service:
        client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        if not client_id:
            return "Gmail not connected. Google OAuth credentials not configured."
        return "Gmail not connected. Visit http://localhost:8000/auth/google to connect."

    try:
        if action == "latest":
            return _get_latest_emails(service, limit)
        elif action == "search":
            return _search_emails(service, query, limit)
        elif action == "unread_summary":
            return _get_unread_summary(service, limit)
        elif action == "read":
            return _get_full_email(service, message_id or query)
        elif action == "mark_read":
            return _mark_as_read(service, message_id)
        elif action == "unread_count":
            count = _get_unread_count(service)
            return f"You have {count} unread emails."
        else:
            return "Unknown email action."
    except Exception as e:
        return f"Gmail error: {e}"


def send_email(to: str, subject: str, body: str) -> str:
    """Send an email via Gmail."""
    service = get_gmail_service()
    if not service:
        return "Gmail not connected. Visit http://localhost:8000/auth/google to connect."

    if not to or not subject or not body:
        return "Missing required fields: to, subject, body."

    try:
        msg = email.mime.text.MIMEText(body)
        msg['to'] = to
        msg['subject'] = subject

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        return f"Email sent to {to} with subject '{subject}'."
    except Exception as e:
        return f"Failed to send email: {e}"


def _get_latest_emails(service, limit: int = 5) -> str:
    results = service.users().messages().list(
        userId='me', maxResults=limit, labelIds=['INBOX']
    ).execute()
    messages = results.get('messages', [])
    if not messages:
        return "No emails in inbox."
    summaries = [_get_email_details(service, m['id']) for m in messages]
    return "\n\n".join(s for s in summaries if s)


def _search_emails(service, query: str, limit: int = 5) -> str:
    results = service.users().messages().list(
        userId='me', maxResults=limit, q=query
    ).execute()
    messages = results.get('messages', [])
    if not messages:
        return f"No emails found matching '{query}'."
    summaries = [_get_email_details(service, m['id']) for m in messages]
    return "\n\n".join(s for s in summaries if s)


def _get_unread_summary(service, limit: int = 10) -> str:
    results = service.users().messages().list(
        userId='me', maxResults=limit, labelIds=['INBOX', 'UNREAD']
    ).execute()
    messages = results.get('messages', [])
    if not messages:
        return "No unread emails."
    count = results.get('resultSizeEstimate', len(messages))
    summaries = [_get_email_details(service, m['id']) for m in messages[:5]]
    result = f"You have approximately {count} unread emails. Here are the most recent:\n\n"
    return result + "\n\n".join(s for s in summaries if s)


def _get_full_email(service, query: str) -> str:
    """Get a specific email with full body content."""
    # If query looks like an ID, fetch directly; otherwise search
    if len(query) > 20 and ' ' not in query:
        msg_id = query
    else:
        results = service.users().messages().list(
            userId='me', maxResults=1, q=query
        ).execute()
        messages = results.get('messages', [])
        if not messages:
            return f"No email found matching '{query}'."
        msg_id = messages[0]['id']

    try:
        msg = service.users().messages().get(
            userId='me', id=msg_id, format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
        body = _extract_body(msg['payload'])

        sender = headers.get('From', 'Unknown')
        if '<' in sender:
            sender = sender.split('<')[0].strip().strip('"')

        return (
            f"From: {sender}\n"
            f"Subject: {headers.get('Subject', 'No subject')}\n"
            f"Date: {headers.get('Date', '')}\n\n"
            f"{body[:2000]}"
        )
    except Exception as e:
        return f"Could not read email: {e}"


def _extract_body(payload) -> str:
    """Recursively extract plain text body from a Gmail message payload."""
    if payload.get('mimeType') == 'text/plain':
        data = payload.get('body', {}).get('data', '')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')

    if 'parts' in payload:
        for part in payload['parts']:
            result = _extract_body(part)
            if result:
                return result

    # Fallback: try body data directly
    data = payload.get('body', {}).get('data', '')
    if data:
        return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')

    return ""


def _mark_as_read(service, message_id: str) -> str:
    if not message_id:
        return "No message ID provided."
    try:
        service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
        return "Marked as read."
    except Exception as e:
        return f"Could not mark as read: {e}"


def _get_unread_count(service) -> int:
    try:
        results = service.users().messages().list(
            userId='me', q='is:unread', maxResults=1
        ).execute()
        return results.get('resultSizeEstimate', 0)
    except Exception:
        return 0


def _get_email_details(service, msg_id: str) -> Optional[str]:
    try:
        msg = service.users().messages().get(
            userId='me', id=msg_id, format='metadata',
            metadataHeaders=['From', 'Subject', 'Date']
        ).execute()
        headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
        sender = headers.get('From', 'Unknown')
        if '<' in sender:
            name_part = sender.split('<')[0].strip().strip('"')
            sender = name_part if name_part else sender
        return (
            f"From: {sender}\n"
            f"Subject: {headers.get('Subject', 'No subject')}\n"
            f"Preview: {msg.get('snippet', '')}"
        )
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
