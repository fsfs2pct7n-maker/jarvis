"""Runs after conversations to extract new memories."""
import time
import threading
from typing import List, Dict
from backend.database import get_db


_pending_conversations = []
_lock = threading.Lock()


def queue_conversation(conversation: List[Dict]):
    """Add a conversation to the extraction queue."""
    with _lock:
        _pending_conversations.append(conversation)


def start_memory_processor():
    """Start background memory extraction thread."""
    t = threading.Thread(target=_processor_loop, daemon=True)
    t.start()
    print("[MEMORY] Memory processor started.")


def _processor_loop():
    """Process queued conversations every 30 seconds."""
    while True:
        try:
            with _lock:
                to_process = _pending_conversations.copy()
                _pending_conversations.clear()

            for conversation in to_process:
                _extract_memories(conversation)

        except Exception as e:
            print(f"[MEMORY] Processor error: {e}")

        time.sleep(30)


def _extract_memories(conversation: List[Dict]):
    """Extract memories from a conversation."""
    from backend.brain.claude import get_brain
    from backend.memory.extractor import extract_and_save_memories

    brain = get_brain()
    if not brain.is_ready():
        return

    count = extract_and_save_memories(conversation, brain.get_client())
    if count > 0:
        print(f"[MEMORY] Extracted {count} new memories.")
