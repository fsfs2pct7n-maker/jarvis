"""Chrome browser control via AppleScript."""
import subprocess


def run_applescript(script: str) -> str:
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=15)
    return result.stdout.strip()


def open_url(url: str) -> str:
    if not url.startswith("http"):
        url = f"https://{url}"
    run_applescript('tell application "Google Chrome" to activate')
    run_applescript(f'tell application "Google Chrome" to open location "{url}"')
    return f"Opened {url}"


def search_google(query: str) -> str:
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    return open_url(url)


def get_current_url() -> str:
    script = '''tell application "Google Chrome"
        return URL of active tab of front window
    end tell'''
    return run_applescript(script)


def get_page_title() -> str:
    script = '''tell application "Google Chrome"
        return title of active tab of front window
    end tell'''
    return run_applescript(script)
