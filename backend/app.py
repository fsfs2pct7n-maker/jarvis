"""FastAPI application — routes, WebSocket, and all endpoints."""
import os
import json
import uuid
import asyncio
import pickle
from pathlib import Path
from typing import Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Jarvis v2.0")

# CORS — allow iPhone + local access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connected WebSocket clients
connected_clients: Set[WebSocket] = set()

# Session tracking
active_sessions = {}


# ─── WebSocket ───────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    session_id = str(uuid.uuid4())

    try:
        # Send welcome
        await websocket.send_json({
            "type": "status",
            "status": "connected",
            "session_id": session_id
        })

        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            if payload.get("type") == "chat":
                text = payload.get("text", "").strip()
                if text:
                    await websocket.send_json({"type": "status", "status": "thinking"})
                    response = await process_message(text, session_id, websocket)
                    await websocket.send_json({
                        "type": "response",
                        "text": response,
                        "session_id": session_id
                    })
                    await websocket.send_json({"type": "status", "status": "listening"})

            elif payload.get("type") == "wake_word":
                # Browser detected "Hey Jarvis" — play chime, signal listening state
                try:
                    from backend.audio.text_to_speech import play_chime
                    play_chime()
                except Exception:
                    pass
                await websocket.send_json({"type": "status", "status": "listening"})

            elif payload.get("type") == "voice_activate":
                await websocket.send_json({"type": "status", "status": "listening"})

            elif payload.get("type") == "interrupt":
                # User pressed stop — kill audio immediately
                try:
                    from backend.audio.text_to_speech import stop_speaking
                    stop_speaking()
                except Exception:
                    pass
                await websocket.send_json({"type": "speaking_done"})
                await websocket.send_json({"type": "status", "status": "listening"})

    except WebSocketDisconnect:
        connected_clients.discard(websocket)
    except Exception as e:
        import traceback
        print(f"[WS] Error: {e}")
        print(f"[WS] Traceback:\n{traceback.format_exc()}")
        connected_clients.discard(websocket)


async def broadcast_message(message: dict):
    """Broadcast a message to all connected clients."""
    disconnected = set()
    for client in connected_clients:
        try:
            await client.send_json(message)
        except Exception:
            disconnected.add(client)
    connected_clients.difference_update(disconnected)


# ─── Core message processing ─────────────────────────────────────────────────

