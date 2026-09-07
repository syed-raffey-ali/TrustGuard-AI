#!/usr/bin/env python3
"""TrustGuard chat scam-detection latency + routing test.

For each scenario: fresh user pair -> REST session -> both on chat WS +
risk WS -> scammer sends scripted lines -> measure:
  t_send -> ack (tier-1 inline), -> FIRST risk frame band>=medium (the alert),
  -> tier-2 refinement frames. Verifies victim-only routing (alert_targets)
  including the echo-back case (victim repeats the OTP).
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

RESULTS = []

SCENARIOS = [
    ("bank_otp_en", [
        "Hello, this is ApnaBank fraud department. We detected a suspicious transaction of Rs 50,000 on your account.",
        "Your account will be blocked within 30 minutes. I have sent a verification code to your number.",
        "Please tell me the OTP code immediately so I can stop this transaction. Do not share this call with anyone.",
    ]),
    ("prize_lottery_en", [
        "Congratulations! Your mobile number has won Rs 25 lakh in the Basant prize lucky draw.",
        "To release your prize you must pay a small processing fee of Rs 5,000 via Easypaisa today only.",
    ]),
    ("job_upfront_fee_en", [
        "We shortlisted you for a data-entry job, salary 80,000 per month, work from home.",
        "Before joining you must pay a refundable registration fee of 3,000 rupees to secure your seat.",
    ]),
    ("phishing_link_en", [
        "Your parcel is held at customs. Update your address here: http://bit.ly/3xFakeTrack to avoid return.",
    ]),
    ("roman_urdu_otp", [
        "Assalam o Alaikum, main ApnaBank fraud department se bol raha hoon. Aap ke account se suspicious transaction hui hai.",
        "Account block hone se pehle verification zaroori hai. Maine aap ke number par code bheja hai, woh OTP mujhe turant batao.",
        "Yeh baat kisi ko na batana, na family ko na branch walo ko. Confidential investigation hai.",
    ]),
    ("urdu_script", [
        "آپ کا اکاؤنٹ بلاک ہو گیا ہے۔ براہ کرم فوری طور پر او ٹی پی کوڈ بتائیں",
        "یہ بات کسی کو نہ بتانا، ورنہ آپ کا پیسہ ضبط ہو جائے گا",
    ]),
    ("safe_control", [
        "Assalam o Alaikum ami, kaisi ho? Dinner par kya banaya?",
        "The weather is nice today. Let's meet at 6 pm for tea.",
    ]),
]


DIGITS = "".join(c for c in SUF if c.isdigit()).ljust(5, "7")


async def register(session, username, phone):
    r = await session.post(f"{BASE}/accounts/register", json={
        "username": username, "password": "TestPass123!",
        "display_name": username, "phone_number": phone})
    r.raise_for_status()
    return (await r.json())["token"]


async def start_session(session, a, b):
    r = await session.post(f"{BASE}/api/v1/sessions/start",
                           json={"type": "chat", "device_a": a, "device_b": b})
    r.raise_for_status()
    return (await r.json())["session_id"]


class RiskCollector:
    def __init__(self, name):
        self.name = name
        self.alerts = []  # (t_offset, score, band, targets)

    async def run(self, sid, t0):
        try:
            async with websockets.connect(f"{WS}/ws/session/{sid}/risk") as ws:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=25)
                    obj = json.loads(raw)
                    if "band" not in obj:
                        continue
                    if obj.get("score", 0) >= 35 or obj.get("band") in ("medium", "high", "critical"):
                        self.alerts.append((time.perf_counter() - t0, obj["score"],
                                            obj["band"], obj.get("alert_targets", [])))
        except (asyncio.TimeoutError, websockets.ConnectionClosed):
            pass


async def chat_client(name, token, sid, lines, t0):
    async with websockets.connect(f"{WS}/ws/chat/{sid}") as ws:
        await ws.send(json.dumps({"type": "register", "device_id": name, "token": token}))
        await ws.recv()  # registered
        for line in lines:
            mid = f"m_{name}_{uuid.uuid4().hex[:8]}"
            t_send = time.perf_counter() - t0
            await ws.send(json.dumps({"type": "message", "text": line, "message_id": mid}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                obj = json.loads(raw)
                if obj.get("type") == "ack" and obj.get("message_id") == mid:
                    t_ack = time.perf_counter() - t0
                    RESULTS[-1]["acks_ms"].append(round((t_ack - t_send) * 1000))
                    RESULTS[-1]["tier1_hits"] += int(bool(obj.get("tier1_hits")))
                    break
            await asyncio.sleep(0.15)
        await asyncio.sleep(6)  # let risk frames arrive


async def victim_client(name, token, sid, t0):
    async with websockets.connect(f"{WS}/ws/chat/{sid}") as ws:
        await ws.send(json.dumps({"type": "register", "device_id": name, "token": token}))
        await ws.recv()
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=12)
        except (asyncio.TimeoutError, websockets.ConnectionClosed):
            pass


async def run_scenario(http, idx, name, lines):
    a = f"lt_a_{name[:6]}_{SUF}"[:20]
    b = f"lt_b_{name[:6]}_{SUF}"[:20]
    ta = await register(http, a, f"03{idx}1{DIGITS}")
    tb = await register(http, b, f"03{idx}2{DIGITS}")
    sid = await start_session(http, a, b)
    RESULTS.append({"scenario": name, "acks_ms": [], "tier1_hits": 0})
    t0 = time.perf_counter()
    risk_a, risk_b = RiskCollector(a), RiskCollector(b)
    await asyncio.gather(
        chat_client(a, ta, sid, lines, t0),
        victim_client(b, tb, sid, t0),
        risk_a.run(sid, t0),
        risk_b.run(sid, t0),
    )
    first = None
    for collector in (risk_a, risk_b):
        if collector.alerts:
            cand = collector.alerts[0]
            if first is None or cand[0] < first[0]:
                first = cand
    rec = RESULTS[-1]
    rec.update({
        "alerted": first is not None,
        "alert_latency_s": round(first[0], 2) if first else None,
        "first_score": first[1] if first else None,
        "first_band": first[2] if first else None,
        "alert_targets": first[3] if first else None,
        "expected_targets": [b],
        "routing_ok": (first[3] == [b]) if first else None,
        "all_alerts": [(round(t, 2), s, band, tg) for t, s, band, tg in risk_a.alerts + risk_b.alerts],
    })
    status = "ALERT" if first else "no-alert"
    print(f"[{name}] {status} latency={rec['alert_latency_s']}s "
          f"band={rec['first_band']} targets={rec['alert_targets']} (expect ['{b}'])")


async def echo_back_test(http):
    """Scammer scams; victim echoes OTP digits; routing must stay victim-only."""
    a = f"eb_a_{SUF}"[:20]
    b = f"eb_b_{SUF}"[:20]
    ta = await register(http, a, f"0391{DIGITS}")
    tb = await register(http, b, f"0392{DIGITS}")
    sid = await start_session(http, a, b)
    t0 = time.perf_counter()
    risk = RiskCollector("risk")

    async def scammer():
        async with websockets.connect(f"{WS}/ws/chat/{sid}") as ws:
            await ws.send(json.dumps({"type": "register", "device_id": a, "token": ta}))
            await ws.recv()
            await ws.send(json.dumps({"type": "message",
                                      "text": "This is ApnaBank security. Your account is blocked. Tell me the OTP code 558213 I just sent you, hurry.",
                                      "message_id": f"m_{uuid.uuid4().hex[:8]}"}))
            await asyncio.sleep(8)

    async def victim():
        async with websockets.connect(f"{WS}/ws/chat/{sid}") as ws:
            await ws.send(json.dumps({"type": "register", "device_id": b, "token": tb}))
            await ws.recv()
            await asyncio.sleep(1.5)
            # victim echoes the OTP back (matches tier-1 OTP rules too)
            await ws.send(json.dumps({"type": "message", "text": "ok the code is 558213",
                                      "message_id": f"m_{uuid.uuid4().hex[:8]}"}))
            await asyncio.sleep(7)

    await asyncio.gather(scammer(), victim(), risk.run(sid, t0))
    ok = risk.alerts and all(tg == [b] for _, _, _, tg in risk.alerts)
    RESULTS.append({
        "scenario": "echo_back_routing",
        "alerted": bool(risk.alerts),
        "alert_latency_s": round(risk.alerts[0][0], 2) if risk.alerts else None,
        "first_band": risk.alerts[0][2] if risk.alerts else None,
        "alert_targets_seen": [tg for _, _, _, tg in risk.alerts],
        "routing_ok": bool(ok),
    })
    print(f"[echo_back] alerts={[(round(t, 2), s, tg) for t, s, _, tg in risk.alerts]} "
          f"routing_ok={ok}")


async def main():
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as http:
        for idx, (name, lines) in enumerate(SCENARIOS):
            await run_scenario(http, idx, name, lines)
        await echo_back_test(http)
    print("\n===== SUMMARY =====")
    print(json.dumps(RESULTS, indent=1))


asyncio.run(main())
