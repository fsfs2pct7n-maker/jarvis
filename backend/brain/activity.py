"""Activity logging and behavioral pattern analysis."""
import json
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import Optional
from backend.database import get_db


# ── Logging ────────────────────────────────────────────────────────────────

def log_interaction(
    session_id: str,
    input_text: str,
    tool_used: Optional[str],
    tool_input: Optional[dict],
    response_ms: int,
    tone: str = "neutral",
):
    """Record a single interaction to the activity log."""
    now = datetime.now()
    db = get_db()
    try:
        db.execute(
            """INSERT INTO activity_log
               (session_id, input_text, tool_used, tool_input, response_ms,
                tone, hour_of_day, day_of_week)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                input_text[:500] if input_text else "",
                tool_used,
                json.dumps(tool_input) if tool_input else None,
                response_ms,
                tone,
                now.hour,
                now.weekday(),
            ),
        )
        db.commit()
    finally:
        db.close()


# ── Analysis ───────────────────────────────────────────────────────────────

def get_activity_stats(days: int = 14) -> dict:
    """Return behavioral stats for the last N days."""
    db = get_db()
    since = (datetime.now() - timedelta(days=days)).isoformat()

    rows = db.execute(
        "SELECT * FROM activity_log WHERE created_at > ? ORDER BY created_at DESC",
        (since,),
    ).fetchall()
    db.close()

    if not rows:
        return {"total": 0, "days": days}

    tool_counts = Counter(r["tool_used"] for r in rows if r["tool_used"])
    hour_counts = Counter(r["hour_of_day"] for r in rows)
    day_counts  = Counter(r["day_of_week"] for r in rows)
    tone_counts = Counter(r["tone"] for r in rows)

    day_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    peak_hour = hour_counts.most_common(1)[0][0] if hour_counts else 0
    peak_day  = day_counts.most_common(1)[0][0] if day_counts else 0

    avg_ms = sum(r["response_ms"] for r in rows if r["response_ms"]) / max(len(rows), 1)

    return {
        "total_interactions": len(rows),
        "days_analyzed": days,
        "top_tools": [{"tool": t, "count": c} for t, c in tool_counts.most_common(5)],
        "peak_hour": peak_hour,
        "peak_hour_label": f"{peak_hour:02d}:00",
        "peak_day": day_names[peak_day],
        "hourly_distribution": dict(hour_counts),
        "tone_distribution": dict(tone_counts),
        "avg_response_ms": int(avg_ms),
        "most_requested": _most_common_topics(rows),
    }


def _most_common_topics(rows) -> list:
    """Extract recurring themes from recent inputs."""
    keywords = defaultdict(int)
    skip = {"the","a","an","is","are","my","i","to","can","you","what","how",
            "jarvis","hey","please","and","of","in","for","it","that","this","me"}
    for r in rows:
        if r["input_text"]:
            for word in r["input_text"].lower().split():
                word = word.strip(".,?!")
                if len(word) > 3 and word not in skip:
                    keywords[word] += 1
    return [w for w, _ in sorted(keywords.items(), key=lambda x: -x[1])[:8]]


def get_hourly_pattern() -> dict:
    """Get interaction frequency by hour for the last 30 days."""
    db = get_db()
    since = (datetime.now() - timedelta(days=30)).isoformat()
    rows = db.execute(
        "SELECT hour_of_day, COUNT(*) as cnt FROM activity_log WHERE created_at > ? GROUP BY hour_of_day",
        (since,),
    ).fetchall()
    db.close()
    return {r["hour_of_day"]: r["cnt"] for r in rows}


def get_tool_frequency(days: int = 7) -> list:
    """Most-used tools in the last N days."""
    db = get_db()
    since = (datetime.now() - timedelta(days=days)).isoformat()
    rows = db.execute(
        """SELECT tool_used, COUNT(*) as cnt
           FROM activity_log
           WHERE created_at > ? AND tool_used IS NOT NULL
           GROUP BY tool_used ORDER BY cnt DESC LIMIT 10""",
        (since,),
    ).fetchall()
    db.close()
    return [{"tool": r["tool_used"], "count": r["cnt"]} for r in rows]


def get_recent_commands(limit: int = 10) -> list:
    """Last N user inputs."""
    db = get_db()
    rows = db.execute(
        "SELECT input_text FROM activity_log ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    db.close()
    return [r["input_text"] for r in rows if r["input_text"]]


# ── Tone detection ─────────────────────────────────────────────────────────

def detect_tone(text: str) -> str:
    """Simple keyword-based tone classifier — no external deps."""
    text = text.lower()

    urgent_words = {"urgent","asap","immediately","now","quick","hurry","rush","critical","emergency","deadline"}
    frustrated_words = {"wrong","broken","not working","doesn't work","failed","error","fix","still","again","ugh"}
    curious_words = {"what","why","how","explain","tell me","curious","wonder","understand","learn"}
    casual_words = {"hey","cool","nice","awesome","thanks","cheers","ok","sure","yep","nope"}

    counts = {
        "urgent":     sum(1 for w in urgent_words     if w in text),
        "frustrated": sum(1 for w in frustrated_words if w in text),
        "curious":    sum(1 for w in curious_words    if w in text),
        "casual":     sum(1 for w in casual_words     if w in text),
    }

    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else "neutral"
