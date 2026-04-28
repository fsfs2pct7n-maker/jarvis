"""Smart content summarization — emails, threads, documents, meetings."""
import os
import re
import anthropic


def _claude_summarize(content: str, instruction: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"{instruction}\n\n---\n{content[:6000]}"
        }]
    )
    return resp.content[0].text.strip()


async def handle_summarize_request(
    content_type: str,
    content: str = "",
    source: str = "",
    depth: str = "brief",
) -> str:
    """
    Summarize any content. content_type: email_thread | document | meeting | general
    depth: brief (2-3 sentences) | normal (1 paragraph) | detailed (key points + actions)
    """

    if not content and not source:
        return "Nothing to summarize — provide content or a source."

    # Pull email thread from Gmail if source looks like a search query
    if content_type == "email_thread" and not content and source:
        content = await _fetch_email_thread(source)
        if not content:
            return f"Couldn't find an email thread matching '{source}'."

    # Pull file content if source is a file path
    if content_type == "document" and not content and source:
        content = _read_file(source)
        if not content:
            return f"Couldn't read document at '{source}'."

    if not content:
        return "No content to summarize."

    if depth == "brief":
        instruction = (
            "Summarize this in 2-3 sentences. Plain English, no bullet points, no markdown. "
            "Lead with the most important point. Be direct."
        )
    elif depth == "detailed":
        instruction = (
            "Summarize this with: (1) the key point, (2) any action items or decisions, "
            "(3) one sentence on next steps. Plain English only, no markdown."
        )
    else:
        instruction = (
            "Summarize this in one short paragraph. Plain English, no bullet points."
        )

    type_prefix = {
        "email_thread": "EMAIL THREAD",
        "document":     "DOCUMENT",
        "meeting":      "MEETING NOTES",
        "general":      "CONTENT",
    }.get(content_type, "CONTENT")

    return _claude_summarize(f"[{type_prefix}]\n{content}", instruction)


async def _fetch_email_thread(query: str) -> str:
    """Fetch and format an email thread from Gmail."""
    try:
        from backend.tools.gmail import handle_email_request
        result = await handle_email_request(action="search", query=query, max_results=5)
        return result if isinstance(result, str) else str(result)
    except Exception as e:
        return ""


def _read_file(path: str) -> str:
    """Read a text file safely."""
    import os
    try:
        if not os.path.exists(path):
            return ""
        size = os.path.getsize(path)
        if size > 500_000:
            return ""  # too large
        with open(path, "r", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


async def smart_email_triage(emails: list[dict]) -> str:
    """
    Given a list of email dicts (subject, sender, snippet),
    return a spoken triage: who to respond to, what to ignore.
    """
    if not emails:
        return "No emails to triage."

    lines = []
    for i, e in enumerate(emails[:10], 1):
        lines.append(f"{i}. From: {e.get('sender','?')} | Subject: {e.get('subject','?')} | {e.get('snippet','')[:120]}")

    content = "\n".join(lines)
    instruction = (
        "You are triaging Owen Medley's inbox. For each email, say in one phrase: "
        "respond now, respond later, or ignore. Group them. "
        "Spoken English only, no bullet points, no markdown."
    )
    return _claude_summarize(content, instruction)
