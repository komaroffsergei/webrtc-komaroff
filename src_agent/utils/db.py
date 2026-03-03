from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional
from uuid import uuid4

import asyncpg


@dataclass
class Database:
    """Minimal asyncpg pool wrapper."""

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


def _to_jsonb(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True)


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
    return str(sid)


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


async def chat_turn_exists(db: Database, *, session_id: str, turn_id: str) -> bool:
    exists = await db.fetchval(
        """
        select exists(
          select 1
          from events
          where session_id = $1
            and turn_id = $2
            and lower(role) = 'user'
          limit 1
        )
        """,
        session_id,
        turn_id,
    )
    return bool(exists)


async def persist_chat_turn(
    db: Database,
    *,
    session_id: str,
    user_turn_id: str,
    user_text: str,
    assistant_turn_id: str,
    assistant_text: str,
    edit_from_turn_id: str | None = None,
    user_meta: dict[str, Any] | None = None,
    assistant_meta: dict[str, Any] | None = None,
) -> None:
    if db._pool is None:
        raise RuntimeError("Database pool is not connected")

    async with db._pool.acquire() as conn:
        async with conn.transaction():
            if edit_from_turn_id:
                anchor = await conn.fetchval(
                    """
                    select event_id
                    from events
                    where session_id = $1
                      and turn_id = $2
                      and lower(role) = 'user'
                    order by event_id
                    limit 1
                    """,
                    session_id,
                    edit_from_turn_id,
                )
                if anchor is None:
                    raise ValueError("edit_turn_not_found")

                await conn.execute(
                    """
                    delete from events
                    where session_id = $1
                      and event_id >= $2
                    """,
                    session_id,
                    anchor,
                )

            await conn.execute(
                """
                insert into events (session_id, turn_id, role, text, meta)
                values ($1, $2, 'user', $3, $4::jsonb)
                on conflict (session_id, turn_id) do update
                set role = excluded.role,
                    text = excluded.text,
                    meta = excluded.meta,
                    created_at = now()
                """,
                session_id,
                user_turn_id,
                user_text,
                _to_jsonb(user_meta),
            )

            await conn.execute(
                """
                insert into events (session_id, turn_id, role, text, meta)
                values ($1, $2, 'assistant', $3, $4::jsonb)
                on conflict (session_id, turn_id) do update
                set role = excluded.role,
                    text = excluded.text,
                    meta = excluded.meta,
                    created_at = now()
                """,
                session_id,
                assistant_turn_id,
                assistant_text,
                _to_jsonb(assistant_meta),
            )


async def fetch_chat_history(
    db: Database,
    *,
    session_id: str,
    limit: int = 200,
) -> list[dict[str, Any]]:
    if db._pool is None:
        raise RuntimeError("Database pool is not connected")

    safe_limit = max(1, min(int(limit), 1000))
    async with db._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            with last_events as (
              select event_id, turn_id, role, text, coalesce(meta, '{}'::jsonb) as meta, created_at
              from events
              where session_id = $1
              order by event_id desc
              limit $2
            )
            select
              turn_id::text as turn_id,
              role,
              text,
              meta,
              (extract(epoch from created_at) * 1000)::bigint as ts_ms
            from last_events
            order by event_id asc
            """,
            session_id,
            safe_limit,
        )

    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "turn_id": str(row["turn_id"]),
                "role": str(row["role"]),
                "text": str(row["text"]),
                "meta": dict(row["meta"]) if isinstance(row["meta"], dict) else {},
                "ts_ms": int(row["ts_ms"]),
            }
        )
    return out
