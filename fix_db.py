import psycopg2
import config

def fix_database_structure():
    print("🛠 Начинаю проверку и ремонт структуры БД...")
    
    try:
        conn = psycopg2.connect(
            host=config.DB_HOST, port=config.DB_PORT, 
            database=config.DB_NAME, user=config.DB_USER, password=config.DB_PASS
        )
        conn.autocommit = True
        cur = conn.cursor()

        # ==========================================
        # 1. ТАБЛИЦА ЧАТОВ (monitored_chats)
        # ==========================================
        print("\n--- [1/3] Проверка таблицы monitored_chats ---")
        
        # Список колонок, которые ОБЯЗАНЫ быть
        required_columns = {
            "id": "SERIAL",  # Добавим как простое поле, если его нет
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "status_msg": "TEXT DEFAULT 'Waiting'",
            "is_active": "BOOLEAN DEFAULT TRUE",
            "depth": "INTEGER DEFAULT 100",
            "last_scan_id": "BIGINT DEFAULT 0",
            "chat_title": "TEXT"
        }

        for col, dtype in required_columns.items():
            cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='monitored_chats' AND column_name='{col}'")
            if not cur.fetchone():
                print(f"   ⚠️ Нет колонки '{col}'. Добавляю...")
                try:
                    cur.execute(f"ALTER TABLE monitored_chats ADD COLUMN {col} {dtype};")
                    print(f"   ✅ Колонка '{col}' добавлена.")
                except Exception as e:
                    print(f"   ❌ Ошибка добавления {col}: {e}")
            else:
                print(f"   🆗 Колонка '{col}' на месте.")

        # ==========================================
        # 2. ТАБЛИЦА ЛИДОВ (leads)
        # ==========================================
        print("\n--- [2/3] Проверка таблицы leads ---")
        # Тут обычно всё ок, но проверим updated_at
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='leads' AND column_name='updated_at'")
        if not cur.fetchone():
             cur.execute("ALTER TABLE leads ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
             print("   ✅ Добавлена колонка updated_at в leads")

        # ==========================================
        # 3. ТАБЛИЦА МАРКЕТА (market_items)
        # ==========================================
        print("\n--- [3/3] Проверка таблицы market_items ---")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS market_items (
                id SERIAL PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                name TEXT,
                target_price INTEGER DEFAULT 0,
                last_price INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("   ✅ Таблица market_items проверена/создана.")

        conn.close()
        print("\n🎉 ГОТОВО! База данных полностью обновлена под новый код.")

    except Exception as e:
        print(f"\n❌ Критическая ошибка подключения или прав: {e}")

if __name__ == "__main__":
    fix_database_structure()