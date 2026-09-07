#!/usr/bin/env python3
"""TrustGuard CALL pipeline test: real-time audio streaming over the call WS.

Two call clients per scenario (token-authed, like the app). The "scammer"
streams a synthesized 16 kHz PCM16 clip in real-time 100 ms chunks (exactly
what the Android AudioEngine sends). We measure:
  - first caption latency (speech start -> first transcript_segment)
  - caption text + detected language (Urdu must produce Urdu captions)
  - first scam alert latency (risk frame band>=medium) and alert_targets
  - echo-back: victim streams an OTP-echo clip afterwards; routing must
    stay victim-only.
"""
import asyncio
import json
import time
import uuid

import aiohttp
import websockets

BASE = "http://127.0.0.1:8080"
WS = "ws://127.0.0.1:8080"
SUF = uuid.uuid4().hex[:6]
DIG = "".join(c for c in SUF if c.isdigit()).ljust(5, "5")
CHUNK = 3200  # 100 ms of 16 kHz PCM16 mono (matches Android AudioEngine)

RESULTS = []


async def register(http, username, phone):
    r = await http.post(f"{BASE}/accounts/register", json={
        "username": username, "password": "TestPass123!",
        "display_name": username, "phone_number": phone})
    r.raise_for_status()
    return (await r.json())["token"]


async def invite(http, a, b):
    r = await http.post(f"{BASE}/api/v1/calls/invite",
                        json={"from_user": a, "to_user": b})
    r.raise_for_status()
    return (await r.json())["session_id"]


async def stream_clip(ws, pcm_path, t0, pace=0.1):
    with open(pcm_path, "rb") as fh:
        pcm = fh.read()
    for off in range(0, len(pcm), CHUNK):
        await ws.send(pcm[off:off + CHUNK])
        await asyncio.sleep(pace)
    return time.perf_counter() - t0  # stream end time


async def call_peer(name, token, sid, t0, clips):
    """Connect to the call WS, auth, stream clips in order."""
    ends = []
    async with websockets.connect(f"{WS}/ws/call/{sid}", max_size=None) as ws:
        await ws.recv()  # registered control frame
        await ws.send(json.dumps({"type": "control", "event": "start",
                                  "device_id": name, "token": token}))
        # stream clips, spaced; keep socket open afterwards
        for delay_before, clip in clips:
            await asyncio.sleep(delay_before)
            end_t = await stream_clip(ws, clip, t0)
            ends.append((clip, round(end_t, 2)))
            print(f"    [{name}] finished streaming {clip.split('/')[-1]} at {end_t:.1f}s")
        await asyncio.sleep(14)  # let STT + scoring finish
        try:
            await ws.send(json.dumps({"type": "control", "event": "end"}))
        except Exception:
            pass
    return ends


async def risk_collector(sid, t0, out):
    try:
        async with websockets.connect(f"{WS}/ws/session/{sid}/risk") as ws:
            while True:
                obj = json.loads(await asyncio.wait_for(ws.recv(), timeout=40))
                t = time.perf_counter() - t0
                if obj.get("type") == "transcript_segment":
                    out["captions"].append((round(t, 2), obj.get("username"),
                                            obj.get("language"), obj.get("text", "")[:80]))
                elif "band" in obj and (obj.get("score", 0) >= 20 or obj.get("band") != "low"):
                    out["alerts"].append((round(t, 2), obj["score"], obj["band"],
                                          obj.get("alert_targets", [])))
    except (asyncio.TimeoutError, websockets.ConnectionClosed):
        pass


async def scenario(http, idx, name, scam_clip, echo_clip=None, expect_alert=True):
    a, b = f"cl_a{idx}_{SUF}"[:20], f"cl_b{idx}_{SUF}"[:20]
    ta = await register(http, a, f"037{idx}1{DIG}"[:11])
    tb = await register(http, b, f"037{idx}2{DIG}"[:11])
    sid = await invite(http, a, b)
    t0 = time.perf_counter()
    out = {"captions": [], "alerts": []}
    a_clips = [(1.0, scam_clip)]
    b_clips = []
    if echo_clip:
        # victim echoes the OTP after the scam clip finishes (~17s + margin)
        b_clips = [(20.0, echo_clip)]
    await asyncio.gather(
        call_peer(a, ta, sid, t0, a_clips),
        call_peer(b, tb, sid, t0, b_clips),
        risk_collector(sid, t0, out),
    )
    first_alert = out["alerts"][0] if out["alerts"] else None
    rec = {
        "scenario": name,
        "captions": out["captions"],
        "first_caption_s": out["captions"][0][0] if out["captions"] else None,
        "languages": sorted({c[2] for c in out["captions"] if c[2]}),
        "alerted": first_alert is not None,
        "first_alert_s": first_alert[0] if first_alert else None,
        "first_band": first_alert[2] if first_alert else None,
        "targets_seen": sorted({tuple(al[3]) for al in out["alerts"]}),
        "expected_targets": [b],
        "victim_user": b,
        "scam_stream_end_s": None,
    }
    RESULTS.append(rec)
    print(f"[{name}] captions={len(out['captions'])} first_caption={rec['first_caption_s']}s "
          f"langs={rec['languages']} alert_at={rec['first_alert_s']}s band={rec['first_band']} "
          f"targets={rec['targets_seen']} (expect victim {b})")


async def main():
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as http:
        await scenario(http, 0, "call_en_bank_scam", "_test_audio/en_scam.pcm")
        await scenario(http, 1, "call_urdu_scam", "_test_audio/ur_scam.pcm")
        await scenario(http, 2, "call_safe_control", "_test_audio/en_safe.pcm")
        await scenario(http, 3, "call_echo_back", "_test_audio/en_scam.pcm",
                       echo_clip="_test_audio/en_echo.pcm")
    print("\n===== SUMMARY =====")
    print(json.dumps(RESULTS, indent=1, ensure_ascii=False))


asyncio.run(main())
