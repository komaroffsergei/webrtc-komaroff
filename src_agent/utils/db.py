from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Dict
from uuid import uuid4

import asyncpg

logger = logging.getLogger("src_agent.db")


@dataclass
class Database:
    """
    Минимальная обёртка над пулом asyncpg.

    В `src_agent` Postgres используется для:
    - таблицы sessions (создание/обновление статуса сессии)
    - таблиц intents/events (аудит сообщений, LLM-запросов и действий сценариев)
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
    return json.dumps(value, ensure_ascii=False)


# ----------------------------
# sessions
# ----------------------------

async def create_session(db: Database, *, user_id: str, session_id: Optional[str] = None) -> str:
    sid = session_id or str(uuid4())
    # Внешние сервисы могут присылать выбранный session_id — делаем upsert,
    # чтобы последующие записи в events не падали на FK.
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
    # События пишем “best effort”:
    # - если не удалось upsert'нуть trace в intents (например, в БД другая схема),
    #   всё равно пытаемся записать event, приклеив request_id внутрь JSONB.
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

def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


DB_STORE: Dict[str, list] = {
    "conversations": [],
}

# Conversation state хранится в памяти процесса (для локального dev):
# turns/pending/scenario_artifacts/scenario_log.
# Это отдельно от Postgres: Postgres нужен для аудита и статусов sessions.

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
        "scenario": {"id": None, "status": "RUNNING", "input": None},
        "pending": None,
        "scenario_log": [],
        "scenario_artifacts": {},
        "updated_at": _now_iso(),
    }


def save_conversation(state: Dict[str, Any]) -> None:
    existing = get_conversation(state["session_id"])
    state["updated_at"] = _now_iso()
    if existing is not None:
        if existing is state:
            return
        existing.clear()
        existing.update(state)
        return
    DB_STORE["conversations"].append(state)


def add_turn(state: Dict[str, Any], *, role: str, text: str, turn_id: Optional[str] = None) -> str:
    tid = turn_id or str(uuid4())
    turns = state.get("turns")
    if not isinstance(turns, list):
        turns = []
        state["turns"] = turns
    turns.append({
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
    state["scenario_log"] = [
        e for e in state.get("scenario_log", [])
        if e.get("turn_id") in kept_ids or e.get("turn_id") is None
    ]
    if isinstance(state.get("scenario"), dict):
        state["scenario"]["status"] = "RUNNING"
        state["scenario"]["input"] = None
    state["pending"] = None
    state["scenario_artifacts"] = {}
    return True
