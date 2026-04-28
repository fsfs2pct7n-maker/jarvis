"""Wake word detection — Python-side using faster-whisper.

Architecture:
  - Wake detection: 0.5s rolling buffer chunks for fast response
  - Command capture: VAD-based — stops when you stop talking (not fixed window)
  - Silence gate: RMS check skips whisper on quiet frames (saves CPU)
  - Pauses automatically during TTS playback to prevent feedback loops

Falls back gracefully: if PyAudio or faster-whisper are unavailable,
logs and returns — browser Web Speech API is the fallback.
"""
import os
import threading
import struct
import math
import time
from typing import Callable

WAKE_PHRASES      = ["hey jarvis", "jarvis", "hey, jarvis"]
CHUNK_SIZE        = 1024        # frames per PyAudio read
SAMPLE_RATE       = 16000       # whisper expects 16kHz
WAKE_CHUNK_SECS   = 0.5         # detection window — smaller = faster response
SILENCE_RMS       = 150         # below this = silence, skip whisper
MIC_DEVICE        = None        # None = default input device

# VAD command capture settings
CMD_SPEECH_RMS    = 200         # RMS to consider as "speech" (slightly higher than silence gate)
CMD_SILENCE_SECS  = 1.2         # seconds of silence to end command capture
CMD_MAX_SECS      = 8.0         # hard cap: never record longer than this


_detector  = None
_stop_flag = threading.Event()
_speaking  = threading.Event()   # set while TTS is playing — pause detection


def get_detector():
    return _detector


def set_speaking(active: bool):
    """Call this when TTS starts/stops so wake word is muted during playback."""
    if active:
        _speaking.set()
    else:
        _speaking.clear()


def _rms(data: bytes) -> float:
    count = len(data) // 2
    if count == 0:
        return 0.0
    shorts = struct.unpack(f"{count}h", data)
    return math.sqrt(sum(s * s for s in shorts) / count)


def _read_chunk(stream, secs: float) -> bytes:
    """Read exactly `secs` seconds of audio from the stream."""
    num_reads = int(SAMPLE_RATE * secs / CHUNK_SIZE)
    frames = []
    for _ in range(num_reads):
        try:
            frames.append(stream.read(CHUNK_SIZE, exception_on_overflow=False))
        except Exception:
            pass
    return b"".join(frames)


def _numpy_from_bytes(raw: bytes):
    import numpy as np
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    return arr / 32768.0


def _transcribe(model, raw: bytes) -> str:
    audio = _numpy_from_bytes(raw)
    segs, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=True)
    return " ".join(s.text for s in segs).strip().lower()


def _capture_command(stream) -> bytes:
    """
    VAD-based command capture: record until CMD_SILENCE_SECS of quiet
    or CMD_MAX_SECS total. Returns the full audio bytes.

    This avoids the fixed 6s wait — Jarvis responds as soon as you stop talking.
    """
    chunk_secs    = CHUNK_SIZE / SAMPLE_RATE           # ~0.064s per chunk read
    max_chunks    = int(CMD_MAX_SECS / chunk_secs)
    silence_limit = int(CMD_SILENCE_SECS / chunk_secs)

    frames          = []
    silent_chunks   = 0
    heard_speech    = False

    for _ in range(max_chunks):
        try:
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        except Exception:
            continue

        frames.append(data)
        level = _rms(data)

        if level >= CMD_SPEECH_RMS:
            heard_speech  = True
            silent_chunks = 0
        elif heard_speech:
            silent_chunks += 1
            if silent_chunks >= silence_limit:
                break   # user has stopped talking — done

    return b"".join(frames) if heard_speech else b""


def _detection_loop(model, stream, on_wake: Callable, on_speech: Callable):
    print("[WAKE] Python wake word detector active — listening for 'Hey Jarvis'")
    while not _stop_flag.is_set():
        # Pause while TTS is playing — prevents feedback loop
        if _speaking.is_set():
            time.sleep(0.05)
            continue

        raw = _read_chunk(stream, WAKE_CHUNK_SECS)
        if _rms(raw) < SILENCE_RMS:
            continue   # silent — skip whisper entirely

        try:
            text = _transcribe(model, raw)
        except Exception as e:
            print(f"[WAKE] Transcription error: {e}")
            continue

        if not text:
            continue

        if any(p in text for p in WAKE_PHRASES):
            print(f"[WAKE] Wake phrase detected: '{text}'")
            on_wake()

            # Brief pause for chime; then immediately start VAD capture
            time.sleep(0.4)

            cmd_raw = _capture_command(stream)
            if not cmd_raw:
                print("[WAKE] No speech heard after wake word — resuming detection")
                continue

            try:
                cmd_text = _transcribe(model, cmd_raw)
            except Exception:
                cmd_text = ""

            # Strip any echoed wake phrase from the transcription
            for p in WAKE_PHRASES:
                cmd_text = cmd_text.replace(p, "").strip()

            if cmd_text:
                print(f"[WAKE] Command: '{cmd_text}'")
                on_speech(cmd_text)
            else:
                print("[WAKE] Command transcription empty — resuming detection")


def init_wake_word(on_wake: Callable, on_speech: Callable):
    """Start the Python wake word detector in a background thread.

    on_wake()          — called when 'Hey Jarvis' is detected
    on_speech(text)    — called with the transcribed follow-up command

    Returns the thread if started, None if falling back to browser.
    """
    global _detector

    try:
        import pyaudio
        import numpy  # noqa: F401
        from faster_whisper import WhisperModel
    except ImportError as e:
        print(f"[WAKE] Missing dependency ({e}) — browser Web Speech API active.")
        return None

    try:
        model = WhisperModel(
            "tiny.en", device="cpu", compute_type="int8",
            download_root=os.path.expanduser("~/.cache/whisper"),
        )
        print("[WAKE] Whisper tiny.en loaded.")
    except Exception as e:
        print(f"[WAKE] Failed to load whisper model: {e} — browser fallback active.")
        return None

    try:
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=MIC_DEVICE,
            frames_per_buffer=CHUNK_SIZE,
        )
    except Exception as e:
        print(f"[WAKE] Microphone open failed: {e} — browser fallback active.")
        return None

    _stop_flag.clear()
    t = threading.Thread(
        target=_detection_loop,
        args=(model, stream, on_wake, on_speech),
        daemon=True,
    )
    t.start()
    _detector = t
    print("[WAKE] Microphone active (faster-whisper tiny.en — Python side)")
    return t
