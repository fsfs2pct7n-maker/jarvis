"""Web search using Anthropic's built-in web search or fallback to DuckDuckGo."""
import os
import requests
from typing import Optional


def search_web(query: str) -> str:
    """Search the web and return a summary."""
    if not query:
        return "No search query provided."

    # Try Anthropic web search first (if API key available)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        try:
            return _anthropic_web_search(query, api_key)
        except Exception as e:
            print(f"[SEARCH] Anthropic search failed: {e}, trying fallback")

    # Fallback: DuckDuckGo instant answer API
    return _duckduckgo_search(query)


def _anthropic_web_search(query: str, api_key: str) -> str:
    """Use Claude with web search tool."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": f"Search for: {query}. Give me a direct, brief answer suitable for reading aloud. No markdown."
        }]
    )

    for block in response.content:
        if hasattr(block, 'text'):
            return block.text

    return f"Search completed for '{query}' but no results returned."


def _duckduckgo_search(query: str) -> str:
    """Use DuckDuckGo instant answer API."""
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1
            },
            timeout=10
        )
        data = response.json()

        answer = data.get("AbstractText", "")
        if answer:
            return answer

        # Try instant answer
        answer = data.get("Answer", "")
        if answer:
            return answer

        # Try definition
        definition = data.get("Definition", "")
        if definition:
            return definition

        return f"No instant answer found for '{query}'. Try asking me to open Chrome and search."

    except Exception as e:
        return f"Search failed: {e}"


def get_weather(location: str = "Lafayette, Indiana") -> str:
    """Get weather for a location."""
    # Use wttr.in for free weather data
    try:
        response = requests.get(
            f"https://wttr.in/{location.replace(' ', '+')}?format=3",
            timeout=10
        )
        if response.status_code == 200:
            return response.text.strip()
    except Exception:
        pass

    return search_web(f"current weather in {location}")
