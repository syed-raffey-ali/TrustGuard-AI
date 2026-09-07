"""Live session state + WebSocket hub — Build Bible Sections 11, 14."""

from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket

from parsing import ParsedMessage


OTP_PATTERN = re.compile(r"\b(\d[\d\s-]{3,9})\b")
OTP_KEYWORDS = ("otp", "code", "pin", "password", "کوڈ", "پن")


@dataclass
class SessionState:
    session_id: str
    type: str                                  # call | chat | paste | replay
    mode: str = "live"
    device_a: Optional[str] = None
    device_b: Optional[str] = None
    started_ts: float = field(default_factory=time.time)

    messages: list[ParsedMessage] = field(default_factory=list)      # text channel
    segments: list[dict] = field(default_factory=list)               # voice transcript segments

    displayed_score: float = 0.0
    band: str = "low"
    score_history: list[dict] = field(default_factory=list)
    last_signals: list[dict] = field(default_factory=list)
    stage: Optional[str] = None

    cross_channel_events: list[dict] = field(default_factory=list)   # OTP msgs arriving during call
    cross_channel_armed: bool = False        # consumed by next scoring cycle
    call_started_ts: Optional[float] = None
    call_active: bool = False

    # Scam-alert routing: who spoke most recently, and how voice speaker
    # labels ("them"/"me") map back to account usernames, so the risk
    # payload can name exactly which participant(s) are potential victims.
    last_speaker: str = ""
    speaker_users: dict[str, str] = field(default_factory=dict)   # speaker label -> username
    call_peer_users: dict[str, str] = field(default_factory=dict) # call peer_id -> username
    # Usernames (lowercased) whose OWN content triggered detection signals —
    # the suspected scammers. Alerts target the other participants, no matter
    # who spoke most recently. flagged_order preserves WHO WAS FLAGGED FIRST —
    # victims often echo flagged content back (reading an OTP aloud), which
    # flags them too; the earliest flagger stays the primary suspect.
    flagged_speakers: set[str] = field(default_factory=set)
    flagged_order: list[str] = field(default_factory=list)

    scoring_task: Optional[asyncio.Task] = None
    new_content_since_cycle: bool = False
    local_slow_cycles: int = 0
    primary_model_override: Optional[str] = None     # auto-switch state
    director_script: Optional[list[str]] = None
    linked_call_id: Optional[str] = None      # explicit Phase-2.5 chat→call link
    caller_number: Optional[str] = None       # caller ID for directory verification


# User-specific notification sockets (incoming calls, new messages).
USER_SOCKETS: dict[str, set[WebSocket]] = {}

# Which usernames are currently inside each chat room (session_id -> set of users).
CHAT_USERS: dict[str, set[str]] = {}


class Hub:
    """WebSocket fan-out for risk updates and dashboard events + chat/call rooms."""

    def __init__(self) -> None:
        self.risk_subs: dict[str, set[WebSocket]] = {}
        self.dashboard_subs: set[WebSocket] = set()
        self.chat_rooms: dict[str, set[WebSocket]] = {}
        self.call_rooms: dict[str, dict[str, WebSocket]] = {}   # session -> peer_id -> ws

    # ---- risk channel -------------------------------------------------
    async def join_risk(self, session_id: str, ws: WebSocket) -> None:
        self.risk_subs.setdefault(session_id, set()).add(ws)

    def leave_risk(self, session_id: str, ws: WebSocket) -> None:
        self.risk_subs.get(session_id, set()).discard(ws)

    async def push_risk(self, session_id: str, payload: dict) -> int:
        subs = list(self.risk_subs.get(session_id, set()))
        return await self._broadcast(subs, payload)

    # ---- dashboard channel --------------------------------------------
    async def join_dashboard(self, ws: WebSocket) -> None:
        self.dashboard_subs.add(ws)

    def leave_dashboard(self, ws: WebSocket) -> None:
        self.dashboard_subs.discard(ws)

    async def push_dashboard(self, payload: dict) -> int:
        return await self._broadcast(list(self.dashboard_subs), payload)

    # ---- chat room ------------------------------------------------------
    def join_chat(self, session_id: str, ws: WebSocket) -> None:
        self.chat_rooms.setdefault(session_id, set()).add(ws)

    def leave_chat(self, session_id: str, ws: WebSocket) -> None:
        self.chat_rooms.get(session_id, set()).discard(ws)

    def mark_chat_user(self, session_id: str, username: str, present: bool) -> None:
        users = CHAT_USERS.setdefault(session_id, set())
        if present:
            users.add(username.lower())
        else:
            users.discard(username.lower())

    async def push_chat(self, session_id: str, payload: dict) -> int:
        """Broadcast a payload to everyone in a chat room (receipts, etc.)."""
        peers = list(self.chat_rooms.get(session_id, set()))
        return await self._broadcast(peers, payload)

    async def chat_peers(self, session_id: str, sender: WebSocket) -> int:
        peers = [w for w in self.chat_rooms.get(session_id, set()) if w is not sender]
        return await self._broadcast(peers, {"type": "relay"}, suppress_payload=True)

    # ---- call room -------------------------------------------------------
    def join_call(self, session_id: str, peer_id: str, ws: WebSocket) -> None:
        self.call_rooms.setdefault(session_id, {})[peer_id] = ws

    def leave_call(self, session_id: str, peer_id: str) -> None:
        self.call_rooms.get(session_id, {}).pop(peer_id, None)

    def call_peer(self, session_id: str, peer_id: str) -> Optional[WebSocket]:
        return self.call_rooms.get(session_id, {}).get(peer_id)

    def call_other(self, session_id: str, peer_id: str) -> Optional[WebSocket]:
        for pid, ws in self.call_rooms.get(session_id, {}).items():
            if pid != peer_id:
                return ws
        return None

    # ---- user notifications ------------------------------------------------
    async def notify_user(self, username: str, payload: dict) -> int:
        """Push a notification to all sockets registered for a user."""
        sockets = list(USER_SOCKETS.get(username.lower(), set()))
        return await self._broadcast(sockets, payload)

    # ---- generic ----------------------------------------------------------
    @staticmethod
    async def _broadcast(sockets: list[WebSocket], payload: dict,
                        suppress_payload: bool = False) -> int:
        sent = 0
        for ws in sockets:
            try:
                if not suppress_payload:
                    await ws.send_json(payload)
                else:
                    pass  # peer-specific payloads are sent by callers directly
                sent += 1
            except Exception:
                pass
        return sent


