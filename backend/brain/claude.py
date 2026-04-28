"""Claude API wrapper — Haiku for fast talk, Sonnet for heavy lifting."""
import os
import json
from typing import List, Dict, Optional, AsyncGenerator
import anthropic

# Tool definitions for Claude
JARVIS_TOOLS = [
    {
        "name": "screen_vision",
        "description": "Take a screenshot of Owen's current screen and analyze what's visible. Use when Owen says 'look at this', 'what's on my screen', 'I have an error', or similar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "What to focus on: 'full' for full screen, 'active' for active window, 'error' for error messages"
                }
            },
            "required": []
        }
    },
    {
        "name": "mac_control",
        "description": "Control Owen's Mac using AppleScript. Open apps, navigate Chrome, run terminal commands, adjust volume, control system.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "What to do: open_app, open_url, run_command, set_volume, open_terminal, run_terminal_command, take_screenshot, get_active_app"
                },
                "target": {
                    "type": "string",
                    "description": "The app name, URL, command, or value to act on"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "read_email",
        "description": "Read Owen's Gmail. Get latest emails, search by sender, summarize unread messages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "latest, search, unread_summary"
                },
                "query": {
                    "type": "string",
                    "description": "Search query or sender name"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of emails to return",
                    "default": 5
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "read_messages",
        "description": "Read Owen's iMessages from his Mac. Search by contact name or keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact": {
                    "type": "string",
                    "description": "Contact name to search (e.g. 'Michael', 'Michael Bennet')"
                },
                "keyword": {
                    "type": "string",
                    "description": "Keyword to search across all messages"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of messages to return",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "read_calendar",
        "description": "Read Owen's Google Calendar events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timeframe": {
                    "type": "string",
                    "description": "today, tomorrow, this_week, or specific date like '2024-01-15'"
                },
                "query": {
                    "type": "string",
                    "description": "Search for specific events by keyword"
                }
            },
            "required": ["timeframe"]
        }
    },
    {
        "name": "search_files",
        "description": "Search Owen's file system for files or folders. List directories, find files by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "File or folder name to search for"
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: home directory)"
                },
                "action": {
                    "type": "string",
                    "description": "search, list, read, git_status"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "web_search",
        "description": "Search the web for current information. Market prices, weather, news, anything requiring live data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_note",
        "description": "Create a note in Apple Notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Note title"
                },
                "content": {
                    "type": "string",
                    "description": "Note content"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "read_notes",
        "description": "Read notes from Apple Notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "latest (most recent note), search (search by keyword)"
                },
                "query": {
                    "type": "string",
                    "description": "Search keyword if action is search"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "create_reminder",
        "description": "Create a reminder in Apple Reminders app.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "What to remind Owen about"
                },
                "due_date": {
                    "type": "string",
                    "description": "When: ISO format datetime or natural language like 'today at 3pm'"
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "read_reminders",
        "description": "Read Owen's reminders and tasks from Apple Reminders.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timeframe": {
                    "type": "string",
                    "description": "today, this_week, all"
                }
            },
            "required": []
        }
    },
    {
        "name": "spawn_build",
        "description": "Spawn a Claude Code build for a software project. Ask clarifying questions, generate spec, open Cursor.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What to build"
                },
                "clarifications": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Answers to clarifying questions Owen has already provided"
                }
            },
            "required": ["description"]
        }
    },
    {
        "name": "get_memory",
        "description": "Retrieve specific memories about Owen from the memory database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look up in memory"
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter: identity, business, routine, relationships, goals, preferences"
                }
            },
            "required": ["query"]
        }
    },

    # ── Phase 2: Gmail send ───────────────────────────────
    {
        "name": "send_email",
        "description": "Send an email from Owen's Gmail account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line"
                },
                "body": {
                    "type": "string",
                    "description": "Email body text"
                }
            },
            "required": ["to", "subject", "body"]
        }
    },

    # ── Phase 2: Calendar create/delete ───────────────────
    {
        "name": "create_calendar_event",
        "description": "Create a new event on Owen's Google Calendar. Use natural language like 'Meeting with John tomorrow at 2pm' or provide explicit start_time in ISO format.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Natural language description, e.g. 'Team standup tomorrow at 9am for 30 minutes'"
                },
                "title": {
                    "type": "string",
                    "description": "Event title (used when start_time is provided)"
                },
                "start_time": {
                    "type": "string",
                    "description": "ISO format datetime, e.g. '2025-05-01T14:00:00'"
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Event duration in minutes (default 60)"
                },
                "description": {
                    "type": "string",
                    "description": "Event description or notes"
                },
                "attendees": {
                    "type": "string",
                    "description": "Comma-separated email addresses to invite"
                }
            },
            "required": []
        }
    },
    {
        "name": "delete_calendar_event",
        "description": "Delete a calendar event by its ID. Get the ID from read_calendar first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Google Calendar event ID"
                }
            },
            "required": ["event_id"]
        }
    },

    # ── Phase 2: Google Drive ─────────────────────────────
    {
        "name": "search_drive",
        "description": "Search Owen's Google Drive for files and documents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "File name or keyword to search for"
                },
                "action": {
                    "type": "string",
                    "description": "search (find by name) or recent (most recently modified files)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of results (default 10)"
                }
            },
            "required": []
        }
    },

    # ── Phase 2: Unified Search ───────────────────────────
    {
        "name": "unified_search",
        "description": "Search across all of Owen's services at once — Gmail, Drive, local files, and Notes. Use when Owen asks to 'find' something without specifying where.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for"
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Which sources to search: gmail, drive, files, notes. Omit to search all."
                }
            },
            "required": ["query"]
        }
    },

    # ── Phase 2: Automation Rules ─────────────────────────
    {
        "name": "manage_automation",
        "description": "Create, list, or delete automation rules. Rules run automatically when triggered (e.g. 'alert me when I get email from X', 'open Spotify every morning').",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "list, create, delete, enable, disable"
                },
                "name": {
                    "type": "string",
                    "description": "Rule name (for create)"
                },
                "trigger_type": {
                    "type": "string",
                    "description": "email, keyword, time, startup"
                },
                "trigger_config": {
                    "type": "object",
                    "description": "Trigger config e.g. {from: 'boss@co.com'} or {keyword: 'urgent'}"
                },
                "actions": {
                    "type": "array",
                    "description": "List of actions e.g. [{type: 'notify', message: 'Boss emailed you'}]",
                    "items": {"type": "object"}
                },
                "rule_id": {
                    "type": "integer",
                    "description": "Rule ID (for delete/enable/disable)"
                }
            },
            "required": ["action"]
        }
    }
]


