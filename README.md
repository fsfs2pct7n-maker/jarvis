# JARVIS v2.0
### Owen Medley's Personal AI Operating System

---

## Quick Start

```bash
# 1. Add your API key
echo "ANTHROPIC_API_KEY=your_key_here" >> .env

# 2. Start Jarvis
./start.sh
```

Opens at http://localhost:8000

---

## Setup Checklist

### Step 1 — API Keys (edit `.env`)

| Key | Where to get it | Required |
|-----|----------------|----------|
| `ANTHROPIC_API_KEY` | console.anthropic.com | Yes |
| `FISH_AUDIO_API_KEY` | fish.audio | Optional (macOS voice is fallback) |
| `NGROK_AUTH_TOKEN` | ngrok.com | For iPhone access |
| `GOOGLE_CLIENT_ID` | Google Cloud Console | For Gmail + Calendar |
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console | For Gmail + Calendar |

### Step 2 — Mac Permissions

Run this and follow the instructions:
```bash
bash scripts/setup_permissions.sh
```

Permissions needed:
- **Microphone** — wake word + voice input
- **Full Disk Access** → add Terminal → for iMessage reading
- **Accessibility** → add Terminal → for Mac control (AppleScript)
- **Screen Recording** → add Terminal → for screen vision

### Step 3 — Google OAuth (Gmail + Calendar)

After adding Google credentials to `.env`:
1. Start Jarvis (`./start.sh`)
2. Visit http://localhost:8000/auth/google
3. Sign in with Owen's Google account
4. Gmail and Calendar will be active

### Step 4 — PyAudio (for microphone wake word)

```bash
# Install Homebrew first if needed (brew.sh)
brew install portaudio
venv/bin/pip install pyaudio
```

Without PyAudio: browser voice button still works (uses Web Speech API).

### Step 5 — iPhone Setup

1. Add `NGROK_AUTH_TOKEN` to `.env`
2. Start Jarvis — the ngrok URL appears in terminal
3. Open that URL on iPhone in Safari
4. Tap Share → "Add to Home Screen"

### Step 6 — Auto-start on Boot

```bash
bash scripts/install_launchagent.sh
```

---

## What Jarvis Can Do

**Voice commands (say "Hey Jarvis" or use the mic button):**
- "What's on my screen?" — takes screenshot, describes what's visible
- "Open Chrome and go to GitHub" — Mac control
- "What's my latest email?" — reads Gmail
- "What did Michael say?" — reads iMessages
- "What's on my schedule today?" — reads Google Calendar
- "Take a note: [content]" — creates Apple Note
- "Remind me to [X] at [time]" — creates Reminder
- "Build me a landing page for BLB" — spawns Claude Code build
- "Search for MNQ futures" — live web search
- "Set volume to 50" — system control
- "Open Spotify" — launches any app

**Background intelligence:**
- Monitors email every 15 minutes — alerts for important senders
- Monitors iMessages every 5 minutes
- Morning briefing at 7am (weather, calendar, emails, messages)
- Extracts and saves memories from every conversation

---

## File Structure

```
jarvis/
├── main.py              — Entry point, startup sequence
├── start.sh             — One-command launcher
├── .env                 — Your API keys (edit this)
├── jarvis.db            — SQLite database (auto-created)
│
├── backend/
│   ├── app.py           — FastAPI routes + WebSocket
│   ├── database.py      — DB connection + schema
│   ├── audio/           — TTS, STT, wake word
│   ├── brain/           — Claude integration + prompts
│   ├── memory/          — Save/retrieve/extract memories
│   ├── tools/           — All 12 tools (screen, Mac, email, etc.)
│   ├── jobs/            — Background tasks
│   └── services/        — ngrok
│
└── frontend/
    ├── index.html       — Main UI
    ├── app.js           — WebSocket + chat logic
    ├── voice.js         — Browser voice input
    └── style.css        — Dark JARVIS aesthetic
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main UI |
| `/ws` | WS | WebSocket for real-time chat |
| `/api/chat` | POST | REST chat endpoint |
| `/api/status` | GET | System status |
| `/api/memories` | GET | All stored memories |
| `/api/briefing` | GET | Generate morning briefing |
| `/auth/google` | GET | Start Google OAuth |

---

## Troubleshooting

**Jarvis doesn't respond:**
- Check ANTHROPIC_API_KEY is set in `.env`
- Check server is running: `make status`

**iMessage reading fails:**
- Grant Full Disk Access to Terminal in System Settings

**AppleScript / Mac control fails:**
- Grant Accessibility to Terminal in System Settings

**Voice not working in browser:**
- Must use Chrome or Safari
- Allow microphone when prompted

**Gmail/Calendar shows "not connected":**
- Visit http://localhost:8000/auth/google to authorize

---

## Commands

```bash
make setup    # Install dependencies
make run      # Start Jarvis
make stop     # Stop Jarvis
make logs     # Tail logs
make status   # Check if running
```
