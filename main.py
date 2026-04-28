"""Jarvis v2.0 — Main entry point."""
import warnings
warnings.filterwarnings("ignore")

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

import uvicorn
from backend.database import init_db
from backend.memory.seed import seed_memories


def _check_permission(path: str) -> bool:
    """Quick check if a path is readable (proxy for permission granted)."""
    try:
        return os.access(path, os.R_OK)
    except Exception:
        return False


def startup():
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  JARVIS v2.0 — Personal AI Operating System")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 1. Database + memories
    init_db()
    seed_memories()

    # 2. ngrok tunnel
    ngrok_url = ""
    if os.getenv("NGROK_AUTH_TOKEN"):
        try:
            from backend.services.ngrok import start_ngrok_tunnel
            ngrok_url = start_ngrok_tunnel(int(os.getenv("PORT", "8001")))
        except Exception as e:
            print(f"[NGROK] Failed: {e}")

    # 3. Background jobs
    for label, fn in [
        ("email monitor",    "backend.jobs.email_monitor.start_email_monitor"),
        ("message monitor",  "backend.jobs.message_monitor.start_message_monitor"),
        ("memory processor", "backend.jobs.memory_processor.start_memory_processor"),
        ("briefing",         "backend.jobs.briefing.start_briefing_scheduler"),
        ("proactive",        "backend.jobs.proactive.start_proactive_engine"),
    ]:
        try:
            mod, fn_name = fn.rsplit(".", 1)
            import importlib
            getattr(importlib.import_module(mod), fn_name)()
        except Exception as e:
            print(f"[JOBS] {label} skipped: {e}")

    # 4. Wake word — Python-side via faster-whisper (browser is secondary fallback)
    from backend.audio.wake_word import init_wake_word
    from backend.audio.text_to_speech import play_chime

    def _on_wake():
        """Python wake word detected — play chime + tell browser we're listening."""
        try:
            play_chime()
        except Exception:
            pass
        import asyncio
        loop = asyncio.get_event_loop()
        from backend.app import broadcast_message
        asyncio.run_coroutine_threadsafe(
            broadcast_message({"type": "status", "status": "listening"}),
            loop,
        )

    def _on_speech(text: str):
        """Python captured the command — send it through the full pipeline."""
        import asyncio
        import uuid
        loop = asyncio.get_event_loop()
        from backend.app import broadcast_message, process_message

        session_id = "voice-" + uuid.uuid4().hex[:8]

        async def _run():
            await broadcast_message({"type": "status", "status": "thinking"})
            response = await process_message(text, session_id)
            await broadcast_message({"type": "response", "text": response, "session_id": session_id})

        asyncio.run_coroutine_threadsafe(_run(), loop)

    init_wake_word(_on_wake, _on_speech)

    # ── Status banner ────────────────────────────────────────
    port = int(os.getenv("PORT", "8001"))
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Local UI:     http://localhost:{port}")
    if ngrok_url:
        print(f"  iPhone URL:   {ngrok_url}")
        print(f"  → Add to iPhone home screen: Safari → Share → Add to Home Screen")
    else:
        print("  iPhone:       add NGROK_AUTH_TOKEN to .env then restart")

    # API key status
    print()
    ok = lambda s: f"  ✓ {s}"
    no = lambda s: f"  ✗ {s}"
    print(ok("Anthropic API") if os.getenv("ANTHROPIC_API_KEY") else no("ANTHROPIC_API_KEY missing — add to .env"))
    print(ok("Fish Audio TTS") if os.getenv("FISH_AUDIO_API_KEY") else "  ~ Fish Audio: not set — using macOS Alex voice (works fine)")
    print(ok("Google OAuth") if (Path(__file__).parent / "gmail_token.pickle").exists() else "  ~ Gmail/Calendar: visit http://localhost:{} /auth/google to connect".format(port))

    # Permission checks
    print()
    print("  Mac permissions:")
    imsg_ok = _check_permission(str(Path.home() / "Library/Messages/chat.db"))
    print(("  ✓ iMessage (Full Disk Access)" if imsg_ok else
           "  ✗ iMessage BLOCKED — fix: System Settings → Privacy → Full Disk Access → add Terminal"))

    # Screen recording: try screencapture -x to /dev/null
    try:
        import subprocess, tempfile
        tmp = tempfile.mktemp(suffix=".png")
        r = subprocess.run(["screencapture", "-x", tmp], capture_output=True, timeout=3)
        sr_ok = r.returncode == 0 and Path(tmp).exists()
        try: Path(tmp).unlink()
        except Exception: pass
    except Exception:
        sr_ok = False
    print(("  ✓ Screen Recording" if sr_ok else
           "  ✗ Screen Recording BLOCKED — fix: System Settings → Privacy → Screen Recording → add Terminal"))

    print()
    print("  Jarvis online. Listening for 'Hey Jarvis'.")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(_app):
    startup()
    yield


from backend.app import app
app.router.lifespan_context = lifespan


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level="warning")
