# from uuid import uuid4
# from src_agent.utils.db import Database
#
#
# async def create_session(db: Database, user_id: str) -> str:
#     session_id = str(uuid4())
#
#     await db.execute(
#         """
#         insert into sessions (session_id, user_id, status)
#         values ($1, $2, 'RUNNING')
#         """,
#         session_id,
#         user_id,
#     )
#
#     return session_id
#
#
# async def update_session_status(
#         db: Database, session_id: str, status: str
# ):
#     await db.execute(
#         """
#         update sessions
#         set status     = $2,
#             updated_at = now()
#         where session_id = $1
#         """,
#         session_id,
#         status,
#     )
