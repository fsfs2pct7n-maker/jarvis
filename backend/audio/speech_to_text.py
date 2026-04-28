"""Speech to Text — delegated entirely to browser Web Speech API.

All STT now runs in the browser (zero Mac RAM, instant, no model loading).
This file is kept as a stub so existing imports don't break.
"""


def transcribe_audio(_audio_data: bytes, _sample_rate: int = 16000) -> str:
    """No-op — STT handled by browser."""
    return ""


def transcribe_file(_file_path: str) -> str:
    """No-op — STT handled by browser."""
    return ""


class MicrophoneRecorder:
    """No-op — microphone handled by browser."""

    def record_until_silence(self, _max_duration: int = 30) -> bytes:
        return b""

    def record_chunk(self, _duration: float = 2.0) -> bytes:
        return b""
