"""TrustGuard AI Realtime Gateway — FastAPI app: REST + WebSocket channels.

Run (repo root):  PYTHONPATH=services uvicorn services.realtime-gateway.main:app --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


def _load_env() -> None:
    """Load .env from the repo root BEFORE tier2 reads os.environ at import."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(root, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


_load_env()

from ai.tier2 import ProviderConfig, ProviderRegistry, call_tier2
from accounts import (
    AccountError,
    InvalidPasswordError,
    InvalidPhoneError,
    InvalidUsernameError,
    PhoneTakenError,
    UsernameTakenError,
    authenticate,
    create_user,
    get_user,
    init_accounts,
    issue_token,
    list_users,
    revoke_token,
    validate_token,
)
from parsing import parse_auto
from scoring.taxonomy import LABELS

from db import init_db, save_session_snapshot
from parsing import ParsedMessage  # re-export for type hints
from pipeline import analyze_messages
from state import (
    HUB,
    METRICS,
    SESSIONS,
    append_message,
    arm_cross_channel,
    get_or_create_session,
)

REGISTRY = ProviderRegistry()

app = FastAPI(title="TrustGuard AI Gateway", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # demo prototype — dashboard + phones on LAN
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    os.makedirs("data", exist_ok=True)
    try:
        await init_db()
        await init_accounts()
    except Exception as exc:
        print(f"[gateway] DB init failed ({exc}) — continuing in memory-only mode")
    asyncio.create_task(_invite_expiry_sweeper())
    asyncio.create_task(_stt_preload())


async def _stt_preload() -> None:
    """Warm both whisper models in the background so the first call of the
    day doesn't pay the ~15 s CT2 int8 engine-init as a caption stall."""
    try:
        from stt.service import is_available, preload

        if is_available():
            await preload()
            print("[stt] models preloaded (tiny + base)")
    except Exception as exc:  # noqa: BLE001
        print(f"[stt] preload failed: {exc}")


async def _invite_expiry_sweeper() -> None:
    """Implements the MISSED call state: invites left 'pending' past their TTL
    (e.g. the caller's app died mid-ring) are expired and BOTH parties are told,
    so neither UI keeps ringing forever."""
    while True:
        await asyncio.sleep(10)
        now = time.time()
        expired = [
            inv_id for inv_id, inv in list(PENDING_INVITES.items())
            if inv.get("status") == "pending" and now - inv.get("created_at", now) > 60
        ]
        for inv_id in expired:
            inv = PENDING_INVITES.pop(inv_id, None)
            if not inv:
                continue
            payload = {"type": "call_rejected", "invite_id": inv_id, "reason": "missed"}
            await _notify_user(inv["from_user"], payload)
            await _notify_user(inv["to_user"], payload)


# ================================================================ schemas
class DeviceRegister(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


class SessionStart(BaseModel):
    type: str = "chat"                     # call | chat | replay
    device_a: str | None = None
    device_b: str | None = None


class PasteRequest(BaseModel):
    text: str = Field(min_length=1)
    format: str = "plain"                  # plain | whatsapp_export
    unknown_caller: bool = False
    caller_number: str | None = None        # optional caller ID to verify


class ProviderUpsert(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    base_url: str
    model: str
    api_key: str = ""
    priority: int = 100
    enabled: bool = True


class BankFreeze(BaseModel):
    session_id: str
    account_hint: str = ""                 # never real credentials


class AccountRegister(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=6, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)
    phone_number: str | None = Field(default=None, max_length=24)


class AccountLogin(BaseModel):
    username: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=1, max_length=128)


# ================================================================ accounts (register/login)
def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


async def _user_from_request(request: Request):
    token = _bearer_token(request)
    if not token:
        return None
    user_id = validate_token(token)
    if not user_id:
        return None
    return await get_user(user_id)


@app.post("/accounts/register")
async def accounts_register(body: AccountRegister) -> dict:
    try:
        user = await create_user(body.username, body.password,
                                 body.display_name, body.phone_number)
    except UsernameTakenError as exc:
        raise HTTPException(409, str(exc))
    except PhoneTakenError as exc:
        raise HTTPException(409, str(exc))
    except InvalidUsernameError as exc:
        raise HTTPException(422, str(exc))
    except InvalidPasswordError as exc:
        raise HTTPException(422, str(exc))
    except InvalidPhoneError as exc:
        raise HTTPException(422, str(exc))
    except AccountError as exc:                       # future account-domain errors
        raise HTTPException(400, str(exc))
    token = issue_token(user.user_id)
    await HUB.push_dashboard({"type": "user_registered", "user_id": user.user_id,
                              "username": user.username,
                              "display_name": user.display_name})
    return {"user_id": user.user_id, "username": user.username,
            "phone_number": user.phone_number, "token": token}


@app.post("/accounts/login")
async def accounts_login(body: AccountLogin) -> dict:
    user = await authenticate(body.username, body.password)
    if not user:
        raise HTTPException(401, "invalid username or password")
    token = issue_token(user.user_id)
    return {"user_id": user.user_id, "username": user.username, "token": token}


@app.get("/accounts/me")
async def accounts_me(request: Request) -> dict:
    user = await _user_from_request(request)
    if not user:
        raise HTTPException(401, "missing, invalid or expired bearer token")
    return user.summary()


@app.get("/accounts/users")
async def accounts_users() -> dict:
    """All accounts — powers the contact/peer list in the apps."""
    return {"users": [u.summary() for u in await list_users()]}


@app.post("/accounts/logout")
async def accounts_logout(request: Request) -> dict:
    token = _bearer_token(request)
    if not token:
        raise HTTPException(401, "missing bearer token")
    invalidated = revoke_token(token)
    return {"ok": True, "invalidated": invalidated}


# ================================================================ health & stats
@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "trustguard-gateway",
        "cloud_providers": [p.name for p in REGISTRY.usable_cloud()],
        "local_model": os.getenv("LOCAL_MODEL_NAME", "qwen2.5:3b-instruct"),
        "primary_model": os.getenv("PRIMARY_MODEL", "cloud"),
        "time": time.time(),
    }


def _golden_badge() -> dict | None:
    path = os.getenv("EVAL_RESULTS_FILE", "eval_results.json")
    if os.path.exists(path):
        try:
            with open(path) as fh:
                data = json.load(fh)
            return {k: data.get(k) for k in ("precision", "recall", "f1", "band_correct", "injection_pass")}
        except Exception:
            return None
    return None


@app.get("/api/v1/stats")
async def stats() -> dict:
    return METRICS.snapshot(active_devices=len(SESSIONS), golden_badge=_golden_badge())


# ================================================================ devices
@app.post("/api/v1/devices/register")
async def register_device(body: DeviceRegister) -> dict:
    device_id = f"dev_{uuid.uuid4().hex[:8]}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    await HUB.push_dashboard({
        "type": "device_registered",
        "device": {"device_id": device_id, "display_name": body.display_name,
                   "registered_at": now, "status": "online"},
    })
    return {"device_id": device_id, "display_name": body.display_name,
            "registered_at": now, "status": "online"}


