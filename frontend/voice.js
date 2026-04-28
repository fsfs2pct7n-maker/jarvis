// JARVIS Voice — Web Speech API
// Modes: WATCHING | COMMANDING | FOLLOWUP

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const voiceBtn = document.getElementById('voice-btn');
const micDot   = document.getElementById('mic-dot');
const micLabel = document.getElementById('mic-label');

if (!SR) {
  voiceBtn.style.opacity = '0.3';
  voiceBtn.title = 'Voice requires Chrome or Safari';
}

// ── Mic indicator ─────────────────────────────────────────

function setMicState(state) {
  micDot.className   = 'mic-' + state;
  micLabel.textContent = {
    off:      'MIC OFF',
    watching: 'WATCHING',
    active:   'LISTENING',
    error:    'MIC DENIED',
  }[state] || 'MIC OFF';
}

// ── State ─────────────────────────────────────────────────

let mode         = 'WATCHING';
let watchRecog   = null;
let watchRestart = null;
let cmdRecog     = null;

const WAKE_PHRASES = ['hey jarvis', 'jarvis', 'hey, jarvis'];

function containsWake(text) {
  return WAKE_PHRASES.some(p => text.toLowerCase().includes(p));
}

// Follow-up duration — reads live from the settings select (via app.js helper)
function getFollowupDuration() {
  if (typeof window.getFollowupDuration === 'function') {
    const d = window.getFollowupDuration();
    return isNaN(d) ? 15 : d;
  }
  return 15;
}

// ── Wake-word watcher ─────────────────────────────────────

function startWatcher() {
  if (mode !== 'WATCHING') return;
  if (watchRecog) return;

  if (!SR) return;
  watchRecog = new SR();
  watchRecog.continuous     = true;
  watchRecog.interimResults = false;
  watchRecog.lang           = 'en-US';

  watchRecog.onstart = () => {
    setMicState('watching');
  };

  watchRecog.onresult = (e) => {
    if (mode !== 'WATCHING') return;
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const text = e.results[i][0].transcript.trim();
      if (!text) continue;

      // Always-listening mode: treat any speech as a command
      if (window.alwaysListeningMode) {
        console.log('[JARVIS] Always-listening — sending:', text);
        stopWatcher();
        mode = 'WATCHING';  // stays in WATCHING; we skip command recog phase
        if (window.onVoiceStart)  window.onVoiceStart();
        if (window.onVoiceResult) window.onVoiceResult(text);
        if (window.onVoiceEnd)    window.onVoiceEnd();
        setTimeout(startWatcher, 400);
        return;
      }

      // Normal mode: check for wake phrase
      if (containsWake(text)) {
        console.log('[JARVIS] Wake word detected:', text);
        triggerWake();
        return;
      }
    }
  };

  watchRecog.onend = () => {
    watchRecog = null;
    if (mode !== 'WATCHING') return;
    setMicState('off');
    clearTimeout(watchRestart);
    watchRestart = setTimeout(startWatcher, 300);
  };

  watchRecog.onerror = (e) => {
    if (e.error === 'not-allowed') { setMicState('error'); return; }
    if (e.error === 'aborted') return;
  };

  try {
    watchRecog.start();
  } catch (_) {
    watchRecog = null;
    watchRestart = setTimeout(startWatcher, 500);
  }
}

function stopWatcher() {
  clearTimeout(watchRestart);
  watchRestart = null;
  if (watchRecog) {
    try { watchRecog.abort(); } catch (_) {}
    watchRecog = null;
  }
}

// ── Mute during TTS playback ──────────────────────────────

let _speakingWatchdog = null;

window.muteDuringSpeech = function () {
  stopWatcher();
  if (typeof window.cancelFollowup === 'function') window.cancelFollowup();
  try { cmdRecog && cmdRecog.abort(); } catch (_) {}
  cmdRecog = null;
  mode = 'WATCHING';
  setMicState('off');

  // Safety watchdog: if speaking_done never arrives, force-restart the watcher
  // after 45s so the mic doesn't stay dead permanently.
  clearTimeout(_speakingWatchdog);
  _speakingWatchdog = setTimeout(() => {
    if (mode === 'WATCHING' && !watchRecog) {
      console.warn('[JARVIS] speaking_done watchdog fired — restarting watcher');
      startWatcher();
    }
  }, 45000);
};

function _clearWatchdog() {
  clearTimeout(_speakingWatchdog);
  _speakingWatchdog = null;
}

// ── Wake trigger ──────────────────────────────────────────

