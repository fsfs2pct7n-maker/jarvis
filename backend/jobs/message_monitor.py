"""Background iMessage monitoring — checks every 5 minutes for important messages."""
import time
import threading
from backend.database import get_db

IMPORTANT_CONTACTS = ["michael", "bennet", "jaden", "dad"]
IMPORTANT_KEYWORDS = ["urgent", "asap", "break", "blb", "tonight", "help", "emergency"]

_last_message_date = None
_consecutive_failures = 0
_MAX_FAILURES = 3  # after 3 failures, back off to 2 hours (permission denied is permanent)


def start_message_monitor():
    """Start background message monitoring thread."""
    t = threading.Thread(target=_monitor_loop, daemon=True)
    t.start()
    print("[IMSG] Message monitor started.")


def _monitor_loop():
    """Check messages every 5 minutes. Wait 60s on startup so server stabilizes first."""
    global _consecutive_failures
    time.sleep(60)
    while True:
        try:
            _check_messages()
            _consecutive_failures = 0
        except Exception as e:
            _consecutive_failures += 1
            if _consecutive_failures <= _MAX_FAILURES:
                print(f"[IMSG] Monitor error (#{_consecutive_failures}): {e}")
            elif _consecutive_failures == _MAX_FAILURES + 1:
                print("[IMSG] Persistent error — backing off to 2-hour interval. Grant Full Disk Access to fix.")
        interval = 2 * 3600 if _consecutive_failures >= _MAX_FAILURES else 5 * 60
        time.sleep(interval)


def _check_messages():
    """Check for important new messages."""
    global _last_message_date

    from backend.tools.imessage import get_imessage_db

    conn = get_imessage_db()
    if not conn:
        return

    try:
        import time as time_module
        current_time = time_module.time()

        # Check messages in last 6 minutes (slightly more than our 5 min interval)
        cutoff_epoch = (current_time - 360) - 978307200  # Convert to Apple epoch
        cutoff_ns = cutoff_epoch * 1e9

        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                m.text,
                m.date,
                h.id as handle,
                c.display_name
            FROM message m
            JOIN handle h ON m.handle_id = h.rowid
            LEFT JOIN chat_handle_join chj ON h.rowid = chj.handle_id
            LEFT JOIN chat c ON chj.chat_id = c.rowid
            WHERE m.date > ?
            AND m.is_from_me = 0
            AND m.text IS NOT NULL
            ORDER BY m.date DESC
        """, (cutoff_ns,))

        rows = cursor.fetchall()

        for row in rows:
            sender = (row["display_name"] or row["handle"] or "").lower()
            text = (row["text"] or "").lower()
            msg_date = row["date"]

            if _last_message_date and msg_date <= _last_message_date:
                continue

            is_important = (
                any(name in sender for name in IMPORTANT_CONTACTS) or
                any(kw in text for kw in IMPORTANT_KEYWORDS)
            )

            if is_important:
                sender_display = row["display_name"] or row["handle"]
                alert_text = f"Owen, message from {sender_display}: {row['text'][:150]}"

                db_conn = get_db()
                db_cursor = db_conn.cursor()
                db_cursor.execute(
                    "INSERT INTO alerts (type, content) VALUES (?, ?)",
                    ("message", alert_text)
                )
                db_conn.commit()
                db_conn.close()

                print(f"[IMSG] Alert: {alert_text[:80]}")

        if rows:
            _last_message_date = rows[0]["date"]

    except Exception as e:
        print(f"[IMSG] Check error: {e}")
    finally:
        conn.close()
