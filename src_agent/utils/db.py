from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional, Dict
from uuid import uuid4

import asyncpg

logger = logging.getLogger("src_agent.db")


@dataclass
class Database:
    """
    Minimal asyncpg pool wrapper.

    In `src_agent` Postgres is used for:
    - `sessions` table (create/update status)
    - `intents/events` tables (best-effort audit)
    """
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
    # Keep JSON ASCII-safe in logs/events; payloads may still contain UTF-8 text.
    return json.dumps(value, ensure_ascii=True)


# ----------------------------
# sessions
# ----------------------------

async def create_session(db: Database, *, user_id: str, session_id: Optional[str] = None) -> str:
    sid = session_id or str(uuid4())
    # External services may provide session_id; use upsert so later FK inserts do not fail.
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
# events
# ----------------------------

def _attach_trace(payload: Optional[Dict[str, Any]], request_id: str) -> Dict[str, Any]:
    if payload is None:
        return {"trace": {"request_id": request_id}}
    if not isinstance(payload, dict):
        return {"trace": {"request_id": request_id}, "value": payload}
    trace = payload.get("trace")
    if isinstance(trace, dict) and trace.get("request_id") == request_id:
        return payload
    merged = dict(payload)
    merged_trace: Dict[str, Any] = dict(trace) if isinstance(trace, dict) else {}
    merged_trace.setdefault("request_id", request_id)
    merged["trace"] = merged_trace
    return merged


async def log_event(
    db: Database,
    *,
    session_id: str,
    request_id: Optional[str],
    role: str,
    event_type: str,
    name: Optional[str] = None,
    input: Optional[Dict[str, Any]] = None,
    output: Optional[Dict[str, Any]] = None,
) -> None:
    # Events are best-effort:
    # - if intents upsert fails (e.g. schema mismatch), still try to write the event row;
    #   also attach request_id into JSONB for later debugging.
    intent_id = request_id
    db_input = input
    db_output = output

    if db._pool is None:
        raise RuntimeError("Database pool is not connected")

    async with db._pool.acquire() as conn:
        if request_id:
            try:
                await conn.execute(
                    """
                    insert into intents (intent_id, session_id, intent_type, status)
                    values ($1, $2, 'request', 'RUNNING')
                    on conflict (intent_id) do update
                    set updated_at = now()
                    """,
                    request_id,
                    session_id,
                )
            except asyncpg.PostgresError as exc:
                logger.warning(
                    "Failed to upsert request trace row into intents; events.intent_id will be NULL. error=%s",
                    str(exc),
                )
                intent_id = None
                db_input = _attach_trace(input, request_id)
                db_output = _attach_trace(output, request_id)

        try:
            await conn.execute(
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
                _to_jsonb(db_input),
                _to_jsonb(db_output),
            )
        except asyncpg.PostgresError as exc:
            logger.warning(
                "Failed to insert event row; skipped. error=%s",
                str(exc),
            )
