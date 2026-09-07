"""In-memory audio ingest + rolling STT hand-off for the voice path.

Raw PCM16 frames are held ONLY in rolling in-memory buffers (privacy rule:
no raw audio persisted, Bible Section 17). Every STT_INTERVAL_S the voice
loop drains each peer's buffer (consuming it — audio is transcribed once),
hands it to the streaming STT service (services/stt) and feeds the resulting
segments into the live scoring pipeline. The STT service is imported lazily
so the gateway still runs when faster-whisper is not installed.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque

_BUFFERS: dict[str, deque[tuple[float, bytes]]] = {}
_LOCK = asyncio.Lock()
MAX_BUFFER_SECONDS = 90.0          # rolling window; discarded after transcription


async def _put(session_id: str, item: tuple[float, bytes]) -> None:
    async with _LOCK:
        buf = _BUFFERS.setdefault(session_id, deque())
        buf.append(item)
        total = sum(len(b) for _, b in buf)
        # 32000 bytes/sec at 16 kHz PCM16 mono
        while total > MAX_BUFFER_SECONDS * 32000 and buf:
            _, dropped = buf.popleft()
            total -= len(dropped)


def ingest_audio(session_id: str, peer_id: str, frame: bytes) -> None:
    """Called from WS receive loop with a binary PCM16 chunk."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_put(f"{session_id}:{peer_id}", (time.time(), frame)))
    except RuntimeError:
        pass


def peer_keys(session_id: str) -> list[str]:
    """All buffered peer streams for a call session (order of first audio)."""
    prefix = f"{session_id}:"
    return [k for k in _BUFFERS if k.startswith(prefix)]


def buffered_bytes(session_key: str) -> int:
    """Un-transcribed bytes waiting for one peer (non-consuming peek)."""
    buf = _BUFFERS.get(session_key)
    return sum(len(b) for _, b in buf) if buf else 0


async def drain_new(session_key: str) -> bytes:
    """Pop and return all un-transcribed chunks for one peer, concatenated.

    Consuming semantics: transcribed audio is never re-transcribed, so live
    captions never duplicate and CPU is spent once per second of speech.
    """
    async with _LOCK:
        buf = _BUFFERS.get(session_key)
        if not buf:
            return b""
        pcm = b"".join(data for _, data in buf)
        buf.clear()
        return pcm


async def drain_window(session_id: str, seconds: float = 30.0) -> list[bytes]:
    """Non-consuming read of recent chunks (kept for the paste/replay tools)."""
    cutoff = time.time() - seconds
    async with _LOCK:
        buf = _BUFFERS.get(session_id)
        if not buf:
            return []
        return [data for ts, data in buf if ts >= cutoff]


def drop_session(session_id: str) -> None:
    """Clear every peer buffer belonging to a session (call teardown)."""
    prefix = f"{session_id}:"
    for key in [k for k in _BUFFERS if k.startswith(prefix) or k == session_id]:
        _BUFFERS.pop(key, None)
