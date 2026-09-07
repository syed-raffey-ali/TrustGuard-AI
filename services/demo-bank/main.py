"""Demo bank mock — Build Bible Sections 5, 11 (Safe Actions freeze layer).

Standalone FastAPI service on :8002. Fictional bank only ("ApnaBank").
Run standalone:  PYTHONPATH=services/demo-bank uvicorn main:app --port 8002
"""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="TrustGuard Demo Bank (ApnaBank mock)", version="1.0.0")

_actions: dict[str, list[dict]] = {}
_frozen: set[str] = set()


class FreezeRequest(BaseModel):
    session_id: str
    account_hint: str = ""      # demo: never real credentials
    reason: str = "critical_scam_alert"


class VerifyRequest(BaseModel):
    account_hint: str


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "bank": "ApnaBank (fictional)", "frozen_accounts": len(_frozen)}


@app.post("/freeze")
async def freeze(body: FreezeRequest) -> dict:
    action_id = f"act_{uuid.uuid4().hex[:8]}"
    entry = {
        "action_id": action_id,
        "session_id": body.session_id,
        "action": "freeze_accounts",
        "reason": body.reason,
        "result": f"ApnaBank demo accounts frozen for session {body.session_id}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _actions.setdefault(body.session_id, []).append(entry)
    _frozen.add(body.account_hint or body.session_id)
    return {"ok": True, **entry}


@app.post("/unfreeze")
async def unfreeze(body: FreezeRequest) -> dict:
    _frozen.discard(body.account_hint or body.session_id)
    entry = {"action": "unfreeze_accounts", "result": "accounts restored", "timestamp": time.time()}
    _actions.setdefault(body.session_id, []).append(entry)
    return {"ok": True, **entry}


@app.post("/verify")
async def verify(body: VerifyRequest) -> dict:
    """Judges ask: 'how does the victim verify for real?' — official-number callback."""
    return {
        "ok": True,
        "official_number": "+92-21-111-APNA-00",
        "advice": "Hang up and call the number printed on your card / the bank's official site. Never trust a number the caller gives you.",
    }


@app.get("/actions/{session_id}")
async def actions(session_id: str) -> dict:
    if session_id not in _actions:
        raise HTTPException(404, "no actions for session")
    return {"session_id": session_id, "actions": _actions[session_id]}