class Metrics:
    """Rolling metrics bar counters — Bible Section 12."""

    def __init__(self) -> None:
        self.sessions_analyzed = 0
        self.latency_local: deque[int] = deque(maxlen=50)
        self.latency_cloud: deque[int] = deque(maxlen=50)
        self.parse_failures = 0
        self.parse_attempts = 0
        self.tier2_cycles = 0

    @staticmethod
    def _median(values: deque[int]) -> Optional[int]:
        if not values:
            return None
        ordered = sorted(values)
        n = len(ordered)
        mid = ordered[n // 2]
        if n % 2 == 0:
            return int((ordered[n // 2 - 1] + mid) / 2)
        return mid

    def snapshot(self, active_devices: int, golden_badge: dict | None = None) -> dict:
        failures = (self.parse_failures / self.parse_attempts) if self.parse_attempts else 0.0
        return {
            "sessions_analyzed": self.sessions_analyzed,
            "active_devices": active_devices,
            "median_tier2_latency_ms_local": self._median(self.latency_local),
            "median_tier2_latency_ms_cloud": self._median(self.latency_cloud),
            "json_parse_failure_rate": round(failures, 4),
            "tier2_cycles": self.tier2_cycles,
            "golden_set_badge": golden_badge,
        }


def looks_like_otp(text: str) -> bool:
    if not OTP_PATTERN.search(text):
        return False
    lowered = text.lower()
    return any(k in lowered for k in OTP_KEYWORDS)


SESSIONS: dict[str, SessionState] = {}
HUB = Hub()
METRICS = Metrics()


def get_or_create_session(session_id: str, stype: str = "chat",
                          device_a: str | None = None, device_b: str | None = None) -> SessionState:
    if session_id not in SESSIONS:
        SESSIONS[session_id] = SessionState(
            session_id=session_id, type=stype, device_a=device_a, device_b=device_b
        )
    return SESSIONS[session_id]


def append_message(state: SessionState, speaker: str, text: str,
                   message_id: str | None = None) -> ParsedMessage:
    msg = ParsedMessage(
        message_id=message_id or f"m_{len(state.messages) + 1}",
        speaker=speaker, text=text,
    )
    state.messages.append(msg)
    state.new_content_since_cycle = True
    return msg


async def arm_cross_channel(state: SessionState, text: str) -> bool:
    """OTP-format chat message arriving while THIS session's call is active -> +10."""
    if state.call_active and looks_like_otp(text):
        state.cross_channel_events.append({"ts": time.time(), "text": text})
        state.cross_channel_armed = True
        return True
    return False


def find_linked_calls(state: SessionState) -> list[SessionState]:
    """Active call sessions sharing a device pair (or an explicit link) with `state`.

    Powers Phase 2.5: an OTP-format message landing on the chat channel during a
    live call arms the +10 cross-channel modifier on the CALL session.
    """
    if state.type == "call":
        return [state] if state.call_active else []
    explicit = getattr(state, "linked_call_id", None)
    out: list[SessionState] = []
    for other in SESSIONS.values():
        if other.session_id == state.session_id or other.type != "call" or not other.call_active:
            continue
        if explicit:
            if other.session_id == explicit:
                out.append(other)
            continue
        pair_a = {state.device_a, state.device_b}
        pair_b = {other.device_a, other.device_b}
        if state.device_a is None or pair_a & pair_b:
            out.append(other)
    return out