async def process_message(text: str, session_id: str, websocket: WebSocket = None) -> str:
    """
    Full streaming pipeline:
      1. Stream Haiku token-by-token — speak sentences as they complete
      2. If tool use detected: speak ack immediately, execute tool, stream follow-up
      3. DB writes happen after speech is already underway
    """
    import time as _time
    from backend.brain.claude import get_brain, TOOL_ACKS
    from backend.brain.router import execute_tool
    from backend.brain.prompts import get_system_prompt
    from backend.memory.engine import (get_relevant_memories, save_conversation,
                                        get_conversation_history)
    from backend.jobs.memory_processor import queue_conversation
    from backend.audio.text_to_speech import new_token, StreamingSpeaker, extract_sentences
    from backend.brain.activity import log_interaction, detect_tone
    from backend.brain.context import get_context
    from backend.brain.preferences import build_preference_block

    brain = get_brain()
    _t0   = _time.monotonic()
    ctx   = get_context()

    if not brain.is_ready():
        fallback = "API key not configured. Add ANTHROPIC_API_KEY to the .env file."
        if websocket:
            await websocket.send_json({"type": "response", "text": fallback})
        return fallback

    # ── Context + preference tracking ────────────────────────
    tone = detect_tone(text)
    ctx.record_topic(text)
    ctx.update_tone(tone)

    memories        = get_relevant_memories(text)
    history         = get_conversation_history(session_id)
    context_block   = ctx.build_context_block()
    preference_block = build_preference_block()
    tone_hint       = ctx.tone_instruction()

    save_conversation(session_id, "user", text)

    system_prompt = get_system_prompt(
        memory_block=memories,
        context_block=context_block + (f"\n  Tone hint: {tone_hint}" if tone_hint else ""),
        preference_block=preference_block,
    )
    messages = list(history)[-10:] + [{"role": "user", "content": text}]

    # Mint cancellation token and start the streaming speaker NOW — audio can
    # begin playing the instant the first sentence is complete.
    tok     = new_token()
    speaker = StreamingSpeaker(tok)

    full_text      = ""
    buf            = ""      # partial sentence accumulator
    final_msg      = None
    tool_acked     = False
    speaking_start_sent = False   # track first-sentence mute signal

    # ── Phase 1: stream Haiku ─────────────────────────────
    async for kind, data in brain.stream_chat(messages, system_prompt):
        if kind == "text":
            chunk     = data
            full_text += chunk
            buf       += chunk

            # Flush complete sentences to speaker immediately
            sentences, buf = extract_sentences(buf)
            for s in sentences:
                speaker.add(s)
                # Tell browser to mute mic on the very first sentence — audio is starting
                if websocket and not speaking_start_sent:
                    await websocket.send_json({"type": "speaking_start"})
                    speaking_start_sent = True
                if websocket:
                    await websocket.send_json({"type": "stream_chunk", "text": s})

        elif kind == "final":
            final_msg = data

    # Flush any trailing text (response ended without terminal punctuation)
    if buf.strip():
        speaker.add(buf.strip())
        if websocket:
            await websocket.send_json({"type": "stream_chunk", "text": buf.strip()})

    # ── Phase 2: handle tool calls ────────────────────────
    if final_msg and final_msg.stop_reason == "tool_use":
        tool_blocks = [b for b in final_msg.content if b.type == "tool_use"]

        for tc in tool_blocks:
            # Speak immediate acknowledgement before the tool runs
            if not tool_acked:
                ack = TOOL_ACKS.get(tc.name, "On it.")
                speaker.add(ack)
                if websocket:
                    await websocket.send_json({"type": "tool_use", "tool": tc.name})
                tool_acked = True

            print(f"[TOOL] {tc.name} → {tc.input}")
            tool_result = await execute_tool(tc.name, tc.input)

            # Build messages with tool results injected
            tool_messages = (
                list(history)[-6:]
                + [{"role": "user",      "content": text}]
                + [{"role": "assistant", "content": final_msg.content}]
                + [{"role": "user",      "content": [{
                    "type":        "tool_result",
                    "tool_use_id": tc.id,
                    "content":     str(tool_result),
                }]}]
            )

        # Stream Haiku's follow-up response
        full_text = ""
        buf       = ""
        async for kind, data in brain.stream_with_tool_result(tool_messages, system_prompt):
            if kind == "text":
                chunk      = data
                full_text += chunk
                buf       += chunk
                sentences, buf = extract_sentences(buf)
                for s in sentences:
                    speaker.add(s)
                    if websocket:
                        await websocket.send_json({"type": "stream_chunk", "text": s})

        if buf.strip():
            speaker.add(buf.strip())
            if websocket:
                await websocket.send_json({"type": "stream_chunk", "text": buf.strip()})

    if not full_text:
        full_text = "Got it."

    # Notify UI with complete text — mic stays muted until speaking_done
    if websocket:
        await websocket.send_json({"type": "response", "text": full_text})

    # ── Activity log ─────────────────────────────────────────
    _response_ms = int((_time.monotonic() - _t0) * 1000)
    _tool_used   = None
    _tool_inp    = None
    if final_msg and final_msg.stop_reason == "tool_use":
        _tb = [b for b in final_msg.content if b.type == "tool_use"]
        if _tb:
            _tool_used = _tb[0].name
            _tool_inp  = _tb[0].input
            ctx.record_tool(_tool_used)
    log_interaction(session_id, text, _tool_used, _tool_inp, _response_ms, tone)

    # DB writes — fire and forget
    save_conversation(session_id, "assistant", full_text, model_used="haiku")
    queue_conversation(get_conversation_history(session_id, limit=4))

    # Finish TTS in background; signal the browser when audio actually stops
    # so the mic only re-opens after Jarvis stops talking (prevents feedback loop)
    async def _finish_and_signal():
        await asyncio.get_event_loop().run_in_executor(None, speaker.finish)
        if websocket:
            try:
                await websocket.send_json({"type": "speaking_done"})
            except Exception:
                pass

    asyncio.create_task(_finish_and_signal())

    return full_text


# ─── REST API ─────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    text: str
    session_id: str = ""


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    response = await process_message(req.text, session_id)
    return {"response": response, "session_id": session_id}


