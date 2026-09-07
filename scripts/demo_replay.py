#!/usr/bin/env python3
"""Phone-free demo replay — Build Bible Sections 19 (Phase 9), 20.

Drives the REAL gateway API over WebSocket/REST so the dashboard shows the
complete demo experience with zero phones. Rehearse the switch to this script;
it must take <30 seconds when live networking fails.

Usage (repo root):
    .venv/bin/python scripts/demo_replay.py --scenario B --speed 1
    .venv/bin/python scripts/demo_replay.py --scenario C --speed 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

import httpx
import websockets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENARIOS_DIR = os.path.join(ROOT, "data", "scripted-scenarios")

GATEWAY = os.getenv("TRUSTGUARD_GATEWAY", "http://127.0.0.1:8080")
WS_GATEWAY = GATEWAY.replace("http", "ws")

COLORS = {
    "low": "\033[92m", "medium": "\033[93m",
    "high": "\033[95m", "critical": "\033[91m", "end": "\033[0m",
}


def band_line(score: float, band: str) -> str:
    color = COLORS.get(band, "")
    bar = "█" * int(score // 5) + "·" * (20 - int(score // 5))
    return f"  RISK [{color}{bar}{COLORS['end']}] {score:5.1f}  {band.upper()}"


async def watch_risk(session_id: str, label: str, stop: asyncio.Event) -> list[dict]:
    updates: list[dict] = []
    uri = f"{WS_GATEWAY}/ws/session/{session_id}/risk"
    async with websockets.connect(uri) as ws:
        while not stop.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            data = json.loads(raw)
            if "score" in data:
                updates.append(data)
                print(f"  [{label}] {band_line(data['score'], data['band'])}")
                for sig in (data.get("delta_signals") or [])[:2]:
                    ev = (sig.get("evidence_ref") or {})
                    print(f"         ↳ {sig.get('type')} (conf {sig.get('confidence')})")
    return updates



async def wait_until_stable(rest: httpx.AsyncClient, session_id: str,
                            max_wait_s: float = 60.0,
                            min_window_s: float = 14.0) -> dict:
    """Poll until the score stops moving, respecting one full scoring window."""
    start = time.time()
    deadline = start + max_wait_s
    last = None
    stable = 0
    report = {}
    while time.time() < deadline:
        await asyncio.sleep(1.5)
        report = (await rest.get(f"{GATEWAY}/api/v1/sessions/{session_id}/report")).json()
        if report.get("score") == last and time.time() - start >= min_window_s:
            stable += 1
            if stable >= 2:
                return report
        else:
            stable = 0
            last = report.get("score")
    return report


async def run_scenario_b(speed: float) -> None:
    script = json.load(open(os.path.join(SCENARIOS_DIR, "scenario_b_bank_otp.json")))
    async with httpx.AsyncClient(timeout=30) as rest:
        call = (await rest.post(f"{GATEWAY}/api/v1/sessions/start",
                                json={"type": "call"})).json()
        chat = (await rest.post(f"{GATEWAY}/api/v1/sessions/start",
                                json={"type": "chat"})).json()
        await rest.post(f"{GATEWAY}/api/v1/sessions/{chat['session_id']}/link_call/{call['session_id']}")
        print(f"Scenario B — call {call['session_id']} + linked chat {chat['session_id']}\n")
        stop = asyncio.Event()
        watcher = asyncio.create_task(watch_risk(call["session_id"], "call", stop))
        try:
            async with websockets.connect(
                f"{WS_GATEWAY}/ws/call/{call['session_id']}"
            ) as call_ws, websockets.connect(
                f"{WS_GATEWAY}/ws/chat/{chat['session_id']}"
            ) as chat_ws:
                await chat_ws.send(json.dumps({"type": "register", "device_id": "replay_chat"}))
                await call_ws.send(json.dumps({"type": "control", "event": "start"}))
                await call_ws.send(json.dumps({"type": "control", "event": "start", "device_id": "replay_b"}))
                for line in script["lines"]:
                    print(f"\n  🎭 Director line {line['n']}: {line['text'][:90]}…")
                    await call_ws.send(json.dumps({
                        "type": "transcript_segment",
                        "speaker": line.get("speaker", "them"),
                        "text": line["text"],
                        "start_ms": int(time.time() * 1000),
                        "end_ms": int(time.time() * 1000) + 2000,
                    }))
                    if line.get("cross_channel_otp_text"):
                        await asyncio.sleep(1.0 / speed)
                        print("  📱 OTP-format text lands on the CHAT channel…")
                        await chat_ws.send(json.dumps({
                            "type": "director_line",
                            "speaker": "them",
                            "text": line["cross_channel_otp_text"],
                        }))
                    await asyncio.sleep(line.get("pause_ms", 1500) / 1000 / speed)
        finally:
            stop.set()
            await watcher
        report = await wait_until_stable(rest, call["session_id"])
    print(f"\nFINAL: {report['score']} → {report['band'].upper()}  "
          f"(expected {script['expected_band'].upper()})")


async def run_chat_scenario(script_file: str, speed: float, label: str) -> None:
    script = json.load(open(os.path.join(SCENARIOS_DIR, script_file)))
    async with httpx.AsyncClient(timeout=30) as rest:
        sess = (await rest.post(f"{GATEWAY}/api/v1/sessions/start",
                                json={"type": "chat"})).json()
        print(f"Scenario {script['id']} ({label}) — session {sess['session_id']}\n")
        stop = asyncio.Event()
        watcher = asyncio.create_task(watch_risk(sess["session_id"], label, stop))
        try:
            async with websockets.connect(
                f"{WS_GATEWAY}/ws/chat/{sess['session_id']}"
            ) as chat_ws:
                await chat_ws.send(json.dumps({"type": "register", "device_id": f"replay_{label}"}))
                for msg in script["messages"]:
                    who = "🧑‍💼 them" if msg["speaker"] == "them" else "🙂 me"
                    print(f"  {who}: {msg['text'][:88]}")
                    await chat_ws.send(json.dumps({
                        "type": "director_line" if msg["speaker"] == "them" else "message",
                        "speaker": msg["speaker"],
                        "text": msg["text"],
                    }))
                    await asyncio.sleep(msg.get("pause_ms", 1200) / 1000 / speed)
        finally:
            stop.set()
            await watcher
        report = await wait_until_stable(rest, sess["session_id"])
        report = (await rest.get(f"{GATEWAY}/api/v1/sessions/{sess['session_id']}/report")).json()
    print(f"\nFINAL: {report['score']} → {report['band'].upper()}  "
          f"(expected {script['expected_band'].upper()})")


async def main_async() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, choices=["A", "B", "C", "D", "E"])
    parser.add_argument("--speed", type=float, default=1.0,
                        help=">1 replays faster (e.g. 4 = 4x)")
    args = parser.parse_args()

    health = httpx.get(f"{GATEWAY}/health", timeout=10).json()
    print(f"gateway: {health['status']} | primary={health['primary_model']} "
          f"| cloud={health['cloud_providers']} local={health['local_model']}\n")

    started = time.time()
    if args.scenario == "A":
        await run_chat_scenario("scenario_d_safe.json", args.speed, "safe-call")
    elif args.scenario == "B":
        await run_scenario_b(args.speed)
    elif args.scenario == "C":
        await run_chat_scenario("scenario_c_grooming.json", args.speed, "grooming")
    elif args.scenario == "D":
        await run_chat_scenario("scenario_d_safe.json", args.speed, "false-positive-check")
    elif args.scenario == "E":
        await run_chat_scenario("scenario_e_injection.json", args.speed, "red-team")
    print(f"\ndone in {time.time() - started:.1f}s")


if __name__ == "__main__":
    asyncio.run(main_async())
