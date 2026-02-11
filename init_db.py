import asyncio
import asyncpg
import config

async def init_db():
    print(f"🚀 Подключаюсь к {config.DB_HOST} для создания таблиц...")
    try:
        conn = await asyncpg.connect(
            user=config.DB_USER,
            password=config.DB_PASS,
            database=config.DB_NAME,
            host=config.DB_HOST,
            port=config.DB_PORT
        )
        
        # SQL запросы для создания всех необходимых таблиц
        queries = [
            """
            CREATE TABLE IF NOT EXISTS monitored_chats (
                id SERIAL PRIMARY KEY,
                chat_link TEXT UNIQUE NOT NULL,
                chat_title TEXT,
                last_scan_id INTEGER DEFAULT 0,
                depth INTEGER DEFAULT 100,
                is_active BOOLEAN DEFAULT TRUE,
                status_msg TEXT,
                progress INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS leads (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                bio TEXT,
                is_premium BOOLEAN,
                role TEXT,
                intent TEXT,
                source_chat TEXT,
                last_message TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS posted_messages (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                msg_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        ]

        for q in queries:
            await conn.execute(q)
            
        # Добавим тестовый чат, чтобы боту было что сканировать (твой канал)
        await conn.execute("""
            INSERT INTO monitored_chats (chat_link, chat_title) 
            VALUES ('-1001691898040', 'ГОСТ 22.0.08-96')
            ON CONFLICT (chat_link) DO NOTHING;
        """)

        print("✅ Все таблицы созданы, тестовый чат добавлен!")
        await conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка инициализации: {e}")

if __name__ == "__main__":
    asyncio.run(init_db())