import asyncpg
import os
from typing import Any, Dict, Optional
from uuid import UUID




class Database:
    def __init__(self, db_url):
        self._pool: Optional[asyncpg.Pool] = None
        self._db_url = db_url

    async def connect(self):
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._db_url,
                min_size=1,
                max_size=10,
            )

    async def close(self):
        if self._pool:
            await self._pool.close()

    async def fetchval(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)
