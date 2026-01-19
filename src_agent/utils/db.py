from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
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


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


DB_STORE: Dict[str, list] = {
    "conversations": [],
}


def get_conversation(session_id: str) -> Optional[Dict[str, Any]]:
    for conv in DB_STORE["conversations"]:
        if conv.get("session_id") == session_id:
            return conv
    return None


def init_conversation(session_id: str) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "turns": [],
        "messages": [],
        "scenario": {"id": None, "status": "RUNNING", "pending": None},
        "scenario_log": [],
        "artifacts": [],
        "updated_at": _now_iso(),
    }


def save_conversation(state: Dict[str, Any]) -> None:
    existing = get_conversation(state["session_id"])
    state["updated_at"] = _now_iso()
    if existing is not None:
        existing.clear()
        existing.update(state)
        return
    DB_STORE["conversations"].append(state)


def add_turn(state: Dict[str, Any], *, role: str, text: str, turn_id: Optional[str] = None) -> str:
    tid = turn_id or str(uuid4())
    state["turns"].append({
        "turn_id": tid,
        "role": role,
        "text": text,
        "ts": _now_iso(),
    })
    return tid


def truncate_conversation_after_turn(state: Dict[str, Any], turn_id: str) -> bool:
    turns = state.get("turns") or []
    idx = next((i for i, t in enumerate(turns) if t.get("turn_id") == turn_id), None)
    if idx is None:
        return False

    kept_turns = turns[:idx + 1]
    kept_ids = {t.get("turn_id") for t in kept_turns}

    state["turns"] = kept_turns
    state["messages"] = []
    state["artifacts"] = [a for a in state.get("artifacts", []) if a.get("turn_id") in kept_ids]
    state["scenario_log"] = [
        e for e in state.get("scenario_log", [])
        if e.get("turn_id") in kept_ids or e.get("turn_id") is None
    ]
    if isinstance(state.get("scenario"), dict):
        state["scenario"]["pending"] = None
        state["scenario"]["status"] = "RUNNING"
    return True
