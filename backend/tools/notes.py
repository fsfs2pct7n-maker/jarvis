"""Apple Notes integration via AppleScript."""
import subprocess
from datetime import datetime


def run_applescript(script: str) -> str:
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=15)
    return result.stdout.strip()


def create_note(content: str, title: str = "") -> str:
    """Create a new note in Apple Notes."""
    if not title:
        title = f"Jarvis Note — {datetime.now().strftime('%B %d, %Y %I:%M %p')}"

    # Escape single quotes for AppleScript
    title_escaped = title.replace('"', '\\"')
    content_escaped = content.replace('"', '\\"').replace('\n', '\\n')

    script = f'''tell application "Notes"
        set newNote to make new note at folder "Notes" of account "iCloud" with properties {{name:"{title_escaped}", body:"{content_escaped}"}}
        return name of newNote
    end tell'''

    result = run_applescript(script)

    if result and "error" not in result.lower():
        return f"Note created: '{title}'"

    # Fallback without account spec
    script2 = f'''tell application "Notes"
        make new note with properties {{name:"{title_escaped}", body:"{content_escaped}"}}
    end tell'''
    run_applescript(script2)
    return f"Note created: '{title}'"


def read_notes(action: str = "latest", query: str = "") -> str:
    """Read notes from Apple Notes."""

    if action == "latest":
        script = '''tell application "Notes"
            set theNotes to notes of default account
            if (count of theNotes) > 0 then
                set latestNote to item 1 of theNotes
                return name of latestNote & "|BODY|" & body of latestNote
            else
                return "No notes found."
            end if
        end tell'''

        result = run_applescript(script)
        if "|BODY|" in result:
            parts = result.split("|BODY|", 1)
            title = parts[0]
            body = parts[1][:500] if len(parts) > 1 else ""
            return f"Most recent note — '{title}':\n\n{body}"
        return result or "Could not read notes."

    elif action == "search":
        if not query:
            return "Please provide a search term."

        query_escaped = query.replace('"', '\\"')
        script = f'''tell application "Notes"
            set matchingNotes to ""
            repeat with n in notes of default account
                if body of n contains "{query_escaped}" or name of n contains "{query_escaped}" then
                    set matchingNotes to matchingNotes & name of n & "\\n"
                end if
            end repeat
            if matchingNotes is "" then
                return "No notes found containing that text."
            else
                return matchingNotes
            end if
        end tell'''

        result = run_applescript(script)
        return f"Notes matching '{query}':\n{result}" if result else f"No notes found for '{query}'."

    return "Unknown notes action."
