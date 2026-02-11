import asyncio
import asyncpg
import logging
import sys
import os

# --- ПОДКЛЮЧЕНИЕ CONFIG ---
# Добавляем путь к корню проекта, чтобы увидеть config.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config 
# --------------------------

class AsyncDatabase:
    def __init__(self):
        self.pool = None
        self.host = config.DB_HOST
        self.port = config.DB_PORT
        self.database = config.DB_NAME
        self.user = config.DB_USER
        self.password = config.DB_PASS

    async def connect(self):
        if not self.pool:
            try:
                self.pool = await asyncpg.create_pool(
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    host=self.host,
                    port=self.port,
                    min_size=1,
                    max_size=20 
                )
                logging.info("✅ [Async DB] Pool created successfully")
            except Exception as e:
                logging.error(f"❌ [Async DB] Connection failed: {e}")
                raise e

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logging.info("💤 [Async DB] Pool closed")

    async def execute(self, query, *args):
        if not self.pool: await self.connect()
        async with self.pool.acquire() as connection:
            return await connection.execute(query, *args)

    async def fetch(self, query, *args):
        if not self.pool: await self.connect()
        async with self.pool.acquire() as connection:
            return await connection.fetch(query, *args)

    async def fetchrow(self, query, *args):
        if not self.pool: await self.connect()
        async with self.pool.acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def fetchval(self, query, *args):
        if not self.pool: await self.connect()
        async with self.pool.acquire() as connection:
            return await connection.fetchval(query, *args)