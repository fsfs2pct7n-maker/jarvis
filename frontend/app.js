// JARVIS v3.0 — Frontend logic

const ORB_STATE = { STANDBY: 0, LISTENING: 1, THINKING: 2, SPEAKING: 3, FOLLOWUP: 4 };

let ws = null;
let sessionId = null;
let isConnected = false;
let thinkingEl = null;

const msgList   = document.getElementById('msg-list');
const msgOverlay = document.getElementById('msg-overlay');
const textInput = document.getElementById('text-input');
const sendBtn   = document.getElementById('send-btn');
const stopBtn   = document.getElementById('stop-btn');
const connDot   = document.getElementById('conn-dot');
const stateDot  = document.getElementById('state-dot');
const stateText = document.getElementById('state-text');

// ── Settings panel ────────────────────────────────────────

const settingsBtn      = document.getElementById('settings-btn');
const settingsPanel    = document.getElementById('settings-panel');
const settingsBackdrop = document.getElementById('settings-backdrop');
const alwaysListeningCb = document.getElementById('always-listening-cb');
const hideCaptionsCb   = document.getElementById('hide-captions-cb');
const followupDurationSel = document.getElementById('followup-duration-sel');

function openSettings() {
  settingsPanel.classList.remove('panel-closed');
  settingsPanel.classList.add('panel-open');
  settingsBackdrop.classList.add('visible');
  settingsBtn.classList.add('open');
}

function closeSettings() {
  settingsPanel.classList.remove('panel-open');
  settingsPanel.classList.add('panel-closed');
  settingsBackdrop.classList.remove('visible');
  settingsBtn.classList.remove('open');
}

settingsBtn.addEventListener('click', () => {
  if (settingsPanel.classList.contains('panel-open')) {
    closeSettings();
  } else {
    openSettings();
  }
});

settingsBackdrop.addEventListener('click', closeSettings);

// ── Always-listening toggle ───────────────────────────────

// Restore from localStorage
alwaysListeningCb.checked = localStorage.getItem('alwaysListening') === '1';
window.alwaysListeningMode = alwaysListeningCb.checked;

alwaysListeningCb.addEventListener('change', () => {
  window.alwaysListeningMode = alwaysListeningCb.checked;
  localStorage.setItem('alwaysListening', alwaysListeningCb.checked ? '1' : '0');
});

// ── Hide captions toggle ──────────────────────────────────

hideCaptionsCb.checked = localStorage.getItem('hideCaptions') === '1';
if (hideCaptionsCb.checked) msgOverlay.classList.add('hidden');

hideCaptionsCb.addEventListener('change', () => {
  if (hideCaptionsCb.checked) {
    msgOverlay.classList.add('hidden');
  } else {
    msgOverlay.classList.remove('hidden');
  }
  localStorage.setItem('hideCaptions', hideCaptionsCb.checked ? '1' : '0');
});

// ── Follow-up duration ────────────────────────────────────

const savedDuration = localStorage.getItem('followupDuration');
if (savedDuration !== null) followupDurationSel.value = savedDuration;

followupDurationSel.addEventListener('change', () => {
  localStorage.setItem('followupDuration', followupDurationSel.value);
});

// Exposed so voice.js can read it
window.getFollowupDuration = () => parseInt(followupDurationSel.value, 10);

// ── Stop button ───────────────────────────────────────────

stopBtn.addEventListener('click', () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'interrupt' }));
  } else {
    fetch('/api/interrupt', { method: 'POST' }).catch(() => {});
  }
  stopBtn.style.display = 'none';
  setStatus('STANDBY', ORB_STATE.STANDBY);
});

// ── WebSocket ──────────────────────────────────────────────

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws`);
  window._jarvisWS = ws;

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
        setStatus('SPEAKING', ORB_STATE.SPEAKING);
        stopBtn.style.display = 'flex';
        if (typeof window.muteDuringSpeech === 'function') window.muteDuringSpeech();
        break;

      case 'response':
        hideThinking();
        addMsg('assistant', msg.text);
        if (typeof window.muteDuringSpeech === 'function') window.muteDuringSpeech();
        break;

      case 'speaking_done':
        stopBtn.style.display = 'none';
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
    stopBtn.style.display = 'none';
    setStatus('RECONNECTING', ORB_STATE.STANDBY);
    setTimeout(connect, 3000);
  };
}

// ── Send message ──────────────────────────────────────────

function send(text) {
  text = text.trim();
  if (!text) return;
  textInput.value = '';
  if (typeof window.cancelFollowup === 'function') window.cancelFollowup();
  addMsg('user', text);

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'chat', text }));
    setStatus('THINKING', ORB_STATE.THINKING);
    showThinking();
  } else {
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
  msgList.querySelectorAll('.tool-indicator').forEach(e => e.remove());
}

// ── Status pill ───────────────────────────────────────────

const DOT_CLASS = {
  [ORB_STATE.STANDBY]:  'standby',
  [ORB_STATE.LISTENING]:'active',
  [ORB_STATE.THINKING]: 'active',
  [ORB_STATE.SPEAKING]: 'speaking',
  [ORB_STATE.FOLLOWUP]: 'active',
};

function setStatus(text, orbState) {
  stateText.textContent = text;
  stateDot.className = DOT_CLASS[orbState] || 'dot-standby';
  if (typeof setOrbState === 'function') setOrbState(orbState);
}

// ── Events ────────────────────────────────────────────────

sendBtn.addEventListener('click', () => send(textInput.value));
textInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(textInput.value); }
});

// Callbacks for voice.js
window.onVoiceStart  = () => setStatus('LISTENING', ORB_STATE.LISTENING);
window.onVoiceEnd    = () => setStatus('STANDBY',   ORB_STATE.STANDBY);
window.onVoiceResult = (text) => send(text);

window.onFollowupTick = (secsLeft) => {
  setStatus(`FOLLOW UP  ${secsLeft}s`, ORB_STATE.FOLLOWUP);
};
window.onFollowupEnd = () => {
  setStatus('STANDBY', ORB_STATE.STANDBY);
};

// ── Start overlay ─────────────────────────────────────────

const startOverlay = document.getElementById('start-overlay');
const startBtn     = document.getElementById('start-btn');
const startStatus  = document.getElementById('start-status');

window.startJarvis = async function () {
  startBtn.disabled = true;
  startStatus.textContent = 'requesting microphone...';
  startStatus.className = '';

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach(t => t.stop());
    startStatus.textContent = 'microphone granted — connecting...';
    startStatus.className = 'ok';
  } catch (err) {
    startStatus.textContent = 'microphone denied — voice won\'t work, continuing anyway';
    startStatus.className = 'err';
    await new Promise(r => setTimeout(r, 1500));
  }

  connect();
};

// Hide overlay once WebSocket opens
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
  // Auto-reload when a new service worker takes over (clears stale cache)
  navigator.serviceWorker.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'SW_UPDATED') {
      console.log('[SW] New service worker active — reloading for fresh assets');
      window.location.reload();
    }
  });
}
