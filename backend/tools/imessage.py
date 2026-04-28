"""iMessage reader — reads directly from Mac's Messages SQLite database."""
import sqlite3
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

CHAT_DB_PATH = Path.home() / "Library/Messages/chat.db"
# Apple's epoch starts 2001-01-01, not 1970-01-01
APPLE_EPOCH_OFFSET = 978307200


def get_imessage_db():
    """Get connection to iMessage database."""
    if not CHAT_DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(str(CHAT_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"[IMESSAGE] DB error: {e}")
        return None


def handle_message_request(contact: str = "", keyword: str = "", limit: int = 10) -> str:
    """Handle iMessage request."""
    conn = get_imessage_db()

    if not conn:
        return "iMessage database not accessible. Grant Full Disk Access to Terminal in System Settings > Privacy & Security > Full Disk Access."

    try:
        if contact:
            return _get_messages_from_contact(conn, contact, limit)
        elif keyword:
            return _search_messages_by_keyword(conn, keyword, limit)
        else:
            return _get_recent_messages(conn, limit)
    except Exception as e:
        return f"iMessage error: {e}"
    finally:
        conn.close()


def _get_messages_from_contact(conn, contact: str, limit: int = 10) -> str:
    """Get recent messages from a specific contact."""
    cursor = conn.cursor()

    # Search for contact by name in address book or handle
    cursor.execute("""
        SELECT DISTINCT
            m.text,
            m.is_from_me,
            datetime(m.date/1000000000 + 978307200, 'unixepoch', 'localtime') as sent_at,
            h.id as phone_or_email,
            c.display_name
        FROM message m
        JOIN handle h ON m.handle_id = h.rowid
        LEFT JOIN chat_handle_join chj ON h.rowid = chj.handle_id
        LEFT JOIN chat c ON chj.chat_id = c.rowid
        WHERE (
            LOWER(h.id) LIKE ? OR
            LOWER(c.display_name) LIKE ?
        )
        AND m.text IS NOT NULL
        AND m.text != ''
        ORDER BY m.date DESC
        LIMIT ?
    """, (f"%{contact.lower()}%", f"%{contact.lower()}%", limit))

    rows = cursor.fetchall()

    if not rows:
        return f"No messages found from '{contact}'. Make sure the name matches how they appear in Messages."

    messages = []
    for row in rows:
        direction = "You" if row["is_from_me"] else (row["display_name"] or contact)
        time = row["sent_at"]
        text = row["text"]
        messages.append(f"[{time}] {direction}: {text}")

    # Return in chronological order
    messages.reverse()
    return f"Messages with {contact}:\n\n" + "\n".join(messages)


def _search_messages_by_keyword(conn, keyword: str, limit: int = 10) -> str:
    """Search messages by keyword."""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            m.text,
            m.is_from_me,
            datetime(m.date/1000000000 + 978307200, 'unixepoch', 'localtime') as sent_at,
            h.id as handle,
            c.display_name
        FROM message m
        JOIN handle h ON m.handle_id = h.rowid
        LEFT JOIN chat_handle_join chj ON h.rowid = chj.handle_id
        LEFT JOIN chat c ON chj.chat_id = c.rowid
        WHERE LOWER(m.text) LIKE ?
        AND m.text IS NOT NULL
        ORDER BY m.date DESC
        LIMIT ?
    """, (f"%{keyword.lower()}%", limit))

    rows = cursor.fetchall()

    if not rows:
        return f"No messages found containing '{keyword}'."

    messages = []
    for row in rows:
        direction = "You" if row["is_from_me"] else (row["display_name"] or row["handle"])
        time = row["sent_at"]
        messages.append(f"[{time}] {direction}: {row['text']}")

    messages.reverse()
    return f"Messages containing '{keyword}':\n\n" + "\n".join(messages)


def _get_recent_messages(conn, limit: int = 10) -> str:
    """Get most recent messages across all chats."""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            m.text,
            m.is_from_me,
            datetime(m.date/1000000000 + 978307200, 'unixepoch', 'localtime') as sent_at,
            h.id as handle,
            c.display_name
        FROM message m
        JOIN handle h ON m.handle_id = h.rowid
        LEFT JOIN chat_handle_join chj ON h.rowid = chj.handle_id
        LEFT JOIN chat c ON chj.chat_id = c.rowid
        WHERE m.text IS NOT NULL AND m.text != ''
        ORDER BY m.date DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()

    if not rows:
        return "No recent messages found."

    messages = []
    for row in rows:
        direction = "You" if row["is_from_me"] else (row["display_name"] or row["handle"])
        time = row["sent_at"]
        messages.append(f"[{time}] {direction}: {row['text']}")

    messages.reverse()
    return "Recent messages:\n\n" + "\n".join(messages)


def get_messages_for_briefing(hours: int = 12) -> List[Dict]:
    """Get messages from the last N hours for briefing."""
    conn = get_imessage_db()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        # Convert hours to Apple epoch time
        import time
        cutoff = (time.time() - (hours * 3600) - APPLE_EPOCH_OFFSET) * 1e9

        cursor.execute("""
            SELECT
                m.text,
                m.is_from_me,
                datetime(m.date/1000000000 + 978307200, 'unixepoch', 'localtime') as sent_at,
                h.id as handle,
                c.display_name
            FROM message m
            JOIN handle h ON m.handle_id = h.rowid
            LEFT JOIN chat_handle_join chj ON h.rowid = chj.handle_id
            LEFT JOIN chat c ON chj.chat_id = c.rowid
            WHERE m.date > ?
            AND m.text IS NOT NULL
            AND m.is_from_me = 0
            ORDER BY m.date DESC
            LIMIT 20
        """, (cutoff,))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []
    finally:
        conn.close()
