"""Routes tool calls to the appropriate tool implementations."""
import json
from typing import Dict, Any


async def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Execute a tool and return the result as a string."""
    try:
        if tool_name == "screen_vision":
            from backend.tools.screen_vision import analyze_screen
            focus = tool_input.get("focus", "full")
            return await analyze_screen(focus)

        elif tool_name == "mac_control":
            from backend.tools.mac_control import execute_mac_action
            action = tool_input.get("action", "")
            target = tool_input.get("target", "")
            return execute_mac_action(action, target)

        elif tool_name == "read_email":
            from backend.tools.gmail import handle_email_request
            return handle_email_request(
                action=tool_input.get("action", "latest"),
                query=tool_input.get("query", ""),
                limit=tool_input.get("limit", 5)
            )

        elif tool_name == "read_messages":
            from backend.tools.imessage import handle_message_request
            return handle_message_request(
                contact=tool_input.get("contact", ""),
                keyword=tool_input.get("keyword", ""),
                limit=tool_input.get("limit", 10)
            )

        elif tool_name == "read_calendar":
            from backend.tools.calendar import handle_calendar_request
            return handle_calendar_request(
                timeframe=tool_input.get("timeframe", "today"),
                query=tool_input.get("query", "")
            )

        elif tool_name == "search_files":
            from backend.tools.file_system import handle_file_request
            return handle_file_request(
                action=tool_input.get("action", "search"),
                query=tool_input.get("query", ""),
                path=tool_input.get("path", "")
            )

        elif tool_name == "web_search":
            from backend.tools.web_search import search_web
            return search_web(tool_input.get("query", ""))

        elif tool_name == "create_note":
            from backend.tools.notes import create_note
            return create_note(
                title=tool_input.get("title", "Jarvis Note"),
                content=tool_input.get("content", "")
            )

        elif tool_name == "read_notes":
            from backend.tools.notes import read_notes
            return read_notes(
                action=tool_input.get("action", "latest"),
                query=tool_input.get("query", "")
            )

        elif tool_name == "create_reminder":
            from backend.tools.tasks import create_reminder
            return create_reminder(
                title=tool_input.get("title", ""),
                due_date=tool_input.get("due_date", "")
            )

        elif tool_name == "read_reminders":
            from backend.tools.tasks import read_reminders
            return read_reminders(timeframe=tool_input.get("timeframe", "today"))

        elif tool_name == "spawn_build":
            from backend.tools.claude_code import spawn_build
            return spawn_build(
                description=tool_input.get("description", ""),
                clarifications=tool_input.get("clarifications", [])
            )

        elif tool_name == "get_memory":
            from backend.memory.engine import get_relevant_memories, search_memories
            query = tool_input.get("query", "")
            results = search_memories(query)
            if results:
                return "\n".join([f"[{r['category']}] {r['value']}" for r in results[:10]])
            return "No memories found for that query."

        # ── Phase 2 ───────────────────────────────────────────────────

        elif tool_name == "send_email":
            from backend.tools.gmail import send_email
            return send_email(
                to=tool_input.get("to", ""),
                subject=tool_input.get("subject", ""),
                body=tool_input.get("body", ""),
            )

        elif tool_name == "create_calendar_event":
            from backend.tools.calendar import create_event_from_text, create_calendar_event
            if tool_input.get("text"):
                return create_event_from_text(tool_input["text"])
            return create_calendar_event(
                title=tool_input.get("title", "Event"),
                start_time=tool_input.get("start_time", ""),
                duration_minutes=tool_input.get("duration_minutes", 60),
                description=tool_input.get("description", ""),
                attendees=tool_input.get("attendees", ""),
            )

        elif tool_name == "delete_calendar_event":
            from backend.tools.calendar import delete_calendar_event
            return delete_calendar_event(tool_input.get("event_id", ""))

        elif tool_name == "search_drive":
            from backend.tools.drive import handle_drive_request
            return handle_drive_request(
                action=tool_input.get("action", "search"),
                query=tool_input.get("query", ""),
                limit=tool_input.get("limit", 10),
            )

        elif tool_name == "unified_search":
            from backend.tools.unified_search import unified_search
            return unified_search(
                query=tool_input.get("query", ""),
                sources=tool_input.get("sources"),
            )

        elif tool_name == "manage_automation":
            from backend.tools.automation import handle_automation_request
            return handle_automation_request(
                action=tool_input.get("action", "list"),
                name=tool_input.get("name", ""),
                trigger_type=tool_input.get("trigger_type", ""),
                trigger_config=tool_input.get("trigger_config", {}),
                actions=tool_input.get("actions", []),
                rule_id=tool_input.get("rule_id", 0),
            )

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Tool error ({tool_name}): {str(e)}"
