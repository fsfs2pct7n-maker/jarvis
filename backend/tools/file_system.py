"""File system operations."""
import os
import subprocess
from pathlib import Path
from typing import List


HOME = Path.home()


def _expand(path: str) -> str:
    """Expand ~ and env vars in paths."""
    return str(Path(path).expanduser()) if path else path


def handle_file_request(action: str, query: str = "", path: str = "") -> str:
    """Handle file system requests."""
    path = _expand(path)

    if action == "search":
        return _search_files(query, path or str(HOME))
    elif action == "list":
        return _list_directory(path or str(HOME))
    elif action == "read":
        return _read_file(path or query)
    elif action == "git_status":
        return _git_status(path or ".")
    elif action == "create_folder":
        return _create_folder(path or query)
    elif action == "open":
        return _open_file(path or query)
    else:
        return f"Unknown file action: {action}"


def _search_files(query: str, search_path: str) -> str:
    """Search for files by name."""
    if not query:
        return "Please provide a search term."

    try:
        result = subprocess.run(
            ["find", search_path, "-name", f"*{query}*", "-not", "-path", "*/.*",
             "-not", "-path", "*/node_modules/*", "-not", "-path", "*/.git/*"],
            capture_output=True, text=True, timeout=15
        )
        files = [f for f in result.stdout.strip().split('\n') if f]

        if not files:
            return f"No files found matching '{query}'."

        if len(files) > 20:
            return f"Found {len(files)} files matching '{query}'. First 20:\n" + "\n".join(files[:20])

        return f"Found {len(files)} file(s) matching '{query}':\n" + "\n".join(files)
    except subprocess.TimeoutExpired:
        return "Search timed out. Try being more specific."
    except Exception as e:
        return f"File search error: {e}"


def _list_directory(path: str) -> str:
    """List directory contents."""
    try:
        p = Path(path)
        if not p.exists():
            return f"Directory not found: {path}"
        if not p.is_dir():
            return f"Not a directory: {path}"

        items = []
        for item in sorted(p.iterdir()):
            if item.name.startswith('.'):
                continue
            if item.is_dir():
                items.append(f"[dir] {item.name}")
            else:
                size = item.stat().st_size
                size_str = f"{size:,} bytes" if size < 1024 else f"{size//1024:,} KB"
                items.append(f"[file] {item.name} ({size_str})")

        if not items:
            return f"Directory '{path}' is empty."

        return f"Contents of {path}:\n" + "\n".join(items[:50])
    except PermissionError:
        return f"Permission denied accessing {path}."
    except Exception as e:
        return f"Error listing directory: {e}"


def _read_file(path: str) -> str:
    """Read file contents."""
    try:
        p = Path(path)
        if not p.exists():
            return f"File not found: {path}"

        if p.stat().st_size > 50000:  # 50KB limit
            return f"File too large to read directly ({p.stat().st_size // 1024} KB)."

        content = p.read_text(encoding='utf-8', errors='replace')
        if len(content) > 3000:
            content = content[:3000] + "\n\n[... truncated ...]"

        return f"Contents of {path}:\n\n{content}"
    except Exception as e:
        return f"Error reading file: {e}"


def _git_status(path: str) -> str:
    """Run git status in a directory."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, timeout=10,
            cwd=path
        )
        if result.returncode != 0:
            return f"Not a git repository: {path}"

        output = result.stdout.strip()
        if not output:
            return "Git status: Working tree clean. Nothing to commit."

        # Also get current branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5, cwd=path
        )
        branch = branch_result.stdout.strip()

        return f"Branch: {branch}\n\n{output}"
    except Exception as e:
        return f"Git error: {e}"


def _create_folder(path: str) -> str:
    """Create a new folder."""
    try:
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        return f"Folder created: {path}"
    except Exception as e:
        return f"Error creating folder: {e}"


def _open_file(path: str) -> str:
    """Open a file with its default application."""
    try:
        subprocess.run(["open", path])
        return f"Opening {path}."
    except Exception as e:
        return f"Error opening file: {e}"
