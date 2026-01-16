from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional, Dict
from uuid import uuid4

import asyncpg


@dataclass
class Database:
    db_url: str
    _pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.db_url,
                min_size=1,
                max_size=10,
            )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def execute(self, query: str, *args):
        if self._pool is None:
            raise RuntimeError("Database pool is not connected")
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetchrow(self, query: str, *args):
        if self._pool is None:
            raise RuntimeError("Database pool is not connected")
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        if self._pool is None:
            raise RuntimeError("Database pool is not connected")
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)


def _to_jsonb(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


# ----------------------------
# sessions
# ----------------------------

async def create_session(db: Database, *, user_id: str, session_id: Optional[str] = None) -> str:
    sid = session_id or str(uuid4())
    await db.execute(
        """
        insert into sessions (session_id, user_id, status)
        values ($1, $2, 'RUNNING')
        on conflict (session_id) do update
        set updated_at = now()
        """,
        sid,
        user_id,
    )
    return sid


async def update_session_status(db: Database, *, session_id: str, status: str) -> None:
    await db.execute(
        """
        update sessions
        set status = $2,
            updated_at = now()
        where session_id = $1
        """,
        session_id,
        status,
    )


# ----------------------------
# intents
# ----------------------------

async def create_intent(db: Database, *, session_id: str, intent_type: str) -> str:
    iid = str(uuid4())
    await db.execute(
        """
        insert into intents (intent_id, session_id, intent_type, status, created_at, updated_at)
        values ($1, $2, $3, 'RUNNING', now(), now())
        """,
        iid,
        session_id,
        intent_type,
    )
    return iid


async def finish_intent(db: Database, *, intent_id: str, status: str = "DONE") -> None:
    await db.execute(
        """
        update intents
        set status = $2,
            updated_at = now()
        where intent_id = $1
        """,
        intent_id,
        status,
    )


# ----------------------------
# events
# ----------------------------

async def log_event(
    db: Database,
    *,
    session_id: str,
    intent_id: Optional[str],
    role: str,
    event_type: str,
    name: Optional[str] = None,
    input: Optional[Dict[str, Any]] = None,
    output: Optional[Dict[str, Any]] = None,
) -> None:
    await db.execute(
        """
        insert into events (
          session_id, intent_id,
          role, event_type, name,
          input, output
        )
        values (
          $1, $2,
          $3, $4, $5,
          $6::jsonb, $7::jsonb
        )
        """,
        session_id,
        intent_id,
        role,
        event_type,
        name,
        _to_jsonb(input),
        _to_jsonb(output),
    )


# ----------------------------
# artifacts
# ----------------------------

async def save_artifact(
    db: Database,
    *,
    session_id: str,
    intent_id: Optional[str],
    type: str,
    name: str,
    data: Dict[str, Any],
) -> None:
    await db.execute(
        """
        insert into artifacts (artifact_id, session_id, intent_id, type, name, data)
        values ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        str(uuid4()),
        session_id,
        intent_id,
        type,
        name,
        _to_jsonb(data),
    )
