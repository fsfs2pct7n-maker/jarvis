"""Text to Speech — streaming sentence-by-sentence with Fish Audio prefetch.

Architecture:
  StreamingSpeaker runs two threads:
    _fetcher  — pulls sentences from a queue, requests Fish Audio (or tags as 'say')
    _player   — pulls (kind, data) from audio queue, plays immediately

  While sentence 1 is playing, Fish Audio is already fetching sentence 2.
  First word plays within ~1s of first sentence being added.

  Cancellation tokens prevent stale audio from playing after a new response arrives.
"""
import os
import queue
import re
import subprocess
import tempfile
import threading
import requests


FISH_API_URL  = "https://api.fish.audio/v1/tts"
FISH_RETRIES  = 2   # 1 attempt + 1 retry before falling back to say


def _set_speaking(active: bool):
    """Notify the wake word detector that audio is playing/stopped."""
    try:
        from backend.audio.wake_word import set_speaking
        set_speaking(active)
    except Exception:
        pass

# Active token tracking (for single-shot speak() calls)
_token_counter = 0
_token_lock    = threading.Lock()
_current_token = None
_current_proc  = None
_proc_lock     = threading.Lock()


# ── Public token API ──────────────────────────────────────

class SpeechToken:
    __slots__ = ("id", "cancelled")
    def __init__(self, tid: int):
        self.id        = tid
        self.cancelled = False


def new_token() -> SpeechToken:
    """Mint a new token. Cancels the current one and kills any playing audio."""
    global _token_counter, _current_token
    with _token_lock:
        _token_counter += 1
        if _current_token:
            _current_token.cancelled = True
        tok = SpeechToken(_token_counter)
        _current_token = tok
    _kill_proc()
    return tok


# ── StreamingSpeaker ──────────────────────────────────────

class StreamingSpeaker:
    """
    Add sentences one at a time; they play as soon as audio is ready.
    Fish Audio sentence N+1 is being fetched while sentence N is playing.

    Usage:
        tok     = new_token()
        speaker = StreamingSpeaker(tok)
        speaker.add("Hello Owen.")
        speaker.add("Your email looks clear today.")
        speaker.finish()      # blocks until all audio played (or cancelled)
    """

    def __init__(self, token: SpeechToken):
        self.token   = token
        self._text_q  = queue.Queue()   # str sentences  → _fetcher
        self._audio_q = queue.Queue()   # ("bytes"|"say", data) → _player

        self._fetcher_t = threading.Thread(target=self._fetcher, daemon=True)
        self._player_t  = threading.Thread(target=self._player,  daemon=True)
        self._fetcher_t.start()
        self._player_t.start()

    def add(self, sentence: str):
        sentence = sentence.strip()
        if sentence:
            self._text_q.put(sentence)

    def finish(self):
        """Signal done and block until all queued audio has played."""
        self._text_q.put(None)
        self._player_t.join(timeout=120)

    def cancel(self):
        self.token.cancelled = True
        self._text_q.put(None)
        self._audio_q.put(None)

    # ── Fetcher thread ────────────────────────────────────

    def _fetcher(self):
        while True:
            sentence = self._text_q.get()
            if sentence is None or self.token.cancelled:
                self._audio_q.put(None)
                return

            fish_key = _get_fish_key()
            audio_bytes = None

            if fish_key:
                for attempt in range(1, FISH_RETRIES + 1):
                    try:
                        resp = requests.post(
                            FISH_API_URL,
                            json={
                                "text":         sentence,
                                "reference_id": _get_fish_model(),
                                "format":       "mp3",
                                "normalize":    True,
                                "latency":      "normal",
                            },
                            headers={
                                "Authorization": f"Bearer {fish_key}",
                                "Content-Type":  "application/json",
                            },
                            timeout=8,
                        )
                        if resp.status_code == 200:
                            print(f"[TTS] Fish Audio success (attempt {attempt})")
                            audio_bytes = resp.content
                            break
                        else:
                            print(f"[TTS] Fish Audio failed — HTTP {resp.status_code} (attempt {attempt}/{FISH_RETRIES})")
                    except Exception as e:
                        print(f"[TTS] Fish Audio failed — {e} (attempt {attempt}/{FISH_RETRIES})")

            if audio_bytes:
                # Pass both bytes AND original text so player can fall back to say if afplay fails
                self._audio_q.put(("bytes", audio_bytes, sentence))
            else:
                if fish_key:
                    print(f"[TTS] All Fish Audio attempts failed, falling back to say.")
                self._audio_q.put(("say", sentence, sentence))

    # ── Player thread ─────────────────────────────────────

    def _player(self):
        _muted = False
        while True:
            item = self._audio_q.get()
            if item is None or self.token.cancelled:
                if _muted:
                    _set_speaking(False)
                return
            kind, data, text = item
            if self.token.cancelled:
                if _muted:
                    _set_speaking(False)
                return
            # Mute the mic on the very first audio play
            if not _muted:
                _set_speaking(True)
                _muted = True
            if kind == "bytes":
                success = _play_bytes(data, self.token)
                if not success and not self.token.cancelled:
                    _say(text, self.token)
            else:
                _say(text, self.token)


