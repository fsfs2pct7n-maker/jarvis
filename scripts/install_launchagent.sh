#!/bin/bash
# Install Jarvis as a macOS LaunchAgent — auto-starts on every login

JARVIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_SRC="$JARVIS_DIR/scripts/launch_agent.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.owen.jarvis.plist"
AGENTS_DIR="$HOME/Library/LaunchAgents"

# Ensure LaunchAgents dir exists
mkdir -p "$AGENTS_DIR"

# Write plist with real path substituted
sed "s|JARVIS_DIR_PLACEHOLDER|$JARVIS_DIR|g" "$PLIST_SRC" > "$PLIST_DEST"

echo "Jarvis directory: $JARVIS_DIR"
echo "Plist installed:  $PLIST_DEST"

# Unload previous instance if running
launchctl unload "$PLIST_DEST" 2>/dev/null || true

# Load (registers with launchd — will start on next login, or start now below)
launchctl load "$PLIST_DEST"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓ Jarvis will auto-start on every Mac login."
echo ""
echo "  Start now:    launchctl start com.owen.jarvis"
echo "  Stop:         launchctl stop com.owen.jarvis"
echo "  Uninstall:    launchctl unload $PLIST_DEST && rm $PLIST_DEST"
echo "  Logs:         tail -f $JARVIS_DIR/logs/jarvis.log"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
