"""Morning briefing generator — runs at 7am daily."""
import time
import threading
import json
from datetime import datetime, date
import pytz

TIMEZONE = "America/Indiana/Indianapolis"
WAKE_TIME = "07:00"


def start_briefing_scheduler():
    """Start background briefing scheduler."""
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()
    print("[BRIEFING] Morning briefing scheduler started.")


def _scheduler_loop():
    """Check every minute if it's time for briefing."""
    import os
    wake_time = os.getenv("WAKE_TIME", WAKE_TIME)

    while True:
        try:
            tz = pytz.timezone(TIMEZONE)
            now = datetime.now(tz)
            current_time = now.strftime("%H:%M")

            if current_time == wake_time:
                _deliver_morning_briefing()
                time.sleep(60)  # Wait a minute to not trigger twice
            else:
                time.sleep(30)

        except Exception as e:
            print(f"[BRIEFING] Scheduler error: {e}")
            time.sleep(60)


def generate_briefing() -> str:
    """Generate and return the morning briefing text."""
    from backend.brain.claude import get_brain
    from backend.tools.web_search import get_weather
    from backend.tools.gmail import get_recent_emails_for_briefing
    from backend.tools.imessage import get_messages_for_briefing
    from backend.tools.calendar import get_events_for_briefing
    from backend.database import get_db

    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    today = now.strftime("%A, %B %d, %Y")

    # Gather all data
    briefing_data = {
        "date": today,
        "time": now.strftime("%I:%M %p"),
        "day_of_week": now.strftime("%A"),
        "weather": "Unavailable",
        "calendar": [],
        "emails": [],
        "messages": []
    }

    # Weather
    try:
        briefing_data["weather"] = get_weather("Lafayette, Indiana")
    except Exception:
        pass

    # Calendar
    try:
        events = get_events_for_briefing()
        briefing_data["calendar"] = [
            {
                "time": e['start'].get('dateTime', e['start'].get('date', '')),
                "title": e.get('summary', 'Event')
            }
            for e in events
        ]
    except Exception:
        pass

    # Emails
    try:
        briefing_data["emails"] = get_recent_emails_for_briefing(5)
    except Exception:
        pass

    # Messages
    try:
        msgs = get_messages_for_briefing(hours=8)
        briefing_data["messages"] = [
            {"from": m.get("display_name") or m.get("handle"), "text": m.get("text", "")[:100]}
            for m in msgs[:5]
        ]
    except Exception:
        pass

    # Generate with Claude Sonnet
    brain = get_brain()
    briefing_text = brain.generate_briefing(briefing_data)

    # Save to database
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO briefings (date, content) VALUES (?, ?)",
        (today, json.dumps({"text": briefing_text, "data": briefing_data}))
    )
    db.commit()
    db.close()

    return briefing_text


def _deliver_morning_briefing():
    """Generate and deliver the morning briefing."""
    from backend.database import get_db

    today = date.today().strftime("%A, %B %d, %Y")

    # Check if already delivered today
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM briefings WHERE date = ?", (today,))
    if cursor.fetchone():
        conn.close()
        return
    conn.close()

    print(f"[BRIEFING] Generating morning briefing for {today}...")

    try:
        text = generate_briefing()
        print(f"[BRIEFING] Generated {len(text)} char briefing.")

        # Deliver via TTS
        from backend.audio.text_to_speech import speak
        speak(text, blocking=False)

        # Broadcast to UI
        try:
            from backend.app import broadcast_message
            import asyncio
            loop = asyncio.new_event_loop()
            loop.run_until_complete(broadcast_message({
                "type": "briefing",
                "content": text
            }))
            loop.close()
        except Exception:
            pass

    except Exception as e:
        print(f"[BRIEFING] Delivery failed: {e}")
