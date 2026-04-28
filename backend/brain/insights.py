"""Pattern detection + optimization insights engine."""
import json
from datetime import datetime, timedelta
from collections import Counter
from backend.database import get_db
from backend.brain.activity import get_activity_stats, get_hourly_pattern, get_tool_frequency


# ── Pattern Detection ──────────────────────────────────────────────────────

def detect_and_store_patterns() -> list:
    """Run pattern detection and persist any new patterns found."""
    stats = get_activity_stats(days=14)
    if stats.get("total_interactions", 0) < 5:
        return []

    found = []

    # 1. Peak usage time
    hourly = get_hourly_pattern()
    if hourly:
        peak_hour = max(hourly, key=hourly.get)
        period = _hour_to_period(peak_hour)
        desc = f"You use Jarvis most in the {period} (around {peak_hour:02d}:00)."
        _upsert_pattern("routine", "peak_usage_time", desc,
                        {"hour": peak_hour, "period": period},
                        confidence=0.8)
        found.append(desc)

    # 2. Most-used tools → suggest automations
    tools = get_tool_frequency(days=7)
    if tools:
        top = tools[0]
        if top["count"] >= 5:
            desc = f"You've used {_friendly_tool(top['tool'])} {top['count']} times this week — consider automating this."
            _upsert_pattern("workflow", "frequent_tool", desc,
                            {"tool": top["tool"], "count": top["count"]},
                            confidence=0.7)
            found.append(desc)

    # 3. High-urgency tone pattern
    tone_dist = stats.get("tone_distribution", {})
    urgent_count = tone_dist.get("urgent", 0)
    total = stats.get("total_interactions", 1)
    if urgent_count / total > 0.3:
        desc = "You often seem in a hurry. Consider setting up more automation rules to reduce manual requests."
        _upsert_pattern("preference", "high_urgency", desc,
                        {"ratio": round(urgent_count / total, 2)},
                        confidence=0.65)
        found.append(desc)

    # 4. Weekend vs weekday
    db = get_db()
    since = (datetime.now() - timedelta(days=30)).isoformat()
    day_rows = db.execute(
        "SELECT day_of_week, COUNT(*) as cnt FROM activity_log WHERE created_at > ? GROUP BY day_of_week",
        (since,)
    ).fetchall()
    db.close()
    if day_rows:
        day_counts = {r["day_of_week"]: r["cnt"] for r in day_rows}
        weekday = sum(day_counts.get(d, 0) for d in range(5))
        weekend = sum(day_counts.get(d, 0) for d in [5, 6])
        if weekend > weekday * 0.5:
            desc = "You work on weekends regularly. Jarvis will stay attentive on Saturdays and Sundays."
            _upsert_pattern("routine", "weekend_work", desc,
                            {"weekday_avg": weekday // 5, "weekend_avg": weekend // 2},
                            confidence=0.7)
            found.append(desc)

    return found


def _upsert_pattern(ptype: str, key_desc: str, description: str, data: dict, confidence: float):
    db = get_db()
    existing = db.execute(
        "SELECT id, occurrence_count FROM detected_patterns WHERE pattern_type=? AND description=?",
        (ptype, description)
    ).fetchone()
    now = datetime.now().isoformat()
    if existing:
        db.execute(
            "UPDATE detected_patterns SET occurrence_count=?, confidence=?, last_seen=? WHERE id=?",
            (existing["occurrence_count"] + 1, confidence, now, existing["id"])
        )
    else:
        db.execute(
            "INSERT INTO detected_patterns (pattern_type, description, data, confidence) VALUES (?,?,?,?)",
            (ptype, description, json.dumps(data), confidence)
        )
    db.commit()
    db.close()


def get_patterns(limit: int = 10) -> list:
    db = get_db()
    rows = db.execute(
        """SELECT pattern_type, description, confidence, occurrence_count, last_seen
           FROM detected_patterns ORDER BY confidence DESC, occurrence_count DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


# ── Optimization Insights ──────────────────────────────────────────────────

def generate_optimization_suggestions() -> list:
    """Return actionable suggestions based on usage patterns."""
    suggestions = []
    stats = get_activity_stats(days=14)

    tools = {t["tool"]: t["count"] for t in get_tool_frequency(days=7)}

    # Suggestion: automate frequent email checks
    if tools.get("read_email", 0) >= 8:
        suggestions.append(
            "You check email manually a lot — set up an automation rule to alert you when "
            "emails from key senders arrive, so you don't have to ask."
        )

    # Suggestion: recurring calendar checks
    if tools.get("read_calendar", 0) >= 6:
        suggestions.append(
            "You check your calendar frequently — I can proactively brief you each morning "
            "without you having to ask. Say 'enable daily briefing' to set it up."
        )

    # Suggestion: web search heavy user
    if tools.get("web_search", 0) >= 10:
        suggestions.append(
            "You run a lot of web searches — consider creating a research template so "
            "I can bundle related searches into one response."
        )

    # Suggestion: late-night activity
    hourly = get_hourly_pattern()
    late = sum(hourly.get(h, 0) for h in [22, 23, 0, 1])
    total = sum(hourly.values()) or 1
    if late / total > 0.25:
        suggestions.append(
            "You work late nights frequently. Focus mode (say 'enable focus mode') can "
            "suppress non-critical alerts so you can concentrate."
        )

    if not suggestions:
        suggestions.append("No major inefficiencies detected yet — keep using Jarvis and I'll spot patterns.")

    return suggestions


# ── Email Importance Scoring ───────────────────────────────────────────────

# Senders Owen cares about (bootstrapped — Jarvis will learn more)
_IMPORTANT_SENDERS = {
    "michael", "bennet", "partner", "investor", "whatnot", "stripe",
    "apple", "google", "irs", "bank", "legal", "attorney"
}

_URGENT_SUBJECTS = {
    "urgent", "asap", "immediately", "action required", "payment",
    "invoice", "deadline", "final notice", "overdue", "time sensitive"
}


def score_email(message_id: str, sender: str, subject: str) -> float:
    """Score an email 0-1 for importance. Persist the score."""
    score = 0.3  # baseline

    sender_l = sender.lower()
    subject_l = subject.lower()

    # Known important sender
    if any(kw in sender_l for kw in _IMPORTANT_SENDERS):
        score += 0.35

    # Urgent subject keywords
    hits = sum(1 for kw in _URGENT_SUBJECTS if kw in subject_l)
    score += min(hits * 0.15, 0.35)

    score = min(score, 1.0)
    action_required = 1 if score >= 0.65 else 0

    db = get_db()
    db.execute(
        """INSERT INTO email_importance (message_id, sender, subject, importance_score, action_required)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(message_id) DO UPDATE SET
             importance_score=excluded.importance_score,
             action_required=excluded.action_required,
             scored_at=CURRENT_TIMESTAMP""",
        (message_id, sender, subject, score, action_required)
    )
    db.commit()
    db.close()
    return score


def get_high_importance_emails(threshold: float = 0.65, limit: int = 5) -> list:
    db = get_db()
    rows = db.execute(
        """SELECT * FROM email_importance WHERE importance_score >= ? AND action_required = 1
           ORDER BY scored_at DESC LIMIT ?""",
        (threshold, limit)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


# ── Helpers ────────────────────────────────────────────────────────────────

def _hour_to_period(hour: int) -> str:
    if 5 <= hour < 12: return "morning"
    if 12 <= hour < 18: return "afternoon"
    if 18 <= hour < 22: return "evening"
    return "night"


def _friendly_tool(tool: str) -> str:
    labels = {
        "read_email": "Gmail", "send_email": "email sending",
        "read_calendar": "Calendar", "create_calendar_event": "event creation",
        "web_search": "web search", "mac_control": "Mac control",
        "search_files": "file search", "search_drive": "Drive search",
        "unified_search": "unified search",
    }
    return labels.get(tool, tool.replace("_", " "))