@app.get("/api/v1/devices")
async def list_devices() -> dict:
    # live devices = active WS peers; demo keeps registry light
    online = [{"device_id": sid, "session_id": s.session_id}
              for sid, s in SESSIONS.items()]
    return {"devices": online}


# ================================================================ in-memory call / chat invitations
PENDING_INVITES: dict[str, dict] = {}        # invite_id -> {from_user, to_user, session_id, type, created_at}


def _deterministic_session_id(user_a: str, user_b: str, stype: str) -> str:
    """Two users always get the same session ID for the same type — like WhatsApp."""
    a, b = sorted([(user_a or "").lower(), (user_b or "").lower()])
    base = f"{stype}:{a}:{b}"
    return f"s_{hash(base) & 0xFFFFFFFF:08x}"


# ================================================================ sessions
@app.post("/api/v1/sessions/start")
async def start_session(body: SessionStart) -> dict:
    # If both participants are known, use a deterministic session ID so both
    # phones end up in the same room regardless of who starts the chat/call.
    if body.device_a and body.device_b:
        session_id = _deterministic_session_id(body.device_a, body.device_b, body.type)
    else:
        session_id = f"s_{uuid.uuid4().hex[:8]}"
    state = get_or_create_session(session_id, stype=body.type,
                                  device_a=body.device_a, device_b=body.device_b)
    METRICS.sessions_analyzed += 1
    await HUB.push_dashboard({"type": "session_started", "session_id": session_id,
                              "session_type": body.type})
    return {"session_id": session_id, "type": state.type, "mode": state.mode}


