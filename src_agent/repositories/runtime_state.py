from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from src_agent.utils.db import Database
from src_shared.contracts import WorkflowRuntimeState


def _jsonb(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True)


def _decode_jsonb(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


async def load_runtime_state(db: Database, *, session_id: UUID) -> WorkflowRuntimeState:
    row = await db.fetchrow(
        """
        select version, active_workflow_id, pending, context
        from runtime_state
        where session_id = $1
        """,
        session_id,
    )
    if row is None:
        await db.execute(
            """
            insert into runtime_state (session_id, version, active_workflow_id, pending, context)
            values ($1, 1, null, null, null)
            on conflict (session_id) do nothing
            """,
            session_id,
        )
        return WorkflowRuntimeState(version=1)

    return WorkflowRuntimeState(
        version=int(row["version"]),
        active_workflow_id=row["active_workflow_id"],
        pending=_decode_jsonb(row["pending"]),
        context=_decode_jsonb(row["context"]),
    )


async def save_runtime_state(
    db: Database,
    *,
    session_id: UUID,
    expected_version: int,
    next_state: WorkflowRuntimeState,
) -> int:
    new_version = await db.fetchval(
        """
        update runtime_state
        set version = version + 1,
            active_workflow_id = $3,
            pending = $4::jsonb,
            context = $5::jsonb,
            updated_at = now()
        where session_id = $1
          and version = $2
        returning version
        """,
        session_id,
        expected_version,
        next_state.active_workflow_id,
        _jsonb(next_state.pending),
        _jsonb(next_state.context),
    )
    if new_version is None:
        raise RuntimeError("runtime_state version conflict")
    return int(new_version)
