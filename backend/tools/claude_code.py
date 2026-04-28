"""Spawn Claude Code builds autonomously."""
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


def spawn_build(description: str, clarifications: list = None) -> str:
    """
    Spawn a Claude Code build for a project.
    1. Generate a spec using Claude Sonnet
    2. Write spec to file
    3. Open Cursor with the spec
    4. Send kickoff prompt
    """
    if not description:
        return "Please describe what you'd like me to build."

    # Generate spec
    spec = _generate_spec(description, clarifications or [])

    # Write spec to file
    projects_dir = Path.home() / "Projects"
    projects_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_name = _slugify(description[:30])
    spec_path = projects_dir / f"{project_name}_{timestamp}_SPEC.md"

    spec_path.write_text(spec)

    # Try to open in Cursor
    try:
        subprocess.Popen(["cursor", str(spec_path)])
        return f"Build spec written to {spec_path.name} and opened in Cursor. Claude Code will take it from here."
    except FileNotFoundError:
        pass

    # Fallback: open in default editor
    subprocess.Popen(["open", str(spec_path)])
    return f"Build spec written to {spec_path}. Open it in Cursor to start the build."


def _generate_spec(description: str, clarifications: list) -> str:
    """Generate a build spec using Claude Sonnet."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _template_spec(description)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        clarification_text = ""
        if clarifications:
            clarification_text = "\n\nAdditional context:\n" + "\n".join(f"- {c}" for c in clarifications)

        prompt = f"""Generate a complete, detailed build specification for the following project:

{description}{clarification_text}

The spec should be a comprehensive markdown document that Claude Code can follow to build the project completely.
Include: project overview, tech stack, file structure, feature breakdown, database schema if needed, API endpoints if needed, and build order.
Make it actionable and specific. This is for Owen Medley, who builds on Mac using Python/FastAPI or React/Next.js."""

        from backend.brain.claude import SONNET_MODEL
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    except Exception as e:
        print(f"[BUILD] Spec generation error: {e}")
        return _template_spec(description)


def _template_spec(description: str) -> str:
    """Fallback spec template."""
    return f"""# Build Spec: {description}
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Project Overview
{description}

## Tech Stack
- Backend: Python 3.11 + FastAPI
- Frontend: React / Next.js
- Database: SQLite (local) or Supabase (cloud)

## TODO
- [ ] Define requirements
- [ ] Set up project structure
- [ ] Build core functionality
- [ ] Add tests
- [ ] Deploy

## Notes
Add Anthropic API key to enable AI-generated specs.
"""


def _slugify(text: str) -> str:
    """Convert text to filename-safe slug."""
    import re
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '_', text.strip())
    return text
