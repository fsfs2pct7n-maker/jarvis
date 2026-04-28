"""Memory engine — save, retrieve, search, and update memories."""
import json
from typing import List, Optional, Dict
from backend.database import get_db


def save_memory(category: str, key: str, value: str, confidence: float = 1.0, source: str = "conversation"):
    """Save or update a memory."""
    conn = get_db()
    cursor = conn.cursor()

    # Check if key already exists
    cursor.execute("SELECT id FROM memories WHERE key = ? AND category = ?", (key, category))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE memories SET value = ?, confidence = ?, updated_at = CURRENT_TIMESTAMP
            WHERE key = ? AND category = ?
        """, (value, confidence, key, category))
    else:
        cursor.execute("""
            INSERT INTO memories (category, key, value, confidence, source)
            VALUES (?, ?, ?, ?, ?)
        """, (category, key, value, confidence, source))

    conn.commit()
    conn.close()


def get_relevant_memories(topic: str, limit: int = 20) -> str:
    """Get the most relevant memories for a given topic."""
    conn = get_db()
    cursor = conn.cursor()

    # Simple keyword matching — split topic into words and search
    words = [w.lower() for w in topic.split() if len(w) > 3]

    if not words:
        # Return top memories by times_referenced
        cursor.execute("""
            SELECT category, key, value FROM memories
            ORDER BY times_referenced DESC, confidence DESC
            LIMIT ?
        """, (limit,))
    else:
        # Search for memories containing topic keywords
        placeholders = " OR ".join(["(LOWER(value) LIKE ? OR LOWER(key) LIKE ?)" for _ in words])
        params = []
        for word in words:
            params.extend([f"%{word}%", f"%{word}%"])
        params.append(limit)

        cursor.execute(f"""
            SELECT category, key, value FROM memories
            WHERE {placeholders}
            ORDER BY confidence DESC, times_referenced DESC
            LIMIT ?
        """, params)

    rows = cursor.fetchall()

    # Also bump times_referenced
    for row in rows:
        cursor.execute("""
            UPDATE memories SET times_referenced = times_referenced + 1
            WHERE key = ? AND category = ?
        """, (row["key"], row["category"]))

    conn.commit()
    conn.close()

    if not rows:
        return ""

    lines = []
    for row in rows:
        lines.append(f"[{row['category']}] {row['value']}")

    return "\n".join(lines)


def get_all_memories() -> List[Dict]:
    """Get all memories as a list of dicts."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM memories ORDER BY category, key")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def search_memories(query: str) -> List[Dict]:
    """Search memories by text."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM memories
        WHERE LOWER(value) LIKE ? OR LOWER(key) LIKE ?
        ORDER BY confidence DESC
    """, (f"%{query.lower()}%", f"%{query.lower()}%"))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_conversation(session_id: str, role: str, content: str, model_used: str = None, tools_used: list = None):
    """Save a conversation turn."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO conversations (session_id, role, content, model_used, tools_used)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, role, content, model_used, json.dumps(tools_used) if tools_used else None))
    conn.commit()
    conn.close()


def get_conversation_history(session_id: str, limit: int = 20) -> List[Dict]:
    """Get recent conversation history for a session."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, content FROM conversations
        WHERE session_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (session_id, limit))
    rows = cursor.fetchall()
    conn.close()
    # Return in chronological order
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
