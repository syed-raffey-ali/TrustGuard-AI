"""User accounts — register/login with PBKDF2-HMAC-SHA256 password hashing.

Stdlib-only crypto (hashlib.pbkdf2_hmac + os.urandom + secrets — no new
dependencies). Storage reuses the async SQLAlchemy engine from db.py, so
users live in the same SQLite/Postgres DB as the rest of the gateway
(DATABASE_URL env, default sqlite+aiosqlite:///data/trustguard.db).

Auth tokens are opaque random strings (secrets.token_urlsafe(32)) mapped to
user_id in memory with a 24 h expiry — demo-grade, no external session store.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from db import Base, SessionFactory, engine

# ------------------------------------------------------------------ policy
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")     # 3-30 chars, alnum + _
PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")            # +923001234567 style
MIN_PASSWORD_LEN = 6
PBKDF2_ITERATIONS = 240_000                           # OWASP 2023 guidance for SHA-256
SALT_BYTES = 16
TOKEN_TTL_S = 24 * 3600                               # 24 h


# ------------------------------------------------------------------ errors
class AccountError(Exception):
    """Base class for account-domain errors (mapped to HTTP codes in main.py)."""


class InvalidUsernameError(AccountError):
    pass


class InvalidPasswordError(AccountError):
    pass


class UsernameTakenError(AccountError):
    pass


class InvalidPhoneError(AccountError):
    pass


class PhoneTakenError(AccountError):
    pass


# ------------------------------------------------------------------ domain object
@dataclass
class User:
    user_id: str
    username: str
    password_hash: str                                 # hex(PBKDF2-HMAC-SHA256)
    salt: str                                          # hex(os.urandom(16))
    display_name: str
    created_at: str                                    # ISO-8601
    device_ids: list[str] = field(default_factory=list)
    phone_number: str = ""                             # WhatsApp-style contact number

    def summary(self) -> dict:
        """Safe projection for API responses — never includes hash/salt."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "created_at": self.created_at,
            "device_ids": list(self.device_ids),
            "phone_number": self.phone_number,
        }


