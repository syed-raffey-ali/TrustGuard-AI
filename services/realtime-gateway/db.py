"""Persistence layer — Build Bible Section 13 data model (SQLAlchemy, async).

PostgreSQL when reachable (docker compose), automatic SQLite fallback for
laptop development so the prototype never hard-fails on a missing DB
(documented assumption in docs/assumptions.md).
"""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    event,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Device(Base):
    __tablename__ = "devices"
    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    registered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SessionRow(Base):
    __tablename__ = "sessions"
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(16))            # call | chat | paste | replay
    mode: Mapped[str] = mapped_column(String(16), default="live")
    device_a: Mapped[Optional[str]] = mapped_column(String(64))
    device_b: Mapped[Optional[str]] = mapped_column(String(64))
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    final_score: Mapped[Optional[float]] = mapped_column(Float)
    final_band: Mapped[Optional[str]] = mapped_column(String(16))


class Event(Base):
    __tablename__ = "events"
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[str] = mapped_column(String(32))   # AUDIO_CHUNK|TEXT|SIGNAL|SCORE_UPDATE
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    actor: Mapped[str] = mapped_column(String(64), default="")
    payload_ref: Mapped[str] = mapped_column(Text, default="")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    segment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    speaker: Mapped[str] = mapped_column(String(64))
    start_ms: Mapped[int] = mapped_column(Integer, default=0)
    end_ms: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(24), default="mixed")


class Message(Base):
    __tablename__ = "messages"
    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    speaker: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(24), default="mixed")
    delivered_to: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of usernames
    read_by: Mapped[str] = mapped_column(Text, default="[]")       # JSON list of usernames


class Signal(Base):
    __tablename__ = "signals"
    signal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[int] = mapped_column(Integer, default=3)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence_event_ids: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    tier: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ScoreHistory(Base):
    __tablename__ = "score_history"
    entry_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    score: Mapped[float] = mapped_column(Float)
    band: Mapped[str] = mapped_column(String(16))


class ModelComparison(Base):
    __tablename__ = "model_comparisons"
    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    cycle_ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    model: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(64), default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    signals_json: Mapped[str] = mapped_column(Text, default="[]")
    would_be_score: Mapped[Optional[float]] = mapped_column(Float)
    error: Mapped[Optional[str]] = mapped_column(Text)


class DemoBankAction(Base):
    __tablename__ = "demo_bank_actions"
    action_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    result: Mapped[str] = mapped_column(String(255), default="")


class AuditEvent(Base):
    """No raw audio/text per privacy rules (Bible Section 17)."""
    __tablename__ = "audit_events"
    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/trustguard.db")
if DATABASE_URL.startswith("postgresql"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if DATABASE_URL.startswith("sqlite"):
            await _sqlite_migrations(conn)


async def _sqlite_migrations(conn) -> None:
    """Add columns introduced after the first DB creation."""
    result = await conn.execute(text("PRAGMA table_info(messages)"))
    cols = {row[1] for row in result.fetchall()}
    if "delivered_to" not in cols:
        await conn.execute(text(
            "ALTER TABLE messages ADD COLUMN delivered_to TEXT DEFAULT '[]'"
        ))
    if "read_by" not in cols:
        await conn.execute(text(
            "ALTER TABLE messages ADD COLUMN read_by TEXT DEFAULT '[]'"
        ))
    # WhatsApp-style phone numbers on accounts.
    result = await conn.execute(text("PRAGMA table_info(users)"))
    user_cols = {row[1] for row in result.fetchall()}
    if "phone_number" not in user_cols:
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN phone_number VARCHAR(24) DEFAULT ''"
        ))


async def save_session_snapshot(
    session_id: str,
    messages: list[tuple[str, str]],
    signals_payload: list[dict],
    score: float,
    band: str,
    model_rows: Optional[list[dict]] = None,
    session_type: str = "paste",
) -> None:
    """Persist one analysis snapshot (paste pipeline / replay)."""
    import uuid

    async with SessionFactory() as db:
        if session_type == "paste" and not await db.get(SessionRow, session_id):
            db.add(SessionRow(session_id=session_id, type=session_type, mode="live"))
        now = _utcnow()
        for i, (speaker, text) in enumerate(messages):
            db.add(Message(message_id=f"{session_id}_m{i}", session_id=session_id,
                           speaker=speaker, text=text, timestamp=now))
        for s in signals_payload:
            db.add(Signal(session_id=session_id, type=s["type"],
                          severity=int(s.get("severity_norm", 0) * 5) or 3,
                          confidence=float(s.get("confidence", 0)),
                          evidence_event_ids=json.dumps(s.get("evidence", {})), tier=s.get("tier", 2)))
        db.add(ScoreHistory(session_id=session_id, score=score, band=band))
        for row in model_rows or []:
            db.add(ModelComparison(
                session_id=session_id, cycle_ts=now, model=row.get("model", ""),
                provider=row.get("provider", ""), latency_ms=row.get("latency_ms", 0),
                signals_json=json.dumps(row.get("signals", [])),
                would_be_score=None, error=row.get("error"),
            ))
        sess = await db.get(SessionRow, session_id)
        if sess:
            sess.final_score = score
            sess.final_band = band
            sess.ended_at = now
        db.add(Event(session_id=session_id, type="SCORE_UPDATE", actor="scoring",
                     payload_ref=f"score={score} band={band}"))
        await db.commit()


def rows_to_dicts(rows: Any) -> list[dict]:
    return [dict(r._mapping) for r in rows]