HAIKU_MODEL  = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-20250514"

# Immediate acknowledgement phrases for tool calls (before result arrives)
TOOL_ACKS = {
    # Phase 1
    "screen_vision":       "Looking at your screen.",
    "read_email":          "Checking your email.",
    "read_messages":       "Checking your messages.",
    "read_calendar":       "Looking at your calendar.",
    "search_files":        "Searching your files.",
    "web_search":          "Searching.",
    "mac_control":         "On it.",
    "create_note":         "Got it.",
    "create_reminder":     "Done.",
    "read_notes":          "Checking your notes.",
    "read_reminders":      "Checking your reminders.",
    "spawn_build":         "On it, spinning up the build.",
    "get_memory":          "Let me think.",
    # Phase 2
    "send_email":          "Sending that now.",
    "create_calendar_event": "Adding that to your calendar.",
    "delete_calendar_event": "Deleting that event.",
    "search_drive":        "Searching Drive.",
    "unified_search":      "Searching everywhere.",
    "manage_automation":   "On it.",
}


class JarvisBrain:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("[BRAIN] WARNING: ANTHROPIC_API_KEY not set.")
            self.client       = None
            self.async_client = None
        else:
            self.client       = anthropic.Anthropic(api_key=api_key)
            self.async_client = anthropic.AsyncAnthropic(api_key=api_key)

    def is_ready(self) -> bool:
        return self.client is not None

    # ── Async streaming (primary path) ───────────────────

    async def stream_chat(self, messages: List[Dict], system_prompt: str):
        """
        Async generator that streams the Haiku response.
        Yields:
          ("text",     str)       — incremental text chunk
          ("tool",     dict)      — tool to call: {id, name, input}
          ("final",    Message)   — the completed Anthropic message object
        """
        if not self.async_client:
            yield ("text", "API key not configured.")
            return

        try:
            async with self.async_client.messages.stream(
                model=HAIKU_MODEL,
                max_tokens=1024,
                system=system_prompt,
                tools=JARVIS_TOOLS,
                messages=messages,
            ) as stream:
                async for event in stream:
                    if (event.type == "content_block_delta"
                            and hasattr(event.delta, "text")):
                        yield ("text", event.delta.text)

                final_msg = await stream.get_final_message()
                yield ("final", final_msg)

        except Exception as e:
            print(f"[BRAIN] Stream error: {e}")
            yield ("text", f"Something went wrong. {e}")

    async def stream_with_tool_result(
        self, messages: List[Dict], system_prompt: str
    ):
        """Stream Haiku's follow-up after tool results are injected."""
        if not self.async_client:
            yield ("text", "API key not configured.")
            return

        try:
            async with self.async_client.messages.stream(
                model=HAIKU_MODEL,
                max_tokens=1024,
                system=system_prompt,
                tools=JARVIS_TOOLS,
                messages=messages,
            ) as stream:
                async for event in stream:
                    if (event.type == "content_block_delta"
                            and hasattr(event.delta, "text")):
                        yield ("text", event.delta.text)

                yield ("final", await stream.get_final_message())

        except Exception as e:
            print(f"[BRAIN] Tool-result stream error: {e}")
            yield ("text", f"Error: {e}")

    # ── Sync fallback (background jobs, non-streaming) ───

    def chat(self, user_message: str, memory_context: str = "",
             conversation_history: List[Dict] = None) -> Dict:
        """Sync Haiku call — used by background jobs and voice pipeline fallback."""
        if not self.client:
            return {
                "text": "API key not configured.",
                "tool_calls": [], "model_used": "none"
            }

        from backend.brain.prompts import get_system_prompt
        system_prompt = get_system_prompt(memory_block=memory_context)
        messages = list(conversation_history or [])[-10:]
        messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=1024,
                system=system_prompt,
                tools=JARVIS_TOOLS,
                messages=messages,
            )
            tool_calls, text_parts = [], []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append({"id": block.id, "name": block.name, "input": block.input})
            return {
                "text": " ".join(text_parts),
                "tool_calls": tool_calls,
                "model_used": HAIKU_MODEL,
                "stop_reason": response.stop_reason,
                "raw_content": response.content,
            }
        except Exception as e:
            print(f"[BRAIN] Chat error: {e}")
            return {"text": str(e), "tool_calls": [], "model_used": "error"}

    def chat_with_tool_result(self, original_messages: List[Dict],
                               tool_results: List[Dict], memory_context: str = "") -> str:
        """Sync: get Haiku's text response after injecting tool results."""
        if not self.client:
            return "API key not configured."
        from backend.brain.prompts import get_system_prompt
        system_prompt = get_system_prompt(memory_block=memory_context)
        try:
            response = self.client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=1024,
                system=system_prompt,
                tools=JARVIS_TOOLS,
                messages=original_messages + [{"role": "user", "content": tool_results}],
            )
            for block in response.content:
                if block.type == "text":
                    return block.text
            return ""
        except Exception as e:
            print(f"[BRAIN] Tool result error: {e}")
            return str(e)

    def generate_briefing(self, briefing_data: dict) -> str:
        """Morning briefing — uses Sonnet for quality."""
        if not self.client:
            return "Good morning Owen. API key not configured."
        from backend.brain.prompts import BRIEFING_PROMPT
        import json
        prompt = BRIEFING_PROMPT.format(briefing_data=json.dumps(briefing_data, indent=2))
        try:
            response = self.client.messages.create(
                model=SONNET_MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            print(f"[BRAIN] Briefing error: {e}")
            return "Good morning Owen. I wasn't able to generate your full briefing due to an error. Check your API key."

    def get_client(self):
        return self.client


# Singleton
_brain = None

def get_brain() -> JarvisBrain:
    global _brain
    if _brain is None:
        _brain = JarvisBrain()
    return _brain
