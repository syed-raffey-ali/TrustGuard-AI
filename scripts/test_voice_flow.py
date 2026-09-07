"""Live voice-flow integration test — run with the gateway up on :8080.

Simulates exactly what the STT loop produces: transcript_segment control
frames on a call WebSocket, while subscribed to the risk channel. Verifies
the voice rescore loop (Tier-1 + ML + Tier-2 + caller-ID) end-to-end.

Scam script: fake HBL caller on a mobile number (caller-ID mismatch),
mixed Urdu/English, OTP demand.

Usage:  .venv/bin/python scripts/test_voice_flow.py
"""
import asyncio
import json
import sys

import websockets

BASE = "ws://localhost:8080"
SESSION = "voice_test_live_001"
CALLER = "+92 300 1234567"          # mobile number claiming to be a bank

SEGMENTS = [
    ("them", "Assalam o alaikum, main HBL bank se call kar raha hoon, aap ke account se suspicious transaction hui hai."),
    ("me", "Kaun bol raha hai? Mujhe aisa koi message nahi aya."),
    ("them", "Sir, security ke liye jaldi karein. Aap ka account abhi block ho raha hai."),
    ("them", "Aap ko jo OTP aya hai woh turant bata dein, warna account block ho jayega aur paisay kho jayenge."),
]


async def main() -> None:
    risk_events: list[dict] = []

    async with websockets.connect(f"{BASE}/ws/session/{SESSION}/risk") as risk_ws:
        async with websockets.connect(f"{BASE}/ws/call/{SESSION}") as call_ws:
            # register with the scammer's caller number
            await call_ws.send(json.dumps({
                "type": "caller_id", "caller_number": CALLER,
            }))
            # drive the conversation like the STT loop would
            for i, (speaker, text) in enumerate(SEGMENTS):
                await call_ws.send(json.dumps({
                    "type": "transcript_segment", "speaker": speaker, "text": text,
                    "start_ms": i * 4000, "end_ms": i * 4000 + 3500,
                    "language": "mixed",
                }))

            # collect risk updates while the rescore loop runs
            deadline = asyncio.get_event_loop().time() + 45
            while asyncio.get_event_loop().time() < deadline:
                try:
                    remaining = max(0.05, deadline - asyncio.get_event_loop().time())
                    raw = await asyncio.wait_for(risk_ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                evt = json.loads(raw)
                if "score" in evt or "band" in evt:
                    risk_events.append(evt)
                    print(f"[risk] score={evt.get('score')} band={evt.get('band')} "
                          f"signals={[s['type'] for s in evt.get('delta_signals', [])][:4]}")
                    if evt.get("band") == "critical":
                        break

    assert risk_events, "no risk updates received"
    final = risk_events[-1]
    print(f"\nfinal: score={final.get('score')} band={final.get('band')}")
    print(f"total risk updates: {len(risk_events)}")
    ok = final.get("band") in ("high", "critical")
    print("VOICE FLOW:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


asyncio.run(main())
