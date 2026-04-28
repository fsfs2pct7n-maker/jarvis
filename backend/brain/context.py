"""Live session context — active app, recent topics, tone, current focus."""
import subprocess
import time
from datetime import datetime
from collections import deque


class SessionContext:
    """Singleton that tracks the current session state."""

    def __init__(self, window: int = 10):
        self._recent_tools: deque[str] = deque(maxlen=window)
        self._recent_topics: deque[str] = deque(maxlen=window)
        self._current_tone: str = "neutral"
        self._tone_history: deque[str] = deque(maxlen=5)
        self._active_app: str = "unknown"
        self._app_last_checked: float = 0
        self._session_start: datetime = datetime.now()
        self._interaction_count: int = 0

    # ── Update methods ─────────────────────────────────────────────────────

    def record_tool(self, tool: str):
        if tool:
            self._recent_tools.append(tool)

    def record_topic(self, text: str):
        """Extract and store the main topic from user input."""
        if not text:
            return
        # Simple noun extraction: words > 4 chars, not stop words
        stop = {"jarvis","please","thanks","could","would","should","about","there"}
        words = [w.strip(".,?!") for w in text.lower().split() if len(w) > 4 and w not in stop]
        if words:
            self._recent_topics.append(" ".join(words[:3]))
        self._interaction_count += 1

    def update_tone(self, tone: str):
        self._current_tone = tone
        self._tone_history.append(tone)

    # ── Active app (cached 30s) ────────────────────────────────────────────

    def get_active_app(self) -> str:
        now = time.time()
        if now - self._app_last_checked < 30:
            return self._active_app
        try:
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of first application process whose frontmost is true'],
                capture_output=True, text=True, timeout=3
            )
            self._active_app = result.stdout.strip() or "unknown"
        except Exception:
            pass
        self._app_last_checked = now
        return self._active_app

    # ── Snapshot for system prompt injection ──────────────────────────────

    def build_context_block(self) -> str:
        """Return a compact context string to inject into Jarvis's system prompt."""
        parts = []

        # Active app
        app = self.get_active_app()
        if app and app != "unknown":
            parts.append(f"Active app: {app}")

        # Recent tools used this session
        tools = list(self._recent_tools)
        if tools:
            unique = list(dict.fromkeys(reversed(tools)))[:4]  # last 4, deduped
            parts.append(f"Recent tools: {', '.join(unique)}")

        # Recent topics
        topics = list(self._recent_topics)
        if topics:
            parts.append(f"Recent topics: {', '.join(topics[-3:])}")

        # Dominant tone
        if self._tone_history:
            dominant = max(set(self._tone_history), key=list(self._tone_history).count)
            if dominant != "neutral":
                parts.append(f"User tone: {dominant}")

        # Session stats
        hour = datetime.now().hour
        period = "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening" if 18 <= hour < 22 else "night"
        parts.append(f"Session: {self._interaction_count} turns this {period}")

        if not parts:
            return ""
        return "CURRENT CONTEXT:\n" + "\n".join(f"  {p}" for p in parts)

    def tone_instruction(self) -> str:
        """Return a tone adaptation hint for Claude."""
        tone = self._current_tone
        if tone == "urgent":
            return "Owen seems in a hurry — be extra brief, lead with the answer."
        if tone == "frustrated":
            return "Owen seems frustrated — acknowledge the issue first, be direct about the fix."
        if tone == "curious":
            return "Owen wants to understand — a bit more explanation is welcome."
        if tone == "casual":
            return "Relaxed conversation — match the casual energy."
        return ""


# Global singleton — imported everywhere
_ctx = SessionContext()

def get_context() -> SessionContext:
    return _ctx
