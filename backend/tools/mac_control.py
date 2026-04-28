"""Mac control via AppleScript."""
import subprocess
import os


def run_applescript(script: str) -> str:
    """Run an AppleScript and return output."""
    result = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        return f"AppleScript error: {result.stderr.strip()}"
    return result.stdout.strip()


def execute_mac_action(action: str, target: str = "") -> str:
    """Execute a Mac control action."""

    if action == "open_url":
        url = target if target.startswith("http") else f"https://{target}"
        script = f'tell application "Google Chrome" to open location "{url}"'
        run_applescript('tell application "Google Chrome" to activate')
        run_applescript(script)
        return f"Opened {url} in Chrome."

    elif action == "open_app":
        script = f'tell application "{target}" to activate'
        result = run_applescript(script)
        if "error" in result.lower():
            # Try launching it
            subprocess.Popen(["open", "-a", target])
            return f"Launching {target}."
        return f"Opened {target}."

    elif action == "run_command":
        result = subprocess.run(
            target, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip() or result.stderr.strip()
        return output if output else "Command ran with no output."

    elif action == "open_terminal":
        run_applescript('tell application "Terminal" to activate')
        return "Terminal is open."

    elif action == "run_terminal_command":
        escaped = target.replace('"', '\\"')
        script = 'tell application "Terminal"\n    activate\n    do script "' + escaped + '"\nend tell'
        run_applescript(script)
        return f"Running '{target}' in Terminal."

    elif action == "set_volume":
        try:
            level = int(target) if target else 50
            level = max(0, min(100, level))
            script = f"set volume output volume {level}"
            run_applescript(script)
            return f"Volume set to {level}."
        except ValueError:
            return "Please provide a volume level between 0 and 100."

    elif action == "mute":
        run_applescript("set volume output muted true")
        return "Muted."

    elif action == "unmute":
        run_applescript("set volume output muted false")
        return "Unmuted."

    elif action == "take_screenshot":
        path = os.path.expanduser("~/Desktop/jarvis_screenshot.png")
        subprocess.run(["screencapture", "-x", path])
        return f"Screenshot saved to Desktop."

    elif action == "get_active_app":
        script = 'tell application "System Events" to get name of first application process whose frontmost is true'
        app = run_applescript(script)
        return f"Active app: {app}"

    elif action == "search_chrome":
        query = target.replace('"', '\\"')
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        run_applescript('tell application "Google Chrome" to activate')
        run_applescript(f'tell application "Google Chrome" to open location "{url}"')
        return f"Searching for '{target}' in Chrome."

    elif action == "new_chrome_tab":
        run_applescript('tell application "Google Chrome" to activate')
        run_applescript('tell application "Google Chrome" to make new tab')
        if target:
            url = target if target.startswith("http") else f"https://{target}"
            run_applescript(f'tell application "Google Chrome" to set URL of active tab of front window to "{url}"')
        return "New Chrome tab opened."

    elif action == "get_system_time":
        import datetime
        now = datetime.datetime.now()
        return now.strftime("It's %I:%M %p on %A, %B %d.")

    elif action == "lock_screen":
        script = 'tell application "System Events" to keystroke "q" using {command down, control down}'
        run_applescript(script)
        return "Screen locked."

    elif action == "empty_trash":
        script = 'tell application "Finder" to empty trash'
        run_applescript(script)
        return "Trash emptied."

    elif action == "get_wifi":
        result = subprocess.run(
            ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
            capture_output=True, text=True
        )
        for line in result.stdout.split('\n'):
            if 'SSID' in line and 'BSSID' not in line:
                return f"Connected to: {line.split(':')[1].strip()}"
        return "Could not determine WiFi network."

    else:
        return f"Unknown Mac action: {action}"
