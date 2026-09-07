#!/usr/bin/env python3
"""Seed demo user accounts for the TrustGuard gateway (idempotent).

Creates the 5 demo users used by the apps' contact list. Safe to re-run:
existing usernames are skipped.

Usage (repo root):
    .venv/bin/python scripts/seed_accounts.py
"""

from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "services"))
sys.path.insert(0, os.path.join(ROOT, "services", "realtime-gateway"))
os.chdir(ROOT)   # DATABASE_URL default is a relative sqlite path (data/trustguard.db)

from accounts import (  # noqa: E402
    create_user,
    get_user_by_username,
    init_accounts,
    list_users,
)

DEMO_USERS = [
    ("alice", "demo123", "Alice"),
    ("bob", "demo123", "Bob"),
    ("carol", "demo123", "Carol"),
    ("dave", "demo123", "Dave"),
    ("eve", "demo123", "Eve"),
]


async def main() -> None:
    await init_accounts()
    print("Seeding demo accounts into", os.getenv("DATABASE_URL",
                                                  "sqlite+aiosqlite:///data/trustguard.db"))
    created = 0
    for username, password, display in DEMO_USERS:
        existing = await get_user_by_username(username)
        if existing:
            print(f"  = {username:8s} exists ({existing.user_id}) — skipped")
            continue
        user = await create_user(username, password, display)
        created += 1
        print(f"  + {username:8s} created ({user.user_id}, display '{user.display_name}')")
    users = await list_users()
    print(f"\nDone: {created} created, {len(users)} total user(s) in DB")


if __name__ == "__main__":
    asyncio.run(main())
