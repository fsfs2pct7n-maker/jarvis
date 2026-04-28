"""Proactive alert engine — delivers alerts to Owen proactively."""
import time
import threading
from datetime import datetime, timedelta
from backend.database import get_db

MAX_ALERTS_PER_HOUR = 3
_alerts_this_hour = []
_alert_lock = threading.Lock()


def start_proactive_engine():
    """Start the proactive alert delivery thread."""
    t = threading.Thread(target=_proactive_loop, daemon=True)
    t.start()
    print("[PROACTIVE] Proactive engine started.")


def _proactive_loop():
    """Check for undelivered alerts every 2 minutes. Wait 45s on startup."""
    time.sleep(45)
    while True:
        try:
            _deliver_pending_alerts()
            _reset_hourly_counter()
        except Exception as e:
            print(f"[PROACTIVE] Error: {e}")
        time.sleep(2 * 60)


def _deliver_pending_alerts():
    """Mark pending alerts as delivered. Email alerts are always silent — Owen
    asks for emails explicitly. Only non-email alert types are shown in the UI."""
    conn = get_db()
    cursor = conn.cursor()

    # Fetch undelivered alerts (email type is silently marked delivered)
    cursor.execute("""
        SELECT id, type, content FROM alerts
        WHERE delivered = 0
        ORDER BY created_at ASC
        LIMIT 5
    """)

    alerts = cursor.fetchall()

    for alert in alerts:
        alert_type = alert["type"]

        if alert_type == "email":
            # Email alerts are NEVER announced — silently mark delivered
            cursor.execute("UPDATE alerts SET delivered = 1 WHERE id = ?", (alert["id"],))
            print(f"[PROACTIVE] Email alert logged silently (ask Jarvis to read it)")
        else:
            # Non-email alerts (tasks, reminders, etc.) — rate-limited UI broadcast only, no TTS
            with _alert_lock:
                if len(_alerts_this_hour) >= MAX_ALERTS_PER_HOUR:
                    break

            cursor.execute("UPDATE alerts SET delivered = 1 WHERE id = ?", (alert["id"],))

            try:
                from backend.app import broadcast_message
                import asyncio
                loop = asyncio.new_event_loop()
                loop.run_until_complete(broadcast_message({
                    "type": "proactive_alert",
                    "content": alert["content"]
                }))
                loop.close()
            except Exception:
                pass

            with _alert_lock:
                _alerts_this_hour.append(datetime.now())

    conn.commit()
    conn.close()


def _reset_hourly_counter():
    """Reset the hourly alert counter."""
    cutoff = datetime.now() - timedelta(hours=1)
    with _alert_lock:
        _alerts_this_hour[:] = [t for t in _alerts_this_hour if t > cutoff]


def queue_alert(alert_type: str, content: str):
    """Queue an alert for delivery."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO alerts (type, content) VALUES (?, ?)",
        (alert_type, content)
    )
    conn.commit()
    conn.close()
