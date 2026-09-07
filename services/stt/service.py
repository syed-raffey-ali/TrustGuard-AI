"""Streaming STT service — Build Bible Sections 6, 11.

faster-whisper (CTranslate2), small on CPU / medium+ if GPU. The gateway feeds
16 kHz mono PCM16 rolling windows; this returns partial transcripts as
speaker-tagged segments. Lazy-loads the model so the whole backend still runs
when faster-whisper isn't installed (text-only demo mode).
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Optional

MODEL_FAST = os.getenv("STT_MODEL_FAST", "tiny")   # English windows
MODEL_QUALITY = os.getenv("STT_MODEL", "base")     # Urdu / roman-Urdu windows
# Dual-model strategy (measured on the i5-4200U): 'tiny' handles English
# 2.5 s windows in ~1.1–1.9 s (keeps up with live speech) but mangles
# synthetic/real Urdu; 'base' romanises Urdu well but needs ~4–5 s per
# window, so it only serves non-English peers on 4 s windows. Detection
# windows (language=None) use the FAST model — all we need from them is
# the en/non-en split, and it keeps the first caption quick.
_loaded_models: dict = {}
_load_lock = asyncio.Lock()


@dataclass
class Segment:
    speaker: str
    text: str
    start_ms: int
    end_ms: int
    language: str


def _load(name: str):
    if name in _loaded_models:
        return _loaded_models[name]
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("[stt] faster-whisper not installed — voice transcript disabled")
        return None
    device = "cpu"
    compute = os.getenv("STT_COMPUTE_TYPE", "int8")
    print(f"[stt] loading faster-whisper '{name}' on {device} ({compute})…")
    model = WhisperModel(name, device=device, compute_type=compute)
    _loaded_models[name] = model
    return model


def pcm16_to_float32(pcm: bytes):
    import numpy as np

    return np.frombuffer(pcm, dtype=np.int16).astype("float32") / 32768.0


async def transcribe_window(
    pcm_bytes: bytes,
    speaker: str = "them",
    offset_ms: int = 0,
    language: Optional[str] = None,
    use_vad: bool = False,
) -> list[Segment]:
    """Transcribe one audio window (blocking CT2 call offloaded to a thread).

    language: pinned whisper language code for steady-state windows. None
    means auto-detect — only trustworthy on a peer's first (longer, VAD'd)
    window; per-window detection on short clips is slow and unreliable.
    use_vad: enable silero VAD (used on the language-detection window).
    """
    name = MODEL_FAST if language == "en" else MODEL_QUALITY
    if language is None:
        name = MODEL_FAST      # detection window: fast, en/non-en split only
    model = await _ensure_loaded(name)
    if model is None or not pcm_bytes:
        return []

    def run() -> list[Segment]:
        audio = pcm16_to_float32(pcm_bytes)
        segments, info = model.transcribe(
            audio,
            beam_size=1,
            temperature=0.0,             # no sampling-fallback cascade — the
            # default retry ladder made one bad window take 73 s (measured)
            vad_filter=use_vad,
            language=language,           # None => auto-detect (first window)
            condition_on_previous_text=False,
        )
        out = []
        base = time.time()
        for seg in segments:
            out.append(
                Segment(
                    speaker=speaker,
                    text=seg.text.strip(),
                    start_ms=offset_ms + int(seg.start * 1000),
                    end_ms=offset_ms + int(seg.end * 1000),
                    language=(info.language or "mixed") if info else "mixed",
                )
            )
        return [s for s in out if s.text]

    return await asyncio.get_running_loop().run_in_executor(None, run)


async def _ensure_loaded(name: str):
    async with _load_lock:
        return await asyncio.get_running_loop().run_in_executor(None, _load, name)


async def preload() -> None:
    """Warm both models at gateway startup.

    CT2 int8 engine init takes ~15 s for 'base' on the i5-4200U — without
    this, the FIRST call of the day pays it as a 16 s caption stall.
    """
    loop = asyncio.get_running_loop()
    async with _load_lock:
        await loop.run_in_executor(None, _load, MODEL_FAST)
        await loop.run_in_executor(None, _load, MODEL_QUALITY)


def is_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False
