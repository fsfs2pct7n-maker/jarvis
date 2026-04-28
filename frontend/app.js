// JARVIS v2.0 — Frontend logic

const ORB_STATE = { STANDBY: 0, LISTENING: 1, THINKING: 2, SPEAKING: 3, FOLLOWUP: 4 };

let ws = null;
let sessionId = null;
let isConnected = false;
let thinkingEl = null;

const msgList    = document.getElementById('msg-list');
const textInput  = document.getElementById('text-input');
const sendBtn    = document.getElementById('send-btn');
const statusLbl  = document.getElementById('status-label');
const connDot    = document.getElementById('conn-dot');

// ── WebSocket ──────────────────────────────────────────────

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws`);
  window._jarvisWS = ws;  // exposed for voice.js wake-word sender

  ws.onopen = () => {
    isConnected = true;
    window._jarvisWS = ws;
    connDot.className = 'dot-online';
    setStatus('STANDBY', ORB_STATE.STANDBY);
  };

  ws.onmessage = ({ data }) => {
    const msg = JSON.parse(data);

    switch (msg.type) {
      case 'status':
        sessionId = msg.session_id || sessionId;
        if (msg.status === 'connected') setStatus('STANDBY', ORB_STATE.STANDBY);
        if (msg.status === 'thinking')  { setStatus('THINKING', ORB_STATE.THINKING); showThinking(); }
        if (msg.status === 'listening') setStatus('STANDBY', ORB_STATE.STANDBY);
        break;

      case 'speaking_start':
        // First audio sentence is queued — mute mic immediately before any sound plays.
        setStatus('SPEAKING', ORB_STATE.SPEAKING);
        if (typeof window.muteDuringSpeech === 'function') window.muteDuringSpeech();
        break;

      case 'response':
        hideThinking();
        addMsg('assistant', msg.text);
        // Mute here too as a safety net for short responses where speaking_start
        // and response arrive close together.
        if (typeof window.muteDuringSpeech === 'function') window.muteDuringSpeech();
        break;

      case 'speaking_done':
        // Audio playback finished on the Mac — safe to re-open the mic now.
        setStatus('STANDBY', ORB_STATE.STANDBY);
        if (typeof window.startFollowup === 'function') window.startFollowup();
        break;

      case 'tool_use':
        setStatus(`▶ ${msg.tool.replace(/_/g, ' ').toUpperCase()}`, ORB_STATE.THINKING);
        break;

      case 'proactive_alert':
        addMsg('alert', msg.content);
        setStatus('ALERT', ORB_STATE.SPEAKING);
        setTimeout(() => setStatus('STANDBY', ORB_STATE.STANDBY), 4000);
        break;

      case 'briefing':
        addMsg('assistant', msg.content);
        break;
    }
  };

  ws.onclose = () => {
    isConnected = false;
    window._jarvisWS = null;
    connDot.className = 'dot-offline';
    setStatus('RECONNECTING...', ORB_STATE.STANDBY);
    setTimeout(connect, 3000);
  };
}

// ── Send message ──────────────────────────────────────────

function send(text) {
  text = text.trim();
  if (!text) return;
  textInput.value = '';
  // Cancel any active follow-up window — we're starting a new turn
  if (typeof window.cancelFollowup === 'function') window.cancelFollowup();
  addMsg('user', text);

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'chat', text }));
    setStatus('THINKING', ORB_STATE.THINKING);
    showThinking();
  } else {
    // REST fallback
    setStatus('THINKING', ORB_STATE.THINKING);
    showThinking();
    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, session_id: sessionId || '' })
    })
    .then(r => r.json())
    .then(d => {
      hideThinking();
      addMsg('assistant', d.response);
      sessionId = d.session_id;
      setStatus('SPEAKING', ORB_STATE.SPEAKING);
      setTimeout(() => setStatus('STANDBY', ORB_STATE.STANDBY), 3000);
    })
    .catch(() => {
      hideThinking();
      addMsg('assistant', 'Connection lost. Is Jarvis running?');
      setStatus('STANDBY', ORB_STATE.STANDBY);
    });
  }
}

// ── Messages ──────────────────────────────────────────────

function addMsg(role, text) {
  const el = document.createElement('div');
  el.className = `msg ${role}`;
  el.textContent = text;
  msgList.appendChild(el);
  // Keep last 40 messages
  while (msgList.children.length > 40) msgList.removeChild(msgList.firstChild);
  msgList.scrollTop = msgList.scrollHeight;
}

function showThinking() {
  hideThinking();
  thinkingEl = document.createElement('div');
  thinkingEl.className = 'thinking';
  thinkingEl.innerHTML = '<span></span><span></span><span></span>';
  msgList.appendChild(thinkingEl);
  msgList.scrollTop = msgList.scrollHeight;
}

function hideThinking() {
  if (thinkingEl) { thinkingEl.remove(); thinkingEl = null; }
  // Clean up any lingering tool indicators
  msgList.querySelectorAll('.tool-indicator').forEach(e => e.remove());
}

// ── Status ────────────────────────────────────────────────

function setStatus(text, orbState) {
  statusLbl.textContent = text;
  statusLbl.classList.toggle('active', orbState !== ORB_STATE.STANDBY);
  if (typeof setOrbState === 'function') setOrbState(orbState);
}

// ── Events ────────────────────────────────────────────────

sendBtn.addEventListener('click', () => send(textInput.value));
textInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(textInput.value); }
});

// Notify voice.js when we start/stop listening
window.onVoiceStart  = () => setStatus('LISTENING', ORB_STATE.LISTENING);
window.onVoiceEnd    = () => setStatus('STANDBY',   ORB_STATE.STANDBY);
window.onVoiceResult = (text) => { send(text); };

// Called by voice.js during the follow-up countdown
window.onFollowupTick = (secsLeft) => {
  setStatus(`FOLLOW UP  ${secsLeft}s`, ORB_STATE.FOLLOWUP);
};
window.onFollowupEnd = () => {
  setStatus('STANDBY', ORB_STATE.STANDBY);
};

// ── START JARVIS overlay ──────────────────────────────────
const startOverlay = document.getElementById('start-overlay');
const startBtn     = document.getElementById('start-btn');
const startStatus  = document.getElementById('start-status');

window.startJarvis = async function () {
  startBtn.disabled = true;
  startStatus.textContent = 'requesting microphone...';
  startStatus.className = '';

  // Request mic permission explicitly — surfaces the browser prompt
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    // Stop the test stream immediately; we just needed the permission grant
    stream.getTracks().forEach(t => t.stop());
    startStatus.textContent = 'microphone granted — connecting...';
    startStatus.className = 'ok';
  } catch (err) {
    startStatus.textContent = 'microphone denied — voice won\'t work, continuing anyway';
    startStatus.className = 'err';
    await new Promise(r => setTimeout(r, 1500));
  }

  // Connect WebSocket — once open, hide overlay and start watcher
  connect();
};

// Hide overlay once WebSocket opens
const _origOnOpen = ws => {
  // ws is null until connect() is called — patch via the connect close
};
// We intercept ws.onopen inside connect() already; here we watch isConnected
const _overlayInterval = setInterval(() => {
  if (isConnected) {
    clearInterval(_overlayInterval);
    startOverlay.classList.add('hidden');
    setTimeout(() => { startOverlay.style.display = 'none'; }, 650);
  }
}, 200);

startBtn.addEventListener('click', window.startJarvis);

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}