@app.get("/api/status")
async def status():
    from backend.brain.claude import get_brain
    from backend.services.ngrok import get_ngrok_url

    brain = get_brain()

    # ── Gmail / Calendar token check ──────────────────────
    TOKEN_PATH = Path(__file__).parent.parent / "gmail_token.pickle"
    gmail_ok = False
    calendar_ok = False
    if TOKEN_PATH.exists():
        try:
            with open(TOKEN_PATH, "rb") as f:
                creds = pickle.load(f)
            if creds and creds.valid:
                gmail_ok = True
                calendar_ok = True
            elif creds and creds.refresh_token:
                # Try to refresh — if this fails, token is revoked
                import google.auth.transport.requests as g_req
                try:
                    creds.refresh(g_req.Request())
                    if creds.valid:
                        gmail_ok = True
                        calendar_ok = True
                        # Save refreshed token
                        with open(TOKEN_PATH, "wb") as f:
                            pickle.dump(creds, f)
                except Exception:
                    pass  # token revoked — needs_auth
        except Exception:
            pass

    # ── iMessage: can we open chat.db? ───────────────────
    imessage_ok = False
    chat_db = Path.home() / "Library/Messages/chat.db"
    if chat_db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(chat_db))
            conn.execute("SELECT 1 FROM message LIMIT 1")
            conn.close()
            imessage_ok = True
        except Exception:
            pass

    # ── Screen recording: try a capture ──────────────────
    screen_ok = False
    try:
        import subprocess
        r = subprocess.run(
            ["screencapture", "-x", "-t", "png", "/dev/null"],
            capture_output=True, timeout=3
        )
        screen_ok = r.returncode == 0
    except Exception:
        pass

    # ── Fish Audio ───────────────────────────────────────
    fish_key = os.getenv("FISH_AUDIO_API_KEY", "")
    fish_ok = bool(fish_key)

    # ── ngrok ─────────────────────────────────────────────
    ngrok_url = get_ngrok_url()

    return {
        "status":          "online",
        "anthropic":       "ok" if brain.is_ready()         else "missing_key",
        "fish_audio":      "ok" if fish_ok                  else "fallback_say",
        "gmail":           "ok" if gmail_ok                 else "needs_auth",
        "calendar":        "ok" if calendar_ok              else "needs_auth",
        "imessage":        "ok" if imessage_ok              else "needs_permission",
        "screen_recording":"ok" if screen_ok                else "needs_permission",
        "ngrok":           ngrok_url                        if ngrok_url else "disabled",
        "clients":         len(connected_clients),
    }


