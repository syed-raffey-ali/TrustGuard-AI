"""FULL AUDIO end-to-end test — real speech through the whole live pipeline.

Streams espeak-synthesized PCM16/16 kHz scam speech over the call WebSocket
(exactly what the Android AudioEngine sends), then watches the risk channel
for: transcript_segment captions, fast-tier (ML) risk updates, and the final
Tier-2 confirmed score.

Prerequisites: gateway running on :8080  (bash scripts/run_gateway.sh)

Usage:  .venv/bin/python scripts/test_voice_audio.py
"""
import asyncio
import json
import sys
import time

import websockets

sys.path.insert(0, ".")
from _tts import synth_pcm16_16k  # noqa: E402

BASE = "ws://localhost:8080"
SESSION = "voice_audio_test_001"
CALLER = "+92 321 9876543"          # mobile number claiming to be HBL

SCAM_SCRIPT = [
    "Hello sir, this is HBL bank security department calling you.",
    "Sir, we have detected a suspicious transaction on your account.",
    "Your account will be blocked within one hour.",
    "Please tell me the OTP code you received on your phone right now, quickly.",
]


async def stream_audio(ws, pcm: bytes, chunk_bytes: int = 3200) -> None:
    """Stream PCM like the phone does: 100 ms frames in real time."""
    for i in range(0, len(pcm), chunk_bytes):
        await ws.send(pcm[i : i + chunk_bytes])
        await asyncio.sleep(chunk_bytes / 32000.0)   # real-time pacing


async def main() -> None:
    risk_events: list[dict] = []
    transcripts: list[str] = []
    t_start = time.time()

    async with websockets.connect(f"{BASE}/ws/session/{SESSION}/risk") as risk_ws:
        async with websockets.connect(f"{BASE}/ws/call/{SESSION}") as call_ws:
            await call_ws.send(json.dumps({
                "type": "caller_id", "caller_number": CALLER,
            }))

            async def read_risk() -> None:
                try:
                    while True:
                        raw = await risk_ws.recv()
                        evt = json.loads(raw)
                        if evt.get("type") == "transcript_segment":
                            transcripts.append(evt["text"])
                            print(f"[caption {time.time()-t_start:5.1f}s] "
                                  f"({evt['speaker']}) {evt['text'][:80]}")
                        elif "score" in evt or "band" in evt:
                            risk_events.append(evt)
                            print(f"[risk    {time.time()-t_start:5.1f}s] "
                                  f"score={evt.get('score')} band={evt.get('band')} "
                                  f"signals={[s['type'] for s in evt.get('delta_signals', [])][:4]}")
                except websockets.ConnectionClosed:
                    pass

            reader = asyncio.create_task(read_risk())

            # synthesize + stream the scam script in real time (with pauses)
            for line in SCAM_SCRIPT:
                pcm = synth_pcm16_16k(line)
                await stream_audio(call_ws, pcm)
                await asyncio.sleep(1.0)             # natural pause between lines

            # let STT (5 s cadence) + fast score + Tier-2 finish
            await asyncio.sleep(30)
            reader.cancel()

    print("\n--- results ---")
    print(f"captions received: {len(transcripts)}")
    for t in transcripts:
        print(f"  - {t}")
    assert risk_events, "no risk updates received"
    final = risk_events[-1]
    print(f"final: score={final.get('score')} band={final.get('band')}")
    ok = final.get("band") in ("high", "critical") and transcripts
    print("AUDIO E2E:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


asyncio.run(main())
