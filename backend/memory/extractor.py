"""Extract new memories from conversations using Claude Sonnet."""
import json
import os
from typing import List, Dict
from backend.memory.engine import save_memory


def extract_and_save_memories(conversation: List[Dict], anthropic_client) -> int:
    """
    Run after a conversation to extract new facts about Owen.
    Returns number of memories saved.
    """
    if not conversation or len(conversation) < 2:
        return 0

    # Format conversation for analysis
    conv_text = "\n".join([
        f"{turn['role'].upper()}: {turn['content']}"
        for turn in conversation
    ])

    from backend.brain.prompts import MEMORY_EXTRACTOR_PROMPT

    try:
        from backend.brain.claude import SONNET_MODEL
        response = anthropic_client.messages.create(
            model=SONNET_MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"{MEMORY_EXTRACTOR_PROMPT}\n\nCONVERSATION:\n{conv_text}"
                }
            ]
        )

        text = response.content[0].text.strip()

        # Parse JSON
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        memories = json.loads(text)

        count = 0
        for mem in memories:
            if all(k in mem for k in ["category", "key", "value"]):
                save_memory(
                    category=mem["category"],
                    key=mem["key"],
                    value=mem["value"],
                    confidence=mem.get("confidence", 0.8),
                    source="conversation"
                )
                count += 1

        return count

    except Exception as e:
        print(f"[MEMORY] Extraction failed: {e}")
        return 0