# ── Convenience: single-shot speak() ─────────────────────

def speak(text: str, blocking: bool = False):
    """Speak a complete text block — cancels anything currently playing."""
    if not text or not text.strip():
        return
    tok = new_token()
    sentences = _split_sentences(_clean(text))

    def _run():
        s = StreamingSpeaker(tok)
        for sentence in sentences:
            s.add(sentence)
        s.finish()

    if blocking:
        _run()
    else:
        threading.Thread(target=_run, daemon=True).start()


# ── Low-level playback helpers ────────────────────────────

def _play_bytes(audio_bytes: bytes, token: SpeechToken) -> bool:
    """Play MP3 bytes via afplay. Returns True on success, False if afplay failed."""
    tmp = tempfile.mktemp(suffix=".mp3")
    try:
        with open(tmp, "wb") as f:
            f.write(audio_bytes)
        if token.cancelled:
            return True  # cancelled, not a failure
        proc = subprocess.Popen(["afplay", tmp], stderr=subprocess.PIPE)
        _register_proc(proc, token)
        proc.wait()
        if proc.returncode != 0 and not token.cancelled:
            stderr = proc.stderr.read().decode(errors="replace").strip()
            print(f"[TTS] afplay failed (rc={proc.returncode}): {stderr}")
            return False
        return True
    except Exception as e:
        print(f"[TTS] afplay error: {e}")
        return False
    finally:
        _unregister_proc()
        try:
            os.unlink(tmp)
        except Exception:
            pass


def _say(text: str, token: SpeechToken):
    if token.cancelled:
        return
    proc = subprocess.Popen(["say", "-v", "Alex", "-r", "185", text])
    _register_proc(proc, token)
    proc.wait()
    _unregister_proc()


def _register_proc(proc: subprocess.Popen, token: SpeechToken):
    global _current_proc
    with _proc_lock:
        _current_proc = proc
    if token.cancelled:
        _kill_proc()


def _unregister_proc():
    global _current_proc
    with _proc_lock:
        _current_proc = None


def _kill_proc():
    global _current_proc
    with _proc_lock:
        proc, _current_proc = _current_proc, None
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=0.3)
        except Exception:
            proc.kill()
    subprocess.run(["pkill", "-x", "afplay"], capture_output=True)
    subprocess.run(["pkill", "-x", "say"],    capture_output=True)


# ── Text helpers ──────────────────────────────────────────

def _get_fish_key()   -> str: return os.getenv("FISH_AUDIO_API_KEY",  "")
def _get_fish_model() -> str: return os.getenv("FISH_AUDIO_MODEL_ID", "612b878b113047d9a770c069c8b4fdfe")


def _clean(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*',     r'\1', text)
    text = re.sub(r'`(.+?)`',       r'\1', text)
    text = re.sub(r'#{1,6}\s+',     '',    text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    text = re.sub(r'^\s*[-*+]\s+',     '',    text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+',     '',    text, flags=re.MULTILINE)
    text = re.sub(r'\n{2,}', ' ', text)
    return text.strip()


def _split_sentences(text: str) -> list:
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


def extract_sentences(buffer: str):
    """Return (complete_sentences, remaining_buffer). Used during streaming."""
    parts = re.split(r'(?<=[.!?])\s+', buffer)
    if len(parts) <= 1:
        return [], buffer
    complete  = [p.strip() for p in parts[:-1] if p.strip()]
    remaining = parts[-1]
    return complete, remaining


# ── Misc ──────────────────────────────────────────────────

def play_chime():
    subprocess.Popen(["afplay", "/System/Library/Sounds/Ping.aiff"])


def stop_speaking():
    """Public: stop all audio immediately."""
    new_token()   # cancels current and kills proc