# ------------------------------------------------------------------ ORM table (same DB as db.py)
class UserRow(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    salt: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    device_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    phone_number: Mapped[str] = mapped_column(String(24), default="", index=True)


async def init_accounts() -> None:
    """Create the users table if missing (idempotent — safe to call repeatedly)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ------------------------------------------------------------------ hashing
def hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                               PBKDF2_ITERATIONS).hex()


def _row_to_user(row: UserRow) -> User:
    created = row.created_at
    if isinstance(created, dt.datetime):
        created = created.isoformat()
    try:
        device_ids = json.loads(row.device_ids_json or "[]")
    except (TypeError, ValueError):
        device_ids = []
    return User(
        user_id=row.user_id,
        username=row.username,
        password_hash=row.password_hash,
        salt=row.salt,
        display_name=row.display_name,
        created_at=str(created),
        device_ids=list(device_ids),
        phone_number=getattr(row, "phone_number", "") or "",
    )


# ------------------------------------------------------------------ CRUD
async def create_user(username: str, password: str,
                      display_name: str | None = None,
                      phone_number: str | None = None) -> User:
    """Validate, hash and persist a new user. Raises InvalidUsernameError /
    InvalidPasswordError / UsernameTakenError / InvalidPhoneError / PhoneTakenError."""
    username = (username or "").strip()
    if not USERNAME_RE.fullmatch(username):
        raise InvalidUsernameError(
            "username must be 3-30 chars, alphanumeric + underscore")
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise InvalidPasswordError(f"password must be at least {MIN_PASSWORD_LEN} chars")
    phone = (phone_number or "").replace(" ", "").replace("-", "").strip()
    if phone and not PHONE_RE.fullmatch(phone):
        raise InvalidPhoneError(
            "phone number must be 7-15 digits, optional leading '+'")

    salt = os.urandom(SALT_BYTES)
    password_hash = hash_password(password, salt)
    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    now = dt.datetime.now(dt.timezone.utc)

    async with SessionFactory() as db:
        existing = (await db.execute(
            select(UserRow).where(UserRow.username == username))).scalar_one_or_none()
        if existing:
            raise UsernameTakenError(f"username '{username}' is already taken")
        if phone:
            taken = (await db.execute(
                select(UserRow).where(UserRow.phone_number == phone))).scalar_one_or_none()
            if taken:
                raise PhoneTakenError(f"phone number '{phone}' is already registered")
        db.add(UserRow(
            user_id=user_id,
            username=username,
            password_hash=password_hash,
            salt=salt.hex(),
            display_name=(display_name or username).strip()[:120] or username,
            created_at=now,
            device_ids_json="[]",
            phone_number=phone,
        ))
        try:
            await db.commit()
        except IntegrityError as exc:                  # unique race backstop
            await db.rollback()
            raise UsernameTakenError(f"username '{username}' is already taken") from exc
    return User(user_id=user_id, username=username, password_hash=password_hash,
                salt=salt.hex(),
                display_name=(display_name or username).strip()[:120] or username,
                created_at=now.isoformat(), device_ids=[], phone_number=phone)


async def authenticate(username: str, password: str) -> Optional[User]:
    """Return the User when username/password match, else None (constant-time compare)."""
    if not username or not password:
        return None
    async with SessionFactory() as db:
        row = (await db.execute(
            select(UserRow).where(UserRow.username == username.strip()))).scalar_one_or_none()
        if not row:
            return None
        candidate = hash_password(password, bytes.fromhex(row.salt))
        if not secrets.compare_digest(candidate, row.password_hash):
            return None
        return _row_to_user(row)


async def get_user(user_id: str) -> Optional[User]:
    async with SessionFactory() as db:
        row = await db.get(UserRow, user_id)
        return _row_to_user(row) if row else None


async def get_user_by_username(username: str) -> Optional[User]:
    async with SessionFactory() as db:
        row = (await db.execute(
            select(UserRow).where(UserRow.username == username.strip()))).scalar_one_or_none()
        return _row_to_user(row) if row else None


async def list_users() -> list[User]:
    async with SessionFactory() as db:
        rows = (await db.execute(
            select(UserRow).order_by(UserRow.created_at, UserRow.username))).scalars().all()
        return [_row_to_user(r) for r in rows]


async def link_device(user_id: str, device_id: str) -> None:
    """Associate a device_id with a user (no-op for unknown user/duplicate)."""
    if not device_id:
        return
    async with SessionFactory() as db:
        row = await db.get(UserRow, user_id)
        if not row:
            return
        try:
            devices = json.loads(row.device_ids_json or "[]")
        except (TypeError, ValueError):
            devices = []
        if device_id not in devices:
            devices.append(device_id)
            row.device_ids_json = json.dumps(devices)
            await db.commit()


# ------------------------------------------------------------------ auth tokens (in-memory, 24 h)
# token -> (user_id, expires_at_unix)
_tokens: dict[str, tuple[str, float]] = {}


def _prune_expired() -> None:
    now = time.time()
    for token in [t for t, (_, exp) in _tokens.items() if exp <= now]:
        _tokens.pop(token, None)


def issue_token(user_id: str) -> str:
    _prune_expired()
    token = secrets.token_urlsafe(32)
    _tokens[token] = (user_id, time.time() + TOKEN_TTL_S)
    return token


def validate_token(token: str) -> Optional[str]:
    """Return user_id for a live token, else None."""
    if not token:
        return None
    entry = _tokens.get(token)
    if not entry:
        return None
    user_id, expires = entry
    if time.time() > expires:
        _tokens.pop(token, None)
        return None
    return user_id


def revoke_token(token: str) -> bool:
    """Invalidate a token (logout). Returns True if it was live."""
    return _tokens.pop(token, None) is not None


def revoke_all_tokens_for(user_id: str) -> int:
    """Invalidate every token belonging to a user. Returns count revoked."""
    revoked = [t for t, (uid, _) in _tokens.items() if uid == user_id]
    for t in revoked:
        _tokens.pop(t, None)
    return len(revoked)


async def user_from_token(token: str) -> Optional[User]:
    """Convenience for WS auth: token -> full User (or None)."""
    user_id = validate_token(token)
    if not user_id:
        return None
    return await get_user(user_id)
