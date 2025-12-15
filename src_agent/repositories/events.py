import json

from src_agent.utils.db import Database
from typing import Optional, Dict, Any

async def next_event_seq(db: Database, session_id: str) -> int:
    seq = await db.fetchval(
        """
        select coalesce(max(seq), 0) + 1
        from events
        where session_id = $1
        """,
        session_id,
    )
    return seq


async def log_event(
    db: Database,
    *,
    session_id: str,
    intent_id: Optional[str],
    role: str,
    event_type: str,
    name: Optional[str],
    input: Optional[Dict[str, Any]],
    output: Optional[Dict[str, Any]],
):
    seq = await next_event_seq(db, session_id)

    input_json = json.dumps(input) if input is not None else None
    output_json = json.dumps(output) if output is not None else None
    print("DEBUG log_event args:")
    print("name:", name, type(name))
    print("input:", input, type(input))
    print("output:", output, type(output))

    await db.execute(
        """
        insert into events (session_id, intent_id, seq,
                            role, event_type, name,
                            input, output)
        values ($1, $2, $3,
                $4, $5, $6,
                $7::jsonb, $8::jsonb)
        """,
        session_id,
        intent_id,
        seq,
        role,
        event_type,
        name,
        input_json,
        output_json,
    )