@app.post("/api/v1/sessions/{session_id}/end")
async def end_session(session_id: str) -> dict:
    state = SESSIONS.get(session_id)
    if not state:
        raise HTTPException(404, "unknown session")
    if state.scoring_task:
        state.scoring_task.cancel()
    payload = build_report(state)
    await save_session_snapshot(
        session_id, [(m.speaker, m.text) for m in state.messages],
        state.last_signals, state.displayed_score, state.band, [], session_type=state.type,
    )
    SESSIONS.pop(session_id, None)
    return {"session_id": session_id, "final_score": payload["score"], "band": payload["band"]}


def build_report(state) -> dict:
    return {
        "session_id": state.session_id,
        "score": round(state.displayed_score, 1),
        "band": state.band,
        "signals": state.last_signals,
        "stage": state.stage,
        "safe_actions": _safe_actions_for(state.band),
        "model_comparison_summary": {},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _safe_actions_for(band: str) -> list[str]:
    from scoring.taxonomy import SAFE_ACTIONS_BY_BAND

    return SAFE_ACTIONS_BY_BAND.get(band, [])


@app.get("/api/v1/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    state = SESSIONS.get(session_id)
    if not state:
        raise HTTPException(404, "unknown session")
    return {
        "session_id": session_id,
        "type": state.type,
        "messages": [vars(m) | {"meta": {}} for m in state.messages],
        "transcript_segments": state.segments,
        "score_history": state.score_history,
        "signals": state.last_signals,
    }


@app.get("/api/v1/sessions/{session_id}/report")
async def get_report(session_id: str) -> dict:
    state = SESSIONS.get(session_id)
    if not state:
        raise HTTPException(404, "unknown session")
    return build_report(state)


@app.get("/api/v1/sessions/{session_id}/model-comparison")
async def model_comparison(session_id: str) -> dict:
    rows = []
    path = f"data/model_comparisons_{session_id}.jsonl"
    if os.path.exists(path):
        with open(path) as fh:
            rows = [json.loads(l) for l in fh if l.strip()]
    return {"session_id": session_id, "results": rows}


# ================================================================ historical sessions
@app.get("/api/v1/sessions")
async def list_sessions(limit: int = 50, offset: int = 0) -> dict:
    """List recent sessions from the database (paginated)."""
    from db import SessionFactory, SessionRow, Message, Signal, ScoreHistory
    from sqlalchemy import select, desc

    async with SessionFactory() as db:
        # Get sessions with pagination
        result = await db.execute(
            select(SessionRow)
            .order_by(desc(SessionRow.started_at))
            .limit(limit)
            .offset(offset)
        )
        sessions = result.scalars().all()

        session_list = []
        for sess in sessions:
            # Get message count and final score for each session
            msg_count = await db.execute(
                select(Message).where(Message.session_id == sess.session_id)
            )
            msg_count = len(msg_count.scalars().all())

            # Get the highest score for this session
            scores = await db.execute(
                select(ScoreHistory)
                .where(ScoreHistory.session_id == sess.session_id)
                .order_by(desc(ScoreHistory.score))
                .limit(1)
            )
            top_score = scores.scalars().first()

            session_list.append({
                "session_id": sess.session_id,
                "type": sess.type,
                "started_at": sess.started_at.isoformat() if sess.started_at else None,
                "ended_at": sess.ended_at.isoformat() if sess.ended_at else None,
                "final_score": sess.final_score,
                "final_band": sess.final_band,
                "message_count": msg_count,
                "peak_score": top_score.score if top_score else None,
                "peak_band": top_score.band if top_score else None,
            })

        return {"sessions": session_list, "total": len(session_list)}


# ================================================================ call invitations (WhatsApp-style)
class CallInviteRequest(BaseModel):
    to_user: str = Field(min_length=1)
    from_user: str = Field(min_length=1)


class CallInviteResponse(BaseModel):
    invite_id: str
    session_id: str
    status: str


@app.post("/api/v1/calls/invite")
async def invite_call(body: CallInviteRequest) -> dict:
    """Phone A invites Phone B to a call."""
    to_user = body.to_user.lower()
    from_user = body.from_user.lower()
    invite_id = f"inv_{uuid.uuid4().hex[:8]}"
    session_id = _deterministic_session_id(from_user, to_user, "call")
    # Ensure session exists
    get_or_create_session(session_id, stype="call", device_a=from_user, device_b=to_user)
    PENDING_INVITES[invite_id] = {
        "invite_id": invite_id,
        "from_user": from_user,
        "to_user": to_user,
        "session_id": session_id,
        "type": "call",
        "created_at": time.time(),
        "status": "pending",
    }
    # Push notification to recipient if online
    await _notify_user(to_user, {
        "type": "incoming_call",
        "invite_id": invite_id,
        "from_user": from_user,
        "session_id": session_id,
    })
    await HUB.push_dashboard({"type": "call_invite_sent", "invite_id": invite_id,
                              "from": from_user, "to": to_user})
    return {"invite_id": invite_id, "session_id": session_id, "status": "pending"}


@app.post("/api/v1/calls/{invite_id}/accept")
async def accept_call(invite_id: str) -> dict:
    """Phone B accepts the call invitation."""
    invite = PENDING_INVITES.get(invite_id)
    if not invite:
        raise HTTPException(404, "invite not found or expired")
    invite["status"] = "accepted"
    session_id = invite["session_id"]
    # Notify caller
    await _notify_user(invite["from_user"], {
        "type": "call_accepted",
        "invite_id": invite_id,
        "session_id": session_id,
        "by_user": invite["to_user"],
    })
    return {"invite_id": invite_id, "session_id": session_id, "status": "accepted"}


@app.post("/api/v1/calls/{invite_id}/reject")
async def reject_call(invite_id: str) -> dict:
    """Rejects/cancels the call invitation.

    Used for BOTH callee-declines and caller-cancels, so both parties are
    notified: the caller's ringing screen and the callee's incoming-call UI /
    notification both dismiss. Each client ignores events for invites it has
    already settled locally, so the extra notify is harmless.
    """
    invite = PENDING_INVITES.pop(invite_id, None)
    if not invite:
        raise HTTPException(404, "invite not found or expired")
    invite["status"] = "rejected"
    payload = {
        "type": "call_rejected",
        "invite_id": invite_id,
        "by_user": invite["to_user"],
    }
    await _notify_user(invite["from_user"], payload)
    await _notify_user(invite["to_user"], payload)
    return {"invite_id": invite_id, "status": "rejected"}


@app.get("/api/v1/calls/pending")
async def pending_calls(user: str) -> dict:
    """Phone B polls for incoming call invitations."""
    user = user.lower()
    invites = [
        inv for inv in PENDING_INVITES.values()
        if inv["to_user"] == user and inv["status"] == "pending"
        and time.time() - inv["created_at"] < 60
    ]
    return {"invites": invites}


async def _notify_user(username: str, payload: dict) -> int:
    """Push a notification to all sockets registered for a user."""
    return await HUB.notify_user(username, payload)


@app.websocket("/ws/notifications/{username}")
async def notifications_socket(ws: WebSocket, username: str):
    """Persistent notification socket for incoming calls/messages."""
    from state import USER_SOCKETS
    await ws.accept()
    user = username.lower()
    USER_SOCKETS.setdefault(user, set()).add(ws)
    try:
        while True:
            data = await ws.receive_text()
            # Clients can send keepalives or acks; we just keep the socket open.
            if data == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    finally:
        USER_SOCKETS.get(user, set()).discard(ws)


@app.get("/api/v1/sessions/{session_id}/history")
async def get_session_history(session_id: str) -> dict:
    """Get full session history with messages, signals, and scam reasons."""
    from db import SessionFactory, SessionRow, Message, Signal, ScoreHistory, TranscriptSegment
    from sqlalchemy import select, desc

    async with SessionFactory() as db:
        # Get session metadata
        sess = await db.get(SessionRow, session_id)
        if not sess:
            # Try in-memory sessions
            state = SESSIONS.get(session_id)
            if not state:
                raise HTTPException(404, "unknown session")
            return {
                "session_id": session_id,
                "type": state.type,
                "messages": [vars(m) | {"meta": {}} for m in state.messages],
                "transcript_segments": state.segments,
                "score_history": state.score_history,
                "signals": state.last_signals,
            }

        # Get messages
        msg_result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.timestamp)
        )
        messages = [
            {
                "message_id": m.message_id,
                "speaker": m.speaker,
                "text": m.text,
                "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                "language": m.language,
            }
            for m in msg_result.scalars().all()
        ]

        # Get transcript segments
        ts_result = await db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.session_id == session_id)
            .order_by(TranscriptSegment.start_ms)
        )
        transcripts = [
            {
                "speaker": t.speaker,
                "text": t.text,
                "start_ms": t.start_ms,
                "end_ms": t.end_ms,
                "language": t.language,
            }
            for t in ts_result.scalars().all()
        ]

        # Get signals (scam reasons)
        sig_result = await db.execute(
            select(Signal)
            .where(Signal.session_id == session_id)
            .order_by(Signal.created_at)
        )
        signals = [
            {
                "type": s.type,
                "severity": s.severity,
                "confidence": s.confidence,
                "tier": s.tier,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sig_result.scalars().all()
        ]

        # Get score history
        score_result = await db.execute(
            select(ScoreHistory)
            .where(ScoreHistory.session_id == session_id)
            .order_by(ScoreHistory.timestamp)
        )
        score_history = [
            {
                "score": s.score,
                "band": s.band,
                "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            }
            for s in score_result.scalars().all()
        ]

        return {
            "session_id": session_id,
            "type": sess.type,
            "started_at": sess.started_at.isoformat() if sess.started_at else None,
            "ended_at": sess.ended_at.isoformat() if sess.ended_at else None,
            "final_score": sess.final_score,
            "final_band": sess.final_band,
            "messages": messages,
            "transcript_segments": transcripts,
            "signals": signals,
            "score_history": score_history,
        }


@app.get("/api/v1/sessions/{session_id}/messages")
async def get_session_messages(session_id: str) -> dict:
    """Fetch persisted chat messages for a session (WhatsApp history)."""
    from db import SessionFactory, Message
    from sqlalchemy import select

    async with SessionFactory() as db:
        result = await db.execute(
            select(Message).where(Message.session_id == session_id).order_by(Message.timestamp)
        )
        messages = [
            {
                "message_id": m.message_id,
                "speaker": m.speaker,
                "text": m.text,
                "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                "delivered_to": json.loads(m.delivered_to),
                "read_by": json.loads(m.read_by),
            }
            for m in result.scalars().all()
        ]
        return {"session_id": session_id, "messages": messages}


class ReceiptRequest(BaseModel):
    message_id: str
    user: str


@app.post("/api/v1/messages/delivered")
async def mark_delivered(body: ReceiptRequest) -> dict:
    """Mark a message as delivered to a user."""
    from db import SessionFactory, Message
    async with SessionFactory() as db:
        msg = await db.get(Message, body.message_id)
        if not msg:
            raise HTTPException(404, "message not found")
        delivered = set(json.loads(msg.delivered_to))
        delivered.add(body.user.lower())
        msg.delivered_to = json.dumps(list(delivered))
        await db.commit()
        return {"message_id": body.message_id, "delivered_to": list(delivered)}


@app.post("/api/v1/messages/read")
async def mark_read(body: ReceiptRequest) -> dict:
    """Mark a message as read by a user."""
    from db import SessionFactory, Message
    async with SessionFactory() as db:
        msg = await db.get(Message, body.message_id)
        if not msg:
            raise HTTPException(404, "message not found")
        read = set(json.loads(msg.read_by))
        read.add(body.user.lower())
        msg.read_by = json.dumps(list(read))
        # Also mark delivered if not already
        delivered = set(json.loads(msg.delivered_to))
        delivered.add(body.user.lower())
        msg.delivered_to = json.dumps(list(delivered))
        await db.commit()
        return {"message_id": body.message_id, "read_by": list(read)}


# ================================================================ paste analysis (Phase 1 core)
@app.post("/api/v1/analyze/paste")
async def analyze_paste(body: PasteRequest, caller_number: str | None = None) -> dict:
    started = time.perf_counter()
    messages = parse_auto(body.text, fmt=body.format)
    if not messages:
        raise HTTPException(422, "could not parse any message out of the input")

    session_id = f"paste_{uuid.uuid4().hex[:8]}"
    effective_caller = (caller_number or body.caller_number or "").strip() or None
    analysis = await analyze_messages(
        messages, REGISTRY,
        unknown_caller=body.unknown_caller,
        caller_number=effective_caller,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    METRICS.sessions_analyzed += 1
    for res in analysis.model_results:
        METRICS.parse_attempts += 1
        if res.parse_failed:
            METRICS.parse_failures += 1
        bucket = "latency_local" if res.provider == "ollama" else "latency_cloud"
        getattr(METRICS, bucket).append(res.latency_ms)

    model_rows = [
        {"model": r.model, "provider": r.provider, "latency_ms": r.latency_ms,
         "signals": r.signals, "error": r.error}
        for r in analysis.model_results
    ]
    report = {
        "session_id": session_id,
        "score": analysis.score,
        "band": analysis.band,
        "stage": analysis.stage,
        "safe_actions": analysis.safe_actions,
        "signals": analysis.signals,
        "tier1_hits": analysis.tier1_count,
        "caller_number": effective_caller,
        "caller_id_warnings": analysis.caller_id_warnings,
        "language_counts": _language_guess(messages),
        "model_comparison_summary": _model_summary(analysis.model_results),
        "analysis_latency_ms": latency_ms,
        "message_count": len(messages),
        "messages_preview": [{"message_id": m.message_id, "speaker": m.speaker,
                              "text": m.text[:200]} for m in messages[:12]],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        await save_session_snapshot(
            session_id, [(m.speaker, m.text) for m in messages],
            analysis.signals, analysis.score, analysis.band, model_rows, "paste",
        )
    except Exception as exc:
        print(f"[paste] persistence skipped: {exc}")
    return report


def _language_guess(messages: list[ParsedMessage]) -> dict:
    urdu = sum(1 for m in messages if any("\u0600" <= ch <= "\u06FF" for ch in m.text))
    roman = sum(1 for m in messages if not urdu and any(
        w in m.text.lower() for w in ("batao", "karo", "paisay", "turant", "nahi")))
    total = len(messages) or 1
    return {"urdu_script": urdu, "roman_urdu_like": roman, "total": total,
            "roman_urdu_ratio": round((urdu + roman) / total, 2)}


def _model_summary(results) -> dict:
    summary = {}
    for r in results:
        summary[r.provider] = {
            "latency_ms": r.latency_ms, "ok": r.ok,
            "signal_count": len(r.signals),
            "error": r.error,
        }
    return summary


# ================================================================ provider admin (add ANY key at runtime)
@app.get("/api/v1/admin/providers")
async def list_providers() -> dict:
    return {
        "providers": [
            {"name": p.name, "base_url": p.base_url, "model": p.model,
             "kind": p.kind, "priority": p.priority, "enabled": p.enabled,
             "has_key": bool(p.api_key),
             "key_hint": (p.api_key[:6] + "…" + p.api_key[-4:]) if len(p.api_key) > 12 else ("set" if p.api_key else "")}
            for p in REGISTRY.list()
        ],
        "note": "Add ANY OpenAI-compatible endpoint via POST. Built-ins: alibaba/groq/gemini/openrouter.",
    }


@app.post("/api/v1/admin/providers")
async def add_provider(body: ProviderUpsert) -> dict:
    cfg = ProviderConfig(name=body.name.lower(), base_url=str(body.base_url).rstrip("/"),
                         model=body.model, api_key=body.api_key,
                         priority=body.priority, enabled=body.enabled)
    REGISTRY.upsert(cfg)
    return {"ok": True, "provider": body.name, "usable_cloud_now": REGISTRY.has_cloud()}


@app.patch("/api/v1/admin/providers/{name}")
async def patch_provider(name: str, body: ProviderUpsert) -> dict:
    existing = REGISTRY.get(name.lower())
    if not existing:
        raise HTTPException(404, "unknown provider")
    merged = ProviderConfig(
        name=name.lower(),
        base_url=str(body.base_url or existing.base_url).rstrip("/"),
        model=body.model or existing.model,
        api_key=body.api_key if body.api_key != "" and body.api_key is not None else existing.api_key,
        priority=body.priority or existing.priority,
        enabled=body.enabled,
    )
    REGISTRY.upsert(merged)
    return {"ok": True, "provider": name.lower()}


@app.delete("/api/v1/admin/providers/{name}")
async def delete_provider(name: str) -> dict:
    ok = REGISTRY.remove(name.lower())
    return {"ok": ok}


@app.post("/api/v1/admin/providers/{name}/test")
async def test_provider(name: str) -> dict:
    cfg = REGISTRY.get(name.lower())
    if not cfg:
        raise HTTPException(404, "unknown provider")
    conv = 'them: Hello, this is your bank fraud department. Read me the OTP code batao.'
    result = await call_tier2(cfg, f"them: scam probe\nyou: ok", conv, timeout_s=20)
    return {
        "provider": cfg.name, "model": cfg.model, "ok": result.ok,
        "latency_ms": result.latency_ms, "signals_found": [s["type"] for s in result.signals],
        "error": result.error,
    }


# ================================================================ demo bank
_freezes: dict[str, dict] = {}


@app.post("/api/v1/bank/freeze")
async def bank_freeze(body: BankFreeze) -> dict:
    action_id = f"act_{uuid.uuid4().hex[:6]}"
    _freezes[body.session_id] = {
        "action_id": action_id, "action": "freeze_accounts",
        "result": "accounts frozen (demo ApnaBank mock)",
        "timestamp": time.time(),
    }
    await HUB.push_dashboard({"type": "bank_action", "session_id": body.session_id,
                              "action": "freeze", "result": "frozen"})
    return {"ok": True, **_freezes[body.session_id]}


@app.get("/api/v1/bank/actions/{session_id}")
async def bank_actions(session_id: str) -> dict:
    return {"session_id": session_id, "actions": [_freezes.get(session_id) or {}]}


# ================================================================ Phase 2.5 — explicit chat↔call link
@app.post("/api/v1/sessions/{chat_id}/link_call/{call_id}")
async def link_sessions(chat_id: str, call_id: str) -> dict:
    """Deterministically link a chat session to an active call for the
    cross-channel OTP correlation demo (Scenario B)."""
    chat_state = SESSIONS.get(chat_id)
    call_state = SESSIONS.get(call_id)
    if not chat_state or not call_state:
        raise HTTPException(404, "unknown session")
    if call_state.type != "call":
        raise HTTPException(422, f"{call_id} is not a call session")
    chat_state.linked_call_id = call_id
    return {"ok": True, "chat_session": chat_id, "linked_call": call_id}


# ================================================================ websockets
from ws import chat_endpoint, call_endpoint, risk_endpoint, dashboard_endpoint  # noqa: E402


@app.websocket("/ws/chat/{session_id}")
async def ws_chat(ws: WebSocket, session_id: str) -> None:
    await chat_endpoint(ws, session_id)


@app.websocket("/ws/call/{session_id}")
async def ws_call(ws: WebSocket, session_id: str) -> None:
    await call_endpoint(ws, session_id)


@app.websocket("/ws/session/{session_id}/risk")
async def ws_risk(ws: WebSocket, session_id: str) -> None:
    await risk_endpoint(ws, session_id)


@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket) -> None:
    await dashboard_endpoint(ws)
