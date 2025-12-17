import json
from uuid import uuid4
from typing import Optional
from ..utils.db import Database


async def get_artifact(
    db: Database,
    *,
    session_id: str,
    name: str,
) -> Optional[dict]:
    row = await db.fetchrow(
        """
        select data
        from artifacts
        where session_id = $1
          and name = $2
        order by created_at desc
        limit 1
        """,
        session_id,
        name,
    )
    return dict(row["data"]) if row else None


async def save_artifact(
    db: Database,
    *,
    session_id: str,
    intent_id: Optional[str],
    type: str,
    name: str,
    data: dict,
):
    await db.execute(
        """
        insert into artifacts (
            artifact_id,
            session_id,
            intent_id,
            type,
            name,
            data
        )
        values ($1,$2,$3,$4,$5,$6)
        """,
        str(uuid4()),
        session_id,
        intent_id,
        type,
        name,
        json.dumps(data, ensure_ascii=False)
    )
