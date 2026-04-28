"""Background Gmail monitoring — checks every 15 minutes for important emails."""
import time
import threading
from backend.database import get_db

IMPORTANT_SENDERS = ["michael", "bennet", "jaden", "dad", "father"]
IMPORTANT_KEYWORDS = ["urgent", "important", "asap", "break", "blb", "trackmycards", "payment", "invoice"]


def start_email_monitor():
    """Start background email monitoring thread."""
    t = threading.Thread(target=_monitor_loop, daemon=True)
    t.start()
    print("[EMAIL] Email monitor started.")


_consecutive_failures = 0
_MAX_FAILURES = 3  # after 3 failures, back off to 2 hours


def _monitor_loop():
    """Check emails every 15 minutes. Wait 90s on startup so server stabilizes first."""
    global _consecutive_failures
    time.sleep(90)
    while True:
        try:
            _check_emails()
            _consecutive_failures = 0
        except Exception as e:
            _consecutive_failures += 1
            print(f"[EMAIL] Monitor error (#{_consecutive_failures}): {e}")
        interval = 2 * 3600 if _consecutive_failures >= _MAX_FAILURES else 15 * 60
        time.sleep(interval)


def _check_emails():
    """Check for important new emails."""
    from backend.tools.gmail import get_gmail_service

    service = get_gmail_service()
    if not service:
        raise RuntimeError("Gmail service unavailable (token expired or missing)")

    try:
        results = service.users().messages().list(
            userId='me',
            maxResults=10,
            labelIds=['INBOX', 'UNREAD'],
            q="newer_than:20m"
        ).execute()

        messages = results.get('messages', [])
        for msg in messages:
            _process_email(service, msg['id'])

    except Exception as e:
        print(f"[EMAIL] Check failed: {e}")


def _already_seen(msg_id: str) -> bool:
    """Return True if this Gmail message ID is already in the alerts table."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM alerts WHERE source_id = ? LIMIT 1", (msg_id,))
    found = cursor.fetchone() is not None
    conn.close()
    return found


def _process_email(service, msg_id: str):
    """Check if email is important and create alert if so."""
    # Persistent deduplication — survives restarts
    if _already_seen(msg_id):
        return

    try:
        msg = service.users().messages().get(
            userId='me', id=msg_id, format='metadata',
            metadataHeaders=['From', 'Subject']
        ).execute()

        headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
        sender = headers.get('From', '').lower()
        subject = headers.get('Subject', '').lower()
        snippet = msg.get('snippet', '').lower()

        is_important = (
            any(name in sender for name in IMPORTANT_SENDERS) or
            any(kw in subject or kw in snippet for kw in IMPORTANT_KEYWORDS)
        )

        # Always record the message ID so we never process it again,
        # even if it's not important enough to alert on.
        conn = get_db()
        cursor = conn.cursor()

        if is_important:
            sender_display = headers.get('From', 'Unknown')
            if '<' in sender_display:
                sender_display = sender_display.split('<')[0].strip().strip('"')

            subject_display = headers.get('Subject', 'No subject')
            alert_text = f"Owen, new email from {sender_display} — subject: {subject_display}. {msg.get('snippet', '')[:100]}"

            cursor.execute(
                "INSERT INTO alerts (type, content, source_id) VALUES (?, ?, ?)",
                ("email", alert_text, msg_id)
            )
            print(f"[EMAIL] Logged (silent): {alert_text[:80]}")
        else:
            # Not important — insert a tombstone so we never check it again
            cursor.execute(
                "INSERT INTO alerts (type, content, source_id, delivered) VALUES (?, ?, ?, 1)",
                ("email_seen", "", msg_id)
            )

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"[EMAIL] Process error: {e}")
