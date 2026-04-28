"""Tasks and Reminders via AppleScript."""
import subprocess
from datetime import datetime


def run_applescript(script: str) -> str:
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=15)
    return result.stdout.strip()


def create_reminder(title: str, due_date: str = "") -> str:
    """Create a reminder in Apple Reminders."""
    if not title:
        return "Please provide a reminder description."

    title_escaped = title.replace('"', '\\"')

    if due_date:
        # Try to parse the due date
        due_str = _parse_due_date(due_date)
        if due_str:
            script = f'''tell application "Reminders"
                set theList to default list
                set newReminder to make new reminder at end of theList with properties {{name:"{title_escaped}", due date:date "{due_str}"}}
                return name of newReminder
            end tell'''
        else:
            script = f'''tell application "Reminders"
                set theList to default list
                make new reminder at end of theList with properties {{name:"{title_escaped}"}}
            end tell'''
    else:
        script = f'''tell application "Reminders"
            set theList to default list
            make new reminder at end of theList with properties {{name:"{title_escaped}"}}
        end tell'''

    result = run_applescript(script)

    if due_date:
        return f"Reminder set: '{title}' — due {due_date}"
    return f"Reminder added: '{title}'"


def read_reminders(timeframe: str = "today") -> str:
    """Read reminders from Apple Reminders."""

    script = '''tell application "Reminders"
        set output to ""
        repeat with r in (reminders of default list whose completed is false)
            set output to output & name of r & "\\n"
        end repeat
        if output is "" then
            return "No pending reminders."
        else
            return output
        end if
    end tell'''

    result = run_applescript(script)
    if not result:
        return "Could not read reminders. Check Automation permission for Terminal in System Settings."

    return f"Your reminders:\n{result}"


def _parse_due_date(due_date: str) -> str:
    """Parse due date string to AppleScript date format."""
    # Handle common formats
    due_lower = due_date.lower()

    now = datetime.now()

    if "today" in due_lower:
        # Extract time
        time_part = _extract_time(due_lower)
        if time_part:
            date_str = now.strftime(f"%B %d, %Y {time_part}")
            return date_str

    elif "tomorrow" in due_lower:
        from datetime import timedelta
        tomorrow = now + timedelta(days=1)
        time_part = _extract_time(due_lower) or "9:00 AM"
        return tomorrow.strftime(f"%B %d, %Y {time_part}")

    # Try ISO format
    try:
        dt = datetime.fromisoformat(due_date)
        return dt.strftime("%B %d, %Y %I:%M %p")
    except ValueError:
        pass

    return ""


def _extract_time(text: str) -> str:
    """Extract time from natural language."""
    import re
    # Match patterns like "3pm", "3:30pm", "3 pm", "3:30 PM"
    match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', text, re.IGNORECASE)
    if match:
        hour = int(match.group(1))
        minute = match.group(2) or "00"
        ampm = match.group(3).upper()
        return f"{hour}:{minute} {ampm}"
    return ""
