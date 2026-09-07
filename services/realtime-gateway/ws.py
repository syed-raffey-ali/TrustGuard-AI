"""WebSocket endpoints — live chat (Phase 2), cross-channel (2.5), voice relay (3),
live risk scoring (5). Audio protocol: raw 16 kHz mono PCM16 binary frames;
control messages are JSON text frames (documented in docs/assumptions.md).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import time
import uuid

from fastapi import WebSocket, WebSocketDisconnect

from accounts import link_device, user_from_token
from scoring.rules_engine import run_counter_rules, run_tier1_message
from scoring.taxonomy import SAFE_ACTIONS_BY_BAND

from parsing import ParsedMessage
from pipeline import analyze_messages, note_local_latency
from state import (
    CHAT_USERS,
    HUB,
    METRICS,
    SESSIONS,
    SessionState,
    append_message,
    arm_cross_channel,
    find_linked_calls,
    get_or_create_session,
)

TIER2_DEBOUNCE_S = 0.3          # event-driven chat: coalesce bursts of messages
VOICE_RESCORE_INTERVAL_S = 3.0  # 2–4 s cycle per Bible Section 6
# Hard budget for live Tier-2 cycles: the race uses whatever providers have
# answered by then, so a slow model can never hold back the scam alert.
LIVE_TIER2_BUDGET_S = float(os.getenv("LIVE_TIER2_BUDGET_S", "2.5"))
STT_INTERVAL_S = float(os.getenv("STT_INTERVAL_S", "0.8"))   # transcription cadence
STT_MIN_AUDIO_BYTES = 16000     # ≥ 0.5 s of 16 kHz PCM16 before transcribing
STT_SILENCE_RMS = 150.0         # skip near-silent windows (CPU saver)
# 2.5 s of 16 kHz PCM16 (32 000 B/s) per live STT window. Whisper's fixed
# per-call cost (~1–2 s on the i5-4200U) makes sub-second slices a pure
# backlog snowball (the 17 s caption delay); 2.5 s amortises it while still
# landing captions ~3–4 s behind speech.
LIVE_WINDOW_BYTES = 80_000
# 4 s windows for non-English peers: the quality ('base') model needs
# ~4–5 s per window on this CPU, so bigger windows keep it closer to
# real-time than 2.5 s slices would.
QUALITY_WINDOW_BYTES = 128_000


async def _persist_and_notify_message(state: SessionState, msg, sender_identity: str) -> None:
    """Save message to DB and push a notification to offline recipients."""
    try:
        from db import SessionFactory, Message
        async with SessionFactory() as db:
            db.add(Message(
                message_id=msg.message_id,
                session_id=state.session_id,
                speaker=msg.speaker,
                text=msg.text,
                timestamp=dt.datetime.now(dt.timezone.utc),
            ))
            await db.commit()
    except Exception as exc:
        # Duplicate-ID collisions must never block delivery; log and move on.
        print(f"[chat] failed to persist message: {exc}")

    # Notify the other participant(s) only if they're not in the chat room right now.
    participants = {state.device_a or "", state.device_b or ""} - {"", sender_identity.lower()}
    online_in_room = CHAT_USERS.get(state.session_id, set())
    for recipient in participants:
        if recipient.lower() in online_in_room:
            continue
        await HUB.notify_user(recipient, {
            "type": "new_message",
            "session_id": state.session_id,
            "from_user": sender_identity,
            "message_id": msg.message_id,
            "text": msg.text[:120],
        })


async def _update_receipt(message_id: str | None, user: str, kind: str, session_id: str) -> None:
    """Update delivered/read status in DB and notify the original sender."""
    if not message_id:
        return
    try:
        from db import SessionFactory, Message
        from sqlalchemy import select
        async with SessionFactory() as db:
            msg = await db.get(Message, message_id)
            if not msg:
                return
            if kind == "read":
                read = set(json.loads(msg.read_by))
                read.add(user.lower())
                msg.read_by = json.dumps(list(read))
                delivered = set(json.loads(msg.delivered_to))
                delivered.add(user.lower())
                msg.delivered_to = json.dumps(list(delivered))
            else:
                delivered = set(json.loads(msg.delivered_to))
                delivered.add(user.lower())
                msg.delivered_to = json.dumps(list(delivered))
            await db.commit()

        # Notify all participants in the chat room about the receipt.
        await HUB.push_chat(session_id, {
            "type": f"{kind}_receipt",
            "message_id": message_id,
            "user": user.lower(),
        })
    except Exception as exc:
        print(f"[chat] failed to update {kind} receipt: {exc}")


async def _safe_send_bytes(ws: WebSocket, data: bytes) -> None:
    """Non-blocking audio relay: silently drops on error to prevent sender blocking."""
    try:
        await ws.send_bytes(data)
    except Exception:
        pass  # receiver disconnected or slow — drop chunk rather than block sender


def _flag_speaker(state: SessionState, username: str) -> None:
    """Record WHO produced flagged content (first-flagged = primary suspect).

    Victims routinely ECHO flagged content back (reading an OTP code aloud,
    replying with account details), which flags them too. Keeping the flag
    order lets _alert_targets stay victim-only even when everyone has been
    flagged: the earliest flagger remains the suspect.
    """
    uname = (username or "").strip().lower()
    if not uname:
        return
    if uname not in state.flagged_speakers:
        state.flagged_order.append(uname)
    state.flagged_speakers.add(uname)


def _alert_targets(state: SessionState) -> list[str]:
    """Usernames that should see the scam warning for this session.

    Victim-only routing (never alert the sender of the suspicious content).
    Primary rule: whoever PRODUCED the flagged content (flagged_speakers) is
    the suspect — everyone else is alerted, no matter who spoke most recently.
    If every participant got flagged (victim echoing an OTP back), the FIRST
    flagger is the suspect. Fallback when nothing is flagged yet: the most
    recent speaker is the presumed source. Empty list means the participant
    topology is unknown — clients then fall back to their local heuristic.
    The dashboard always receives the full payload regardless.
    """
    participants = {p.lower() for p in (state.device_a, state.device_b) if p}
    if len(participants) < 2:
        return []
    flagged = [s for s in state.flagged_order if s in participants]
    if not flagged:  # tolerate states built before flagged_order existed
        flagged = sorted(s for s in state.flagged_speakers if s in participants)
    if flagged:
        suspects = set(flagged)
        if suspects >= participants:
            # Everyone has flagged content (echo-back) — blame the first one.
            suspects = {flagged[0]}
        return sorted(p for p in participants if p not in suspects)
    speaker = state.last_speaker
    speaker_user = state.speaker_users.get(speaker, speaker).lower()
    if not speaker_user or speaker_user not in participants:
        return sorted(participants)
    return sorted(p for p in participants if p != speaker_user)


def _risk_payload(state: SessionState, delta_signals: list[dict] | None = None) -> dict:
    return {
        "session_id": state.session_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tier": 2,
        "score": round(state.displayed_score, 1),
        "band": state.band,
        "delta_signals": delta_signals or [],
        "stage": state.stage,
        "safe_actions": SAFE_ACTIONS_BY_BAND.get(state.band, []),
        "alert_targets": _alert_targets(state),
    }


async def _record_and_push(state: SessionState, analysis) -> None:
    """Ratchet already applied inside scorer via previous_displayed_score."""
    state.last_signals = analysis.signals
    state.stage = analysis.stage or state.stage
    state.displayed_score = analysis.score
    state.band = analysis.band
    entry = {"ts": time.time(), "score": round(analysis.score, 1), "band": analysis.band}
    state.score_history.append(entry)
    await HUB.push_risk(state.session_id, _risk_payload(
        state, [s for s in analysis.signals if s.get("contribution", 0) > 0][:4]
    ))
    await HUB.push_dashboard({"type": "risk_update", **entry, "session_id": state.session_id})


# ================================================================ Phase 2 — live chat
async def chat_endpoint(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    state = get_or_create_session(session_id, stype="chat")
    HUB.join_chat(session_id, ws)
    await HUB.join_risk(f"chat:{session_id}", ws)
    peer_name = "peer"
    auth = "anonymous"                     # ok | invalid | anonymous (device-only)
    try:
        reg = await ws.receive_json()
        peer_name = reg.get("device_id") or reg.get("speaker") or "peer"
        reg_caller = reg.get("caller_number") or reg.get("from_number")
        if reg_caller:
            state.caller_number = str(reg_caller).strip()
        token = reg.get("token")           # optional account auth (backward compatible)
        if token:
            user = await user_from_token(str(token))
            if user:
                peer_name = user.username
                auth = "ok"
                if reg.get("device_id"):
                    await link_device(user.user_id, str(reg["device_id"]))
            else:
                auth = "invalid"
        await ws.send_json({"type": "registered", "session_id": session_id,
                            "analysis_indicator": True,
                            "auth": auth, "peer_name": peer_name,
                            "caller_number": state.caller_number})
        HUB.mark_chat_user(session_id, peer_name, present=True)
        # Populate session participants so victim-only alert routing
        # (_alert_targets) works for chat sessions too, not just calls.
        if peer_name and peer_name not in (state.device_a, state.device_b):
            if not state.device_a:
                state.device_a = peer_name
            elif not state.device_b:
                state.device_b = peer_name

        while True:
            data = await ws.receive_json()
            mtype = data.get("type", "message")
            upd_caller = data.get("caller_number") or data.get("from_number")
            if upd_caller:
                state.caller_number = str(upd_caller).strip()
            if mtype == "ping":
                await ws.send_json({"type": "pong"})
                continue
            if mtype == "delivery_receipt":
                asyncio.create_task(_update_receipt(
                    data.get("message_id"), peer_name, "delivered", session_id
                ))
                continue
            if mtype == "read_receipt":
                asyncio.create_task(_update_receipt(
                    data.get("message_id"), peer_name, "read", session_id
                ))
                continue
            if mtype == "director_line":     # Director mode over text (Phase 6)
                text, speaker = str(data.get("text", "")), "them"
            elif auth == "ok":
                # Authenticated connections cannot impersonate another sender:
                # the speaker label is forced to the token's account username.
                text, speaker = str(data.get("text", "")), peer_name
            else:
                text, speaker = str(data.get("text", "")), str(data.get("speaker", peer_name))
            if not text.strip():
                continue

            msg = append_message(state, speaker, text, message_id=data.get("message_id"))
            state.last_speaker = speaker
            state.speaker_users.setdefault(speaker, speaker)  # chat speaker == username

            # Persist message and notify recipient (WhatsApp-style delivery).
            asyncio.create_task(_persist_and_notify_message(
                state, msg, sender_identity=peer_name
            ))

            # Tier-1 instantly (<150 ms target) — server mirror of on-device rules
            t0 = time.perf_counter()
            hits = run_tier1_message(msg.text, message_index=len(state.messages) - 1)
            counters = run_counter_rules(msg.text, message_index=len(state.messages) - 1)
            tier1_ms = int((time.perf_counter() - t0) * 1000)
            if hits:
                # The sender of flagged content is the suspect — alerts will
                # target everyone else, regardless of who speaks later.
                _flag_speaker(state, peer_name)

            # Phase 2.5: OTP-format message during an active linked call -> +10 armed
            cross_channel = await arm_cross_channel(state, msg.text)
            linked_calls = find_linked_calls(state)
            for call_state in linked_calls:
                if call_state.session_id != state.session_id:
                    cross_channel = cross_channel or await arm_cross_channel(call_state, msg.text)
                    await HUB.push_risk(call_state.session_id, {
                        "type": "cross_channel_evidence",
                        "message": "OTP-format message arrived on chat during this call",
                        "chat_session_id": state.session_id,
                        "quote": text[:120],
                    })

            relay = {"type": "message", "speaker": speaker, "text": text,
                     "message_id": msg.message_id,
                     "timestamp": time.strftime("%H:%M:%S")}
            for peer in list(HUB.chat_rooms.get(session_id, set())):
                if peer is not ws:
                    try:
                        await peer.send_json(relay)
                    except Exception:
                        pass

            await ws.send_json({
                "type": "ack", "message_id": msg.message_id, "tier1_hits": [
                    {"type": h.type, "severity": h.severity, "confidence": h.confidence}
                    for h in hits],
                "counter_hits": [c.type for c in counters],
                "tier1_latency_ms": tier1_ms,
                "cross_channel_otp_armed": cross_channel,
            })

            _schedule_tier2(state, debounce=TIER2_DEBOUNCE_S)
            # Fast path: rules + trained ML only (no cloud wait) so the
            # victim's alert lands in well under a second; the debounced
            # Tier-2 cycle refines the score a moment later.
            asyncio.create_task(_fast_chat_score(state))
    except WebSocketDisconnect:
        pass
    finally:
        HUB.leave_chat(session_id, ws)
        HUB.mark_chat_user(session_id, peer_name, present=False)


async def _fast_chat_score(state: SessionState) -> None:
    """Sub-100 ms chat scoring (Tier-1 rules + trained ML + caller-ID).

    Fires on EVERY chat message — no debounce — so a scam text alerts the
    victim almost instantly. The full Tier-2 LLM cycle (scheduled separately)
    remains the authority and can only RAISE the displayed score afterwards
    (this pass is gated on actually increasing it, so it never fights the
    ratchet).
    """
    try:
        window = state.messages[-20:]
        if not any(m.text.strip() for m in window):
            return
        analysis = await analyze_messages(
            window,
            previous_score=state.displayed_score,
            caller_number=state.caller_number,
            use_llm=False,
        )
        if analysis.score > state.displayed_score + 0.5:
            await _record_and_push(state, analysis)
    except Exception as exc:  # noqa: BLE001 — fast path must never break chat
        print(f"[chat-fast] {exc}")


def _schedule_tier2(state: SessionState, debounce: float) -> None:
    """Event-driven: one in-flight cycle, debounced; skip when nothing new (Bible 8.4)."""
    async def runner():
        try:
            await asyncio.sleep(debounce)
            while state.new_content_since_cycle:
                state.new_content_since_cycle = False
                from main import REGISTRY  # late import avoids circular

                include_local = not (state.primary_model_override == "cloud")
                analysis = await analyze_messages(
                    state.messages, REGISTRY,
                    unknown_caller=False,
                    cross_channel_otp=state.cross_channel_armed,
                    previous_score=state.displayed_score,
                    include_local=include_local,
                    local_timeout_s=float(os.getenv("LIVE_LOCAL_TIMEOUT_S", "3")),
                    caller_number=state.caller_number,
                    live_budget_s=LIVE_TIER2_BUDGET_S,
                )
                state.cross_channel_armed = False

                METRICS.tier2_cycles += 1
                for res in analysis.model_results:
                    METRICS.parse_attempts += 1
                    if res.parse_failed:
                        METRICS.parse_failures += 1
                    bucket = "latency_local" if res.provider == "ollama" else "latency_cloud"
                    getattr(METRICS, bucket).append(res.latency_ms)
                    from pipeline import note_local_latency

                    if res.provider == "ollama":
                        note_local_latency(res.latency_ms)

                # Bible 8.4 auto-switch: local >6 s twice consecutively -> cloud primary
                local_results = [r for r in analysis.model_results if r.provider == "ollama"]
                if local_results and local_results[0].latency_ms > 6000:
                    state.local_slow_cycles += 1
                    if state.local_slow_cycles >= 2:
                        state.primary_model_override = "cloud"
                elif local_results:
                    state.local_slow_cycles = 0

                _log_model_comparison(state, analysis)
                await _record_and_push(state, analysis)
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[tier2] cycle error: {exc}")

    if state.scoring_task and not state.scoring_task.done():
        return  # a cycle is pending/running; it will pick up the new content flag
    state.scoring_task = asyncio.create_task(runner())


def _log_model_comparison(state: SessionState, analysis) -> None:
    path_dir = "data"
    try:
        os.makedirs(path_dir, exist_ok=True)
        path = f"{path_dir}/model_comparisons_{state.session_id}.jsonl"
        row = {
            "cycle_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "primary_model": os.getenv("PRIMARY_MODEL", "cloud"),
            "results": [
                {"model": r.model, "provider": r.provider, "latency_ms": r.latency_ms,
                 "signals": [{"type": s["type"], "severity": s["severity"],
                              "confidence": s["confidence"]} for s in r.signals],
                 "error": r.error}
                for r in analysis.model_results
            ],
        }
        with open(path, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception as exc:
        print(f"[model-race] log failed: {exc}")


# ================================================================ Phase 3 — voice call relay
async def call_endpoint(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    state = get_or_create_session(session_id, stype="call")
    peer_id = str(uuid.uuid4().hex[:8])
    HUB.join_call(session_id, peer_id, ws)
    await HUB.join_risk(session_id, ws)
    peers = len(HUB.call_rooms.get(session_id, {}))
    peer_name: str | None = None          # username, when token auth is used
    auth_attempted = False

    await ws.send_json({"type": "control", "event": "registered",
                        "peer_id": peer_id, "analysis_active": True})
    if peers == 2 and not state.call_active:
        state.call_active = True
        state.call_started_ts = time.time()
        # Both sides are now connected — tell clients to start the call timer.
        for pid, peer_ws in list(HUB.call_rooms.get(session_id, {}).items()):
            try:
                await peer_ws.send_json({"type": "control", "event": "call_connected"})
            except Exception:
                pass
        await HUB.push_risk(session_id, {
            "type": "analysis_notice",
            "message": "This call is being analysed by TrustGuard AI",
            "persistent": True,
        })
        _voice_loops[session_id] = asyncio.create_task(_voice_rescore_loop(state))
        _stt_loops[session_id] = asyncio.create_task(_voice_stt_loop(state))

    try:
        while True:
            payload = await ws.receive()
            if payload.get("type") == "websocket.disconnect":
                break
            if "bytes" in payload and payload["bytes"]:
                other = HUB.call_other(session_id, peer_id)
                if other:
                    # Non-blocking relay: fire-and-forget so a slow receiver
                    # doesn't block the sender (prevents cascading latency/drops).
                    asyncio.create_task(_safe_send_bytes(other, payload["bytes"]))
                # audio also feeds the STT queue (Phase 4) — in-memory only.
                # A single connected peer streaming audio counts as an active
                # call too (test harness / one-sided live monitoring).
                from stt_stream import ingest_audio

                ingest_audio(session_id, peer_id, payload["bytes"])
                if not state.call_active:
                    state.call_active = True
                    state.call_started_ts = time.time()
                if session_id not in _stt_loops or _stt_loops[session_id].done():
                    _stt_loops[session_id] = asyncio.create_task(_voice_stt_loop(state))
                if session_id not in _voice_loops or _voice_loops[session_id].done():
                    _voice_loops[session_id] = asyncio.create_task(_voice_rescore_loop(state))
            elif "text" in payload and payload["text"]:
                control = json.loads(payload["text"])
                ctype = control.get("type", "")
                # optional account auth: a control/register frame may carry a
                # token (e.g. {"type":"control","event":"start","token":...})
                token = control.get("token")
                if token and not auth_attempted:
                    auth_attempted = True
                    user = await user_from_token(str(token))
                    if user:
                        peer_name = user.username
                        state.call_peer_users[peer_id] = peer_name
                        if control.get("device_id"):
                            await link_device(user.user_id, str(control["device_id"]))
                        await ws.send_json({"type": "control", "event": "auth_ok",
                                            "peer_id": peer_id, "peer_name": peer_name,
                                            "user_id": user.user_id})
                    else:
                        await ws.send_json({"type": "control", "event": "auth_failed",
                                            "peer_id": peer_id})
                if ctype == "transcript_segment":
                    # from STT pipeline / test harness: speaker + text + timing
                    seg = {
                        "speaker": control.get("speaker", "them"),
                        "text": control.get("text", ""),
                        "start_ms": control.get("start_ms", 0),
                        "end_ms": control.get("end_ms", 0),
                        "language": control.get("language", "mixed"),
                    }
                    state.segments.append(seg)
                    idx = len(state.segments) - 1
                    seg_hits = run_tier1_message(seg["text"], position_s=seg["start_ms"] / 1000.0)
                    if seg_hits:
                        flagged_user = state.speaker_users.get(seg["speaker"], seg["speaker"])
                        _flag_speaker(state, str(flagged_user))
                    state.new_content_since_cycle = True
                    # text-fed transcripts count as an active call too (external
                    # STT sources / test harness — no binary audio required)
                    if not state.call_active:
                        state.call_active = True
                        state.call_started_ts = time.time()
                    if session_id not in _voice_loops or _voice_loops[session_id].done():
                        _voice_loops[session_id] = asyncio.create_task(
                            _voice_rescore_loop(state)
                        )
                    await ws.send_json({"type": "segment_ack", "index": idx})
                elif ctype == "end" or control.get("event") in ("end", "hang_up", "hangup"):
                    # explicit hang-up frame: {"type":"control","event":"end"}
                    break
                elif (ctype in ("register", "caller_id", "set_caller_number")
                        or "caller_number" in control or "from_number" in control):
                    # caller-ID registration for directory verification
                    num = control.get("caller_number") or control.get("from_number")
                    if num:
                        state.caller_number = str(num).strip()
                        await ws.send_json({"type": "caller_id_ack",
                                            "caller_number": state.caller_number})
    except WebSocketDisconnect:
        pass
    finally:
        HUB.leave_call(session_id, peer_id)
        # Notify any remaining peer that this side ended the call (graceful
        # hang-up OR an unexpected network drop) so their UI closes too.
        for pid, peer_ws in list(HUB.call_rooms.get(session_id, {}).items()):
            try:
                await peer_ws.send_json({"type": "control", "event": "ended"})
            except Exception:
                pass
        if not HUB.call_rooms.get(session_id):
            state.call_active = False
            loop = _voice_loops.pop(session_id, None)
            if loop:
                loop.cancel()
            stt_loop = _stt_loops.pop(session_id, None)
            if stt_loop:
                stt_loop.cancel()
            await _flush_call_audio(state)   # never lose the last spoken words
            _LANG_BY_PEER.pop(session_id, None)
            from stt_stream import drop_session

            drop_session(session_id)   # privacy: raw audio never outlives the call


_voice_loops: dict[str, asyncio.Task] = {}
_stt_loops: dict[str, asyncio.Task] = {}


def _pcm_rms(pcm: bytes) -> float:
    """Cheap sampled int16 RMS — keeps numpy off the audio hot path."""
    import array

    if len(pcm) < 2:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    step = max(1, len(samples) // 4096)
    picked = samples[::step]
    if not picked:
        return 0.0
    return (sum(s * s for s in picked) / len(picked)) ** 0.5


# ~4 s of 16 kHz PCM16 (32 000 bytes/s) — bounds each whisper call so a
# backlog drains in bounded steps instead of one ever-growing transcription
# (that snowballing was the cause of the 10 s+ caption delay).
MAX_STT_CHUNK_BYTES = 128_000

# Whisper hallucination filter: idle/noise windows love emitting stock
# subtitle phrases that would pollute the transcript and confuse scoring.
_STT_HALLUCINATIONS = frozenset({
    "thank you for watching", "thanks for watching", "thank you", "thanks",
    "you", "bye", "bye-bye", "please subscribe", "subtitles by", "watching",
})


def _is_repetition_loop(text: str) -> bool:
    """Whisper degenerate-output filter: one word repeated endlessly
    (observed: "ایک ایک ایک …" ×30 on noisy Urdu windows)."""
    words = text.split()
    return len(words) >= 5 and len(set(words)) <= max(2, len(words) // 5)

# Per-session pinned whisper languages: peer_id -> lang code. Detected once
# on the peer's first (VAD'd) window — per-window auto-detect on 2–3 s clips
# is slow AND wildly unreliable for Urdu (observed tl/ar/ta/si mislabels).
_LANG_BY_PEER: dict[str, dict[str, str]] = {}


async def _transcribe_peer(
    key: str,
    speaker_label: str,
    base_offset_ms: int,
    language: str | None = None,
    detect: bool = False,
) -> list:
    """Drain one peer's buffered audio and transcribe it in bounded chunks.

    detect=True marks a peer's FIRST window: whisper auto-detects the
    language (with VAD) so the caller can pin it for every later window.
    Slices run SERIALLY, not in parallel: CTranslate2 already uses every
    core intra-op, so concurrent calls on a 4-thread CPU just oversubscribe
    it and multiply every slice's latency.
    """
    from stt.service import transcribe_window
    from stt_stream import drain_new

    pcm = await drain_new(key)
    if len(pcm) < STT_MIN_AUDIO_BYTES or _pcm_rms(pcm) < STT_SILENCE_RMS:
        return []
    segments = []
    for start in range(0, len(pcm), MAX_STT_CHUNK_BYTES):
        chunk = pcm[start:start + MAX_STT_CHUNK_BYTES]
        if len(chunk) < STT_MIN_AUDIO_BYTES:
            continue
        try:
            batch = await transcribe_window(
                chunk,
                speaker=speaker_label,
                offset_ms=base_offset_ms + start // 32,  # 32 000 B == 1 s
                language=None if detect else language,
                use_vad=detect,
            )
        except Exception as exc:  # noqa: BLE001 — one bad window never kills STT
            print(f"[stt] transcribe failed: {exc}")
            continue
        segments.extend(
            s for s in batch
            if s.text.strip().lower().strip(".! ") not in _STT_HALLUCINATIONS
            and not _is_repetition_loop(s.text)
        )
    segments.sort(key=lambda s: s.start_ms)
    return segments


async def _voice_stt_loop(state: SessionState) -> None:
    """Live transcription: drain each peer's audio → faster-whisper → segments.

    Every peer's audio is transcribed SEPARATELY, so the server always knows
    WHO said what (the speaker label maps back to the account username), and
    both peers are transcribed CONCURRENTLY so one talker can't delay the
    other's captions. Segments land in state.segments for the rescore loop and
    are pushed to the risk channel as transcript_segment frames so the app can
    render live captions. A fast scoring pass runs right after new speech lands
    so warnings beat the cloud LLM round-trip.
    """
    try:
        from stt.service import is_available

        if not is_available():
            print("[stt] faster-whisper not installed — live voice transcription "
                  "disabled (text/chat detection still fully active)")
            return
        speaker_map: dict[str, str] = {}          # peer_id -> "them" | "me"
        lang_by_peer = _LANG_BY_PEER.setdefault(state.session_id, {})
        while state.call_active:
            await asyncio.sleep(STT_INTERVAL_S)
            from stt_stream import buffered_bytes, peer_keys

            # Pre-check buffered size: only full windows are drained;
            # shorter audio stays buffered for the next cycle instead of
            # being drained and discarded. Threshold depends on the peer's
            # pinned language: 'en' (and not-yet-detected) uses the fast
            # 2.5 s path; Urdu/other uses 4 s windows on the quality model.
            keys = []
            for k in peer_keys(state.session_id):
                pid = k.split(":", 1)[1]
                pin = lang_by_peer.get(pid)
                need = LIVE_WINDOW_BYTES if pin in (None, "en") else QUALITY_WINDOW_BYTES
                if buffered_bytes(k) >= need:
                    keys.append(k)
            if not keys:
                continue

            tasks = []
            for key in keys:
                peer_id = key.split(":", 1)[1]
                if peer_id not in speaker_map:
                    speaker_map[peer_id] = (
                        "them" if "them" not in speaker_map.values() else "me"
                    )
                    # Map the voice label back to the account username so risk
                    # payloads can route the alert to the OTHER participant.
                    uname = state.call_peer_users.get(peer_id)
                    if uname:
                        state.speaker_users[speaker_map[peer_id]] = uname
                offset_ms = int(
                    max(0.0, time.time() - (state.call_started_ts or time.time())) * 1000
                )
                pinned = lang_by_peer.get(peer_id)
                tasks.append(_transcribe_peer(
                    key, speaker_map[peer_id], offset_ms,
                    language=pinned, detect=pinned is None,
                ))

            new_text = False
            for key, segments in zip(keys, await asyncio.gather(*tasks)):
                peer_id = key.split(":", 1)[1]
                if peer_id not in lang_by_peer:
                    # Pin this peer's language from the first detected window:
                    # later windows skip detection (faster AND stable). 'en'
                    # pins as-is; EVERYTHING else on this user base (Urdu
                    # speech mislabelled hi/si/tl/ar) pins 'ur' — base+ur
                    # was the only config producing fast, usable Urdu-script
                    # captions in benchmarking (hi pins degraded to garbage).
                    det = next((s.language for s in segments if s.language), None)
                    if det:
                        lang_by_peer[peer_id] = "en" if det == "en" else "ur"
                for seg in segments:
                    entry = {
                        "speaker": seg.speaker,
                        "text": seg.text,
                        "start_ms": seg.start_ms,
                        "end_ms": seg.end_ms,
                        "language": seg.language,
                    }
                    state.segments.append(entry)
                    state.last_speaker = seg.speaker
                    state.new_content_since_cycle = True
                    new_text = True
                    # Who SAID the flagged content is the suspect — alert the
                    # other side, even if the victim replies afterwards.
                    if run_tier1_message(seg.text, position_s=seg.start_ms / 1000.0):
                        flagged_user = state.speaker_users.get(seg.speaker)
                        if flagged_user:
                            _flag_speaker(state, flagged_user)
                    await HUB.push_risk(state.session_id, {
                        "type": "transcript_segment",
                        "username": state.speaker_users.get(seg.speaker, ""),
                        **entry,
                    })

            if new_text:
                await _fast_voice_score(state)
    except asyncio.CancelledError:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"[stt] loop error: {exc}")


async def _flush_call_audio(state: SessionState) -> None:
    """Transcribe whatever audio is still buffered when the call ends.

    The live loop only fires on full 2.5 s windows, so the call's final
    words would otherwise be dropped with the buffer — the "my paragraph was
    missed" bug. Runs after the loops are cancelled; pushes any late
    captions and a final fast score so a scam uttered seconds before
    hang-up still alerts.
    """
    try:
        from stt.service import is_available
        from stt_stream import buffered_bytes, peer_keys

        if not is_available():
            return
        lang_by_peer = _LANG_BY_PEER.get(state.session_id, {})
        new_text = False
        for key in peer_keys(state.session_id):
            if buffered_bytes(key) < STT_MIN_AUDIO_BYTES:
                continue
            peer_id = key.split(":", 1)[1]
            uname = state.call_peer_users.get(peer_id)
            label = next(
                (lbl for lbl, u in state.speaker_users.items() if u == uname),
                None,
            )
            if label is None:
                label = "them" if "them" not in state.speaker_users else "me"
                if uname:
                    state.speaker_users[label] = uname
            offset_ms = int(
                max(0.0, time.time() - (state.call_started_ts or time.time())) * 1000
            )
            segments = await _transcribe_peer(
                key, label, offset_ms,
                language=lang_by_peer.get(peer_id),
                detect=peer_id not in lang_by_peer,
            )
            for seg in segments:
                entry = {
                    "speaker": seg.speaker,
                    "text": seg.text,
                    "start_ms": seg.start_ms,
                    "end_ms": seg.end_ms,
                    "language": seg.language,
                }
                state.segments.append(entry)
                state.new_content_since_cycle = True
                new_text = True
                if run_tier1_message(seg.text, position_s=seg.start_ms / 1000.0):
                    flagged_user = state.speaker_users.get(seg.speaker)
                    if flagged_user:
                        _flag_speaker(state, flagged_user)
                await HUB.push_risk(state.session_id, {
                    "type": "transcript_segment",
                    "username": state.speaker_users.get(seg.speaker, ""),
                    **entry,
                })
        if new_text:
            await _fast_voice_score(state)
    except Exception as exc:  # noqa: BLE001
        print(f"[stt] flush failed: {exc}")


async def _fast_voice_score(state: SessionState) -> None:
    """Sub-100 ms scoring pass (Tier-1 rules + trained ML + caller-ID directory).

    Runs the instant new transcript lands — the scam alert can fire before the
    Tier-2 cloud LLM answers. Only pushes when the score actually rises so the
    slower full cycle (which adds Tier-2 confirmation) stays the authority.
    """
    try:
        window = state.segments[-20:]
        if not window:
            return
        msgs = [
            ParsedMessage(message_id=f"seg_{i}", speaker=s["speaker"], text=s["text"])
            for i, s in enumerate(window)
        ]
        if not any(m.text.strip() for m in msgs):
            return
        analysis = await analyze_messages(
            msgs,
            cross_channel_otp=state.cross_channel_armed,
            previous_score=state.displayed_score,
            caller_number=state.caller_number,
            use_llm=False,
        )
        if analysis.score > state.displayed_score + 0.5:
            await _record_and_push(state, analysis)
    except Exception as exc:  # noqa: BLE001
        print(f"[voice-fast] {exc}")


async def _voice_rescore_loop(state: SessionState) -> None:
    """Rolling 2–4 s re-score of the growing transcript (Bible Sections 3, 8.4).

    Full fusion path — identical to chat: Tier-1 rules + trained ML tier +
    Tier-2 cloud LLM race + caller-ID directory, capped and ratcheted by the
    deterministic scorer.
    """
    try:
        while state.call_active:
            await asyncio.sleep(VOICE_RESCORE_INTERVAL_S)
            if not state.new_content_since_cycle:
                continue
            state.new_content_since_cycle = False
            from main import REGISTRY

            window_segments = state.segments[-20:]
            prompt_msgs = [
                ParsedMessage(message_id=f"seg_{i}", speaker=s["speaker"], text=s["text"])
                for i, s in enumerate(window_segments)
            ]
            if not any(m.text.strip() for m in prompt_msgs):
                continue

            include_local = not (state.primary_model_override == "cloud")
            analysis = await analyze_messages(
                prompt_msgs,
                REGISTRY,
                cross_channel_otp=state.cross_channel_armed,
                previous_score=state.displayed_score,
                include_local=include_local,
                local_timeout_s=float(os.getenv("LIVE_LOCAL_TIMEOUT_S", "3")),
                caller_number=state.caller_number,
                live_budget_s=LIVE_TIER2_BUDGET_S,
            )
            state.cross_channel_armed = False

            METRICS.tier2_cycles += 1
            for res in analysis.model_results:
                METRICS.parse_attempts += 1
                if res.parse_failed:
                    METRICS.parse_failures += 1
                bucket = "latency_local" if res.provider == "ollama" else "latency_cloud"
                getattr(METRICS, bucket).append(res.latency_ms)
                if res.provider == "ollama":
                    note_local_latency(res.latency_ms)

            # Bible 8.4 auto-switch: local >6 s twice consecutively -> cloud primary
            local_results = [r for r in analysis.model_results if r.provider == "ollama"]
            if local_results and local_results[0].latency_ms > 6000:
                state.local_slow_cycles += 1
                if state.local_slow_cycles >= 2:
                    state.primary_model_override = "cloud"
            elif local_results:
                state.local_slow_cycles = 0

            await _record_and_push(state, analysis)
    except asyncio.CancelledError:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"[voice-rescore] {exc}")


# ================================================================ risk & dashboard channels
async def risk_endpoint(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    await HUB.join_risk(session_id, ws)
    state = SESSIONS.get(session_id)
    if state:
        await ws.send_json(_risk_payload(state))
    try:
        while True:
            await ws.receive_text()   # keepalive pings from clients
    except WebSocketDisconnect:
        pass
    finally:
        HUB.leave_risk(session_id, ws)


async def dashboard_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    await HUB.join_dashboard(ws)
    await ws.send_json({"type": "hello", "sessions": len(SESSIONS)})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        HUB.leave_dashboard(ws)