@app.get("/status", response_class=HTMLResponse)
async def status_page():
    """Human-readable status dashboard."""
    from backend.brain.claude import get_brain
    from backend.services.ngrok import get_ngrok_url

    brain = get_brain()

    TOKEN_PATH = Path(__file__).parent.parent / "gmail_token.pickle"
    gmail_ok = False
    if TOKEN_PATH.exists():
        try:
            with open(TOKEN_PATH, "rb") as f:
                creds = pickle.load(f)
            gmail_ok = creds and (creds.valid or creds.refresh_token)
        except Exception:
            pass

    chat_db = Path.home() / "Library/Messages/chat.db"
    imessage_ok = False
    if chat_db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(chat_db))
            conn.execute("SELECT 1 FROM message LIMIT 1")
            conn.close()
            imessage_ok = True
        except Exception:
            pass

    screen_ok = False
    try:
        import subprocess
        r = subprocess.run(
            ["screencapture", "-x", "-t", "png", "/dev/null"],
            capture_output=True, timeout=3
        )
        screen_ok = r.returncode == 0
    except Exception:
        pass

    fish_ok   = bool(os.getenv("FISH_AUDIO_API_KEY"))
    ngrok_url = get_ngrok_url()
    ngrok_ok  = bool(ngrok_url)

    def row(label, ok, detail=""):
        icon  = "✓" if ok else "✗"
        cls   = "ok" if ok else "fail"
        extra = f'<span class="detail">{detail}</span>' if detail else ""
        return f'<div class="row"><span class="icon {cls}">{icon}</span><span class="svc">{label}</span>{extra}</div>'

    services = [
        row("Claude AI (Anthropic)", brain.is_ready(),
            "Haiku + Sonnet" if brain.is_ready() else '<a href="/.env">Add ANTHROPIC_API_KEY</a>'),
        row("Fish Audio TTS", fish_ok,
            "Custom voice active" if fish_ok else "Using macOS say (fallback)"),
        row("Gmail", gmail_ok,
            "Connected" if gmail_ok else '<a href="/auth/google">Connect Google →</a>'),
        row("Google Calendar", gmail_ok,
            "Connected" if gmail_ok else '<a href="/auth/google">Connect Google →</a>'),
        row("iMessage", imessage_ok,
            "chat.db accessible" if imessage_ok else "Grant Full Disk Access in System Settings → Privacy"),
        row("Screen Vision", screen_ok,
            "Capture permission granted" if screen_ok else "Grant Screen Recording in System Settings → Privacy"),
        row("iPhone (ngrok)", ngrok_ok,
            f'<a href="{ngrok_url}" target="_blank">{ngrok_url}</a>' if ngrok_ok else "Set NGROK_AUTH_TOKEN in .env"),
        row("WebSocket clients", True, f"{len(connected_clients)} connected"),
    ]

    html_rows = "\n".join(services)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Jarvis — Status</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@300;500;700&display=swap">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --cyan: #00d4ff; --bg: #000008; --card: #080814;
      --border: rgba(0,212,255,.15); --glow: rgba(0,212,255,.4);
    }}
    body {{
      background: var(--bg); color: #c8e8f0;
      font-family: 'Rajdhani', sans-serif; min-height: 100vh;
      padding: 40px 20px;
    }}
    header {{
      display: flex; align-items: center; gap: 14px;
      margin-bottom: 36px;
    }}
    .logo {{
      width: 38px; height: 38px;
      border: 2px solid var(--cyan); border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-family: 'Share Tech Mono', monospace; font-size: 16px;
      color: var(--cyan); box-shadow: 0 0 14px var(--glow);
    }}
    h1 {{
      font-size: 22px; font-weight: 700; letter-spacing: 6px;
      color: var(--cyan); text-shadow: 0 0 20px var(--glow);
    }}
    .subtitle {{
      font-size: 12px; letter-spacing: 3px; color: rgba(0,212,255,.4);
      font-family: 'Share Tech Mono', monospace; margin-bottom: 28px;
    }}
    .card {{
      max-width: 600px; background: var(--card);
      border: 1px solid var(--border); border-radius: 4px;
      overflow: hidden;
    }}
    .row {{
      display: flex; align-items: center; gap: 14px;
      padding: 14px 20px;
      border-bottom: 1px solid rgba(0,212,255,.07);
    }}
    .row:last-child {{ border-bottom: none; }}
    .icon {{
      width: 22px; height: 22px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 12px; font-weight: 700; flex-shrink: 0;
    }}
    .icon.ok   {{ background: rgba(0,212,255,.15); color: var(--cyan); }}
    .icon.fail {{ background: rgba(255,60,60,.12); color: #ff6060; }}
    .svc  {{ font-size: 16px; font-weight: 600; flex: 1; }}
    .detail {{ font-size: 13px; color: rgba(0,212,255,.5); font-family: 'Share Tech Mono', monospace; }}
    .detail a {{ color: #4db8ff; text-decoration: none; }}
    .detail a:hover {{ text-decoration: underline; }}
    .actions {{
      max-width: 600px; margin-top: 24px;
      display: flex; gap: 12px; flex-wrap: wrap;
    }}
    .btn {{
      padding: 10px 20px; border: 1px solid rgba(0,212,255,.3);
      background: transparent; color: var(--cyan); border-radius: 3px;
      font-family: 'Rajdhani', sans-serif; font-size: 15px; font-weight: 600;
      text-decoration: none; letter-spacing: 1px; cursor: pointer;
      transition: all .2s;
    }}
    .btn:hover {{ background: rgba(0,212,255,.1); border-color: var(--cyan); }}
    .refresh {{ font-size: 11px; color: rgba(0,212,255,.3); margin-top: 20px;
                font-family: 'Share Tech Mono', monospace; }}
  </style>
</head>
<body>
  <header>
    <div class="logo">J</div>
    <h1>JARVIS</h1>
  </header>
  <p class="subtitle">SYSTEM STATUS</p>
  <div class="card">
    {html_rows}
  </div>
  <div class="actions">
    <a class="btn" href="/">← Back to Jarvis</a>
    <a class="btn" href="/auth/google">Connect Google</a>
    <a class="btn" href="/status" onclick="location.reload();return false;">Refresh</a>
  </div>
  <p class="refresh">Auto-refreshes every 30s</p>
  <script>setTimeout(() => location.reload(), 30000);</script>
</body>
</html>"""


@app.post("/api/interrupt")
async def interrupt():
    """Stop all audio immediately — called by the stop button."""
    try:
        from backend.audio.text_to_speech import stop_speaking
        stop_speaking()
    except Exception:
        pass
    await broadcast_message({"type": "speaking_done"})
    await broadcast_message({"type": "status", "status": "listening"})
    return {"ok": True}


@app.get("/api/memories")
async def get_memories():
    from backend.memory.engine import get_all_memories
    return {"memories": get_all_memories()}


@app.get("/api/briefing")
async def get_briefing():
    from backend.jobs.briefing import generate_briefing
    text = generate_briefing()
    return {"briefing": text}


@app.get("/api/alerts")
async def get_alerts():
    from backend.database import get_db
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alerts ORDER BY created_at DESC LIMIT 20")
    alerts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"alerts": alerts}


# ─── Phase 2: Gmail ───────────────────────────────────────────────────────────

@app.get("/api/gmail/unread")
async def gmail_unread():
    from backend.tools.gmail import get_gmail_service, _get_email_details
    service = get_gmail_service()
    if not service:
        return {"messages": [], "error": "not_connected"}
    results = service.users().messages().list(
        userId='me', maxResults=10, labelIds=['INBOX', 'UNREAD']
    ).execute()
    msgs = []
    for m in results.get('messages', []):
        detail = service.users().messages().get(
            userId='me', id=m['id'], format='metadata',
            metadataHeaders=['From', 'Subject', 'Date']
        ).execute()
        headers = {h['name']: h['value'] for h in detail['payload'].get('headers', [])}
        sender = headers.get('From', '')
        if '<' in sender:
            sender = sender.split('<')[0].strip().strip('"')
        msgs.append({
            'id': m['id'],
            'from': sender,
            'subject': headers.get('Subject', 'No subject'),
            'date': headers.get('Date', ''),
            'snippet': detail.get('snippet', ''),
        })
    return {"messages": msgs}


@app.get("/api/gmail/unread-count")
async def gmail_unread_count():
    from backend.tools.gmail import get_gmail_service
    service = get_gmail_service()
    if not service:
        return {"count": 0}
    results = service.users().messages().list(
        userId='me', q='is:unread', maxResults=1
    ).execute()
    return {"count": results.get('resultSizeEstimate', 0)}


@app.get("/api/gmail/search")
async def gmail_search(q: str = ""):
    from backend.tools.gmail import handle_email_request
    if not q:
        return {"error": "query required"}
    result = handle_email_request(action="search", query=q, limit=10)
    return {"result": result}


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str

@app.post("/api/gmail/send")
async def gmail_send(req: SendEmailRequest):
    from backend.tools.gmail import send_email
    result = send_email(to=req.to, subject=req.subject, body=req.body)
    return {"result": result}


# ─── Phase 2: Drive ───────────────────────────────────────────────────────────

@app.get("/api/drive/search")
async def drive_search(q: str = ""):
    from backend.tools.drive import handle_drive_request
    if not q:
        return {"error": "query required"}
    result = handle_drive_request(action="search", query=q)
    return {"result": result}


@app.get("/api/drive/recent")
async def drive_recent(limit: int = 10):
    from backend.tools.drive import get_recent_files_raw
    files = get_recent_files_raw(limit=limit)
    return {"files": files}


# ─── Phase 2: Automation Rules ────────────────────────────────────────────────

@app.get("/api/automation/rules")
async def automation_list():
    from backend.database import get_db
    import json
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, trigger_type, trigger_config, actions, enabled, run_count, last_run, created_at "
        "FROM automation_rules ORDER BY id"
    ).fetchall()
    conn.close()
    return {"rules": [{
        "id": r["id"],
        "name": r["name"],
        "trigger_type": r["trigger_type"],
        "trigger_config": json.loads(r["trigger_config"]),
        "actions": json.loads(r["actions"]),
        "enabled": bool(r["enabled"]),
        "run_count": r["run_count"],
        "last_run": r["last_run"],
        "created_at": r["created_at"],
    } for r in rows]}


class AutomationRuleRequest(BaseModel):
    name: str
    trigger_type: str
    trigger_config: dict
    actions: list

@app.post("/api/automation/rules")
async def automation_create(req: AutomationRuleRequest):
    from backend.tools.automation import create_rule
    result = create_rule(req.name, req.trigger_type, req.trigger_config, req.actions)
    return {"result": result}


@app.delete("/api/automation/rules/{rule_id}")
async def automation_delete(rule_id: int):
    from backend.tools.automation import delete_rule
    result = delete_rule(rule_id)
    return {"result": result}


@app.patch("/api/automation/rules/{rule_id}/toggle")
async def automation_toggle(rule_id: int, enabled: bool = True):
    from backend.tools.automation import toggle_rule
    result = toggle_rule(rule_id, enabled)
    return {"result": result}


@app.get("/api/automation/log")
async def automation_log(limit: int = 20):
    from backend.database import get_db
    import json
    conn = get_db()
    rows = conn.execute(
        "SELECT al.*, ar.name FROM automation_log al "
        "LEFT JOIN automation_rules ar ON al.rule_id = ar.id "
        "ORDER BY al.ran_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return {"log": [dict(r) for r in rows]}


# ─── Phase 3+4: Insights & Preferences ──────────────────────────────────────

@app.get("/api/insights")
async def get_insights_endpoint(type: str = "all"):
    from backend.brain.activity import get_activity_stats, get_tool_frequency
    from backend.brain.insights import get_patterns, generate_optimization_suggestions, get_high_importance_emails
    return {
        "stats":       get_activity_stats(days=14),
        "tools":       get_tool_frequency(days=7),
        "patterns":    get_patterns(limit=10),
        "suggestions": generate_optimization_suggestions(),
        "high_priority_emails": get_high_importance_emails(limit=5),
    }


@app.get("/api/preferences")
async def get_preferences_endpoint():
    from backend.brain.preferences import get_all_preferences
    return {"preferences": get_all_preferences()}


@app.post("/api/preferences")
async def set_preference_endpoint(req: dict):
    from backend.brain.preferences import set_preference
    key   = req.get("key", "")
    value = req.get("value", "")
    if not key or not value:
        return {"error": "key and value required"}
    set_preference(key, value, source="api", confidence=1.0)
    return {"ok": True, "key": key, "value": value}


@app.post("/api/insights/detect-patterns")
async def detect_patterns_endpoint():
    from backend.brain.insights import detect_and_store_patterns
    found = detect_and_store_patterns()
    return {"patterns_found": len(found), "descriptions": found}


@app.get("/api/activity")
async def activity_endpoint(days: int = 7):
    from backend.brain.activity import get_activity_stats, get_tool_frequency, get_recent_commands
    return {
        "stats":           get_activity_stats(days=days),
        "top_tools":       get_tool_frequency(days=days),
        "recent_commands": get_recent_commands(limit=20),
    }


# ─── Phase 2: Unified Search ──────────────────────────────────────────────────

@app.get("/api/search")
async def unified_search_endpoint(q: str = "", sources: str = ""):
    from backend.tools.unified_search import unified_search
    if not q:
        return {"error": "query required"}
    source_list = [s.strip() for s in sources.split(",")] if sources else None
    result = unified_search(query=q, sources=source_list)
    return {"result": result}


# ─── Google OAuth ─────────────────────────────────────────────────────────────

# Stores state → code_verifier between the two OAuth legs (single-user, in-memory is fine)
_oauth_pending: dict = {}

GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/drive.readonly',
]

def _make_flow():
    from google_auth_oauthlib.flow import Flow
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id":     os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
                "token_uri":     "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=GOOGLE_SCOPES,
    )
    flow.redirect_uri = redirect_uri
    return flow


@app.get("/auth/google")
async def google_auth():
    """Start Google OAuth flow."""
    if not os.getenv("GOOGLE_CLIENT_ID"):
        return HTMLResponse("<h2>Google OAuth not configured. Add GOOGLE_CLIENT_ID to .env</h2>")

    try:
        flow = _make_flow()
        # access_type=offline gets a refresh token; include_granted_scopes avoids scope drift.
        # Do NOT pass code_challenge_method — let google-auth-oauthlib decide; we capture
        # whatever code_verifier it generates and stash it for the callback.
        auth_url, state = flow.authorization_url(
            prompt='consent',
            access_type='offline',
        )
        # Persist the verifier (may be None if PKCE not used by this library version)
        _oauth_pending[state] = getattr(flow, 'code_verifier', None)
        return RedirectResponse(auth_url)
    except Exception as e:
        return HTMLResponse(f"<h2>OAuth error: {e}</h2>")


@app.get("/auth/google/callback")
async def google_callback(code: str = "", error: str = "", state: str = ""):
    """Handle Google OAuth callback."""
    if error:
        return HTMLResponse(f"<h2>OAuth error: {error}</h2>")

    try:
        TOKEN_PATH = Path(__file__).parent.parent / "gmail_token.pickle"

        flow = _make_flow()

        # Retrieve any code_verifier stored during the auth leg
        code_verifier = _oauth_pending.pop(state, None)

        fetch_kwargs = {"code": code}
        if code_verifier:
            fetch_kwargs["code_verifier"] = code_verifier

        flow.fetch_token(**fetch_kwargs)

        creds = flow.credentials
        print(f"[OAUTH] Token obtained. Scopes: {creds.scopes}")

        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)

        print(f"[OAUTH] Token saved to {TOKEN_PATH}")

        return HTMLResponse("""
            <html><body style="background:#0a0a0f;color:#00d4ff;font-family:monospace;padding:40px;">
            <h2>&#x2713; Google connected successfully.</h2>
            <p>Gmail, Calendar, and Drive are now active.</p>
            <p style="color:rgba(0,212,255,.5);font-size:13px;">Redirecting to Jarvis in 2 seconds...</p>
            <script>setTimeout(() => { window.location.href = '/'; }, 2000);</script>
            </body></html>
        """)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[OAUTH] Callback error: {e}\n{tb}")
        return HTMLResponse(f"""
            <html><body style="background:#0a0a0f;color:#ff6060;font-family:monospace;padding:40px;">
            <h2>OAuth callback error</h2>
            <pre style="color:#ffaaaa;font-size:13px;">{e}</pre>
            <p><a href="/auth/google" style="color:#00d4ff;">Try again</a></p>
            </body></html>
        """)


# ─── Static Files + PWA ───────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/manifest.json")
async def manifest():
    return FileResponse(str(FRONTEND_DIR / "manifest.json"))

@app.get("/sw.js")
async def service_worker():
    resp = FileResponse(str(FRONTEND_DIR / "sw.js"), media_type="application/javascript")
    resp.headers["Cache-Control"] = "no-store"
    return resp

@app.get("/nuke", response_class=HTMLResponse)
async def nuke_cache():
    """One-click page that unregisters all service workers and clears all caches."""
    return HTMLResponse("""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Jarvis — Cache Nuke</title>
  <style>
    body { background: #000008; color: #00d4ff; font-family: monospace;
           display: flex; flex-direction: column; align-items: center;
           justify-content: center; height: 100vh; margin: 0; gap: 16px; }
    #status { font-size: 14px; color: #888; }
    button { padding: 12px 28px; background: transparent; border: 1px solid #00d4ff;
             color: #00d4ff; font-family: monospace; font-size: 14px;
             cursor: pointer; border-radius: 4px; }
    button:hover { background: rgba(0,212,255,0.1); }
  </style>
</head>
<body>
  <div style="font-size:22px;letter-spacing:4px;">JARVIS CACHE NUKE</div>
  <div id="status">Click to wipe service workers and all cached files</div>
  <button onclick="nuke()">⚡ NUKE &amp; RELOAD</button>
  <script>
    async function nuke() {
      document.getElementById('status').textContent = 'Unregistering service workers...';
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map(r => r.unregister()));
      document.getElementById('status').textContent = 'Clearing caches...';
      const keys = await caches.keys();
      await Promise.all(keys.map(k => caches.delete(k)));
      document.getElementById('status').textContent = 'Done — redirecting to Jarvis...';
      setTimeout(() => window.location.href = '/', 800);
    }
  </script>
</body>
</html>""")

# Serve static frontend files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
