from uuid import uuid4

from ..utils.db import Database


async def create_intent(
    db: Database,
    *,
    session_id: str,
    intent_type: str,
) -> str:
    intent_id = str(uuid4())

    await db.execute(
        """
        insert into intents (
            intent_id,
            session_id,
            intent_type,
            status
        )
        values ($1, $2, $3, 'RUNNING')
        """,
        intent_id,
        session_id,
        intent_type,
    )

    return intent_id


async def finish_intent(
    db: Database,
    *,
    intent_id: str,
):
    await db.execute(
        """
        update intents
        set status = 'DONE'
        where intent_id = $1
        """,
        intent_id,
    )
