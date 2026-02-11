import asyncpg
import config

class AsyncDatabase:
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Создает пул соединений с PostgreSQL"""
        try:
            self.pool = await asyncpg.create_pool(
                user=config.DB_USER,
                password=config.DB_PASS,
                database=config.DB_NAME,
                host=config.DB_HOST,
                port=config.DB_PORT,
                min_size=1,
                max_size=10
            )
            return True
        except Exception as e:
            print(f"❌ DB Connection Error: {e}")
            return False

    async def fetch(self, query, *args):
        """Выполняет запрос и возвращает все строки"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query, *args):
        """Выполняет запрос и возвращает одну строку"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def execute(self, query, *args):
        """Выполняет команду (INSERT, UPDATE, DELETE)"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def close(self):
        """Закрывает пул соединений"""
        if self.pool:
            await self.pool.close()