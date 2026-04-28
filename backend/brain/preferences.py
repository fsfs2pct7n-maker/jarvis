"""User preference learning — explicit + inferred."""
import json
from datetime import datetime
from backend.database import get_db


DEFAULTS = {
    "response_length":    "brief",       # brief | normal | detailed
    "response_style":     "direct",      # direct | conversational
    "email_detail":       "summary",     # summary | full
    "calendar_lookahead": "7",           # days to show by default
    "briefing_time":      "08:00",
    "focus_mode":         "off",         # on | off — suppress non-urgent alerts
}


def get_preference(key: str) -> str:
    db = get_db()
    row = db.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
    db.close()
    return row["value"] if row else DEFAULTS.get(key, "")


def set_preference(key: str, value: str, source: str = "explicit", confidence: float = 1.0):
    db = get_db()
    db.execute(
        """INSERT INTO preferences (key, value, source, confidence, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET
             value=excluded.value, source=excluded.source,
             confidence=excluded.confidence, updated_at=excluded.updated_at""",
        (key, value, source, confidence, datetime.now().isoformat()),
    )
    db.commit()
    db.close()


def get_all_preferences() -> dict:
    db = get_db()
    rows = db.execute("SELECT key, value, source, confidence FROM preferences").fetchall()
    db.close()
    prefs = dict(DEFAULTS)
    for r in rows:
        prefs[r["key"]] = r["value"]
    return prefs


def infer_response_length_pref(activity_stats: dict):
    """
    If user's most-used tone is 'urgent', lean toward briefer responses.
    If 'curious', lean toward detailed. Update with low confidence.
    """
    tone_dist = activity_stats.get("tone_distribution", {})
    if not tone_dist:
        return

    dominant = max(tone_dist, key=tone_dist.get)
    if dominant == "urgent":
        set_preference("response_length", "brief", source="inferred", confidence=0.6)
    elif dominant == "curious":
        set_preference("response_length", "detailed", source="inferred", confidence=0.6)


def build_preference_block() -> str:
    """Return a short string for injection into the system prompt."""
    prefs = get_all_preferences()
    lines = []
    if prefs.get("response_length") == "brief":
        lines.append("Prefer: very brief answers (1-2 sentences max).")
    elif prefs.get("response_length") == "detailed":
        lines.append("Prefer: more thorough explanations when asked.")
    if prefs.get("focus_mode") == "on":
        lines.append("Focus mode ON: skip proactive alerts, only respond to direct questions.")
    if not lines:
        return ""
    return "PREFERENCES:\n" + "\n".join(f"  {l}" for l in lines)
