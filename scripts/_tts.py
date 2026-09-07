"""Synthesize PCM16/16 kHz speech with libespeak-ng (ctypes) for live tests.

espeak-ng CLI isn't installed but libespeak-ng.so.1 + voice data are — drive
the C API directly. Output: 16 kHz mono PCM16 bytes, ready for the call
WebSocket (same format the Android AudioEngine streams).

Usage as a module:
    from _tts import synth_pcm16_16k
    pcm = synth_pcm16_16k("This is your bank calling", voice="en")
"""
from __future__ import annotations

import ctypes
import threading

TARGET_RATE = 16000

_lib = None
_lock = threading.Lock()


def _load():
    global _lib
    if _lib is not None:
        return _lib
    for name in ("libespeak-ng.so.1", "libespeak-ng.so"):
        try:
            _lib = ctypes.cdll.LoadLibrary(name)
            break
        except OSError:
            continue
    if _lib is None:
        raise RuntimeError("libespeak-ng not found")
    return _lib


def synth_pcm16_16k(text: str, voice: str = "en") -> bytes:
    """Synthesize text to 16 kHz mono PCM16 bytes."""
    lib = _load()
    with _lock:
        # callback: int (*)(short* wav, int numsamples, espeak_EVENT* events)
        chunks: list[bytes] = []

        @ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short),
                          ctypes.c_int, ctypes.c_void_p)
        def on_samples(wav, numsamples, events):
            if numsamples > 0:
                chunks.append(
                    ctypes.string_at(wav, numsamples * ctypes.sizeof(ctypes.c_short))
                )
            return 0

        AUDIO_OUTPUT_SYNCHRONOUS = 2
        rate = lib.espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, None, 0)
        if rate <= 0:
            raise RuntimeError(f"espeak_Initialize failed: {rate}")
        lib.espeak_SetSynthCallback(on_samples)
        if voice:
            v = voice.encode()
            lib.espeak_SetVoiceByName(ctypes.c_char_p(v))

        text_bytes = text.encode("utf-8")
        espeakCHARS_AUTO = 0
        lib.espeak_Synth(
            ctypes.c_char_p(text_bytes), len(text_bytes) + 1,
            0, 0, 0, espeakCHARS_AUTO, None, None,
        )
        lib.espeak_Synchronize()

    pcm = b"".join(chunks)
    return _resample(pcm, rate, TARGET_RATE)


def _resample(pcm16: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Linear-interpolation resample of int16 mono audio."""
    if src_rate == dst_rate or not pcm16:
        return pcm16
    import array

    samples = array.array("h")
    samples.frombytes(pcm16[: len(pcm16) - (len(pcm16) % 2)])
    n_src = len(samples)
    n_dst = int(n_src * dst_rate / src_rate)
    out = array.array("h")
    step = n_src / n_dst
    pos = 0.0
    for _ in range(n_dst):
        i = int(pos)
        frac = pos - i
        a = samples[i]
        b = samples[min(i + 1, n_src - 1)]
        out.append(int(a + (b - a) * frac))
        pos += step
    return out.tobytes()


if __name__ == "__main__":
    pcm = synth_pcm16_16k("Hello, this is a test of the speech system.")
    dur = len(pcm) / (TARGET_RATE * 2)
    print(f"synthesized {len(pcm)} bytes = {dur:.2f}s of 16 kHz PCM16")