function triggerWake() {
  if (mode !== 'WATCHING' && mode !== 'FOLLOWUP') return;
  if (mode === 'FOLLOWUP') window.cancelFollowup();

  mode = 'COMMANDING';
  stopWatcher();
  setMicState('active');
  voiceBtn.classList.add('active');

  if (window._jarvisWS && window._jarvisWS.readyState === WebSocket.OPEN) {
    window._jarvisWS.send(JSON.stringify({ type: 'wake_word' }));
  }
  if (window.onVoiceStart) window.onVoiceStart();
  startCommandRecog();
}

// ── Command recognition (one-shot) ───────────────────────

function startCommandRecog() {
  if (!SR) { endCommand(); return; }

  cmdRecog = new SR();
  cmdRecog.continuous     = false;
  cmdRecog.interimResults = false;
  cmdRecog.lang           = 'en-US';

  const input = document.getElementById('text-input');

  cmdRecog.onresult = (e) => {
    const text = Array.from(e.results).map(r => r[0].transcript).join(' ').trim();
    if (text) {
      input.value = '';
      if (window.onVoiceResult) window.onVoiceResult(text);
    }
  };

  cmdRecog.onend   = () => { input.value = ''; endCommand(); };
  cmdRecog.onerror = (e) => {
    if (e.error !== 'no-speech') console.log('[VOICE cmd]', e.error);
    endCommand();
  };

  try { cmdRecog.start(); } catch (_) { endCommand(); }
}

function endCommand() {
  try { cmdRecog && cmdRecog.abort(); } catch (_) {}
  cmdRecog = null;
  voiceBtn.classList.remove('active');
  if (window.onVoiceEnd) window.onVoiceEnd();
  mode = 'WATCHING';
  setTimeout(startWatcher, 400);
}

// ── Tap-to-talk ───────────────────────────────────────────

voiceBtn.addEventListener('click', () => {
  if (mode === 'COMMANDING') {
    try { cmdRecog && cmdRecog.stop(); } catch (_) {}
  } else {
    triggerWake();
  }
});

// ── Follow-up window ──────────────────────────────────────

let followupInterval = null;
let followupRecog    = null;

window.cancelFollowup = function (returnToStandby = false) {
  clearInterval(followupInterval);
  followupInterval = null;

  if (followupRecog) {
    try { followupRecog.abort(); } catch (_) {}
    followupRecog = null;
  }

  if (mode === 'FOLLOWUP') {
    mode = 'WATCHING';
    if (returnToStandby && window.onFollowupEnd) window.onFollowupEnd();
    setMicState('off');
    setTimeout(startWatcher, 300);
  }
};

window.startFollowup = function () {
  if (mode === 'COMMANDING') return;
  _clearWatchdog();  // speaking_done arrived — cancel the safety watchdog

  const duration = getFollowupDuration();
  if (duration === 0) {
    // Follow-up disabled — go straight back to watching
    mode = 'WATCHING';
    setMicState('off');
    setTimeout(startWatcher, 300);
    return;
  }

  window.cancelFollowup();
  mode = 'FOLLOWUP';
  stopWatcher();
  setMicState('watching');

  let secsLeft = duration;
  if (window.onFollowupTick) window.onFollowupTick(secsLeft);

  followupInterval = setInterval(() => {
    secsLeft--;
    if (window.onFollowupTick) window.onFollowupTick(secsLeft);
    if (secsLeft <= 0) window.cancelFollowup(true);
  }, 1000);

  if (!SR) { window.cancelFollowup(true); return; }

  const input = document.getElementById('text-input');

  followupRecog = new SR();
  followupRecog.continuous     = true;
  followupRecog.interimResults = false;
  followupRecog.lang           = 'en-US';

  followupRecog.onresult = (e) => {
    if (mode !== 'FOLLOWUP') return;
    const text = Array.from(e.results).slice(e.resultIndex).map(r => r[0].transcript).join(' ').trim();
    if (text) {
      input.value = '';
      window.cancelFollowup();
      mode = 'WATCHING';
      if (window.onVoiceResult) window.onVoiceResult(text);
    }
  };

  followupRecog.onend = () => {
    if (mode === 'FOLLOWUP' && followupRecog) {
      try { followupRecog.start(); } catch (_) {}
    }
  };

  followupRecog.onerror = (e) => {
    if (e.error !== 'no-speech' && e.error !== 'aborted') {
      console.log('[FOLLOWUP]', e.error);
    }
  };

  try { followupRecog.start(); } catch (_) { window.cancelFollowup(true); }
};

// ── Boot ──────────────────────────────────────────────────

function waitForWS() {
  if (window._jarvisWS && window._jarvisWS.readyState === WebSocket.OPEN) {
    startWatcher();
  } else {
    setTimeout(waitForWS, 300);
  }
}
waitForWS();
