import psycopg2
import sys
import os

# --- ПОДКЛЮЧЕНИЕ CONFIG ---
try:
    import config
except ImportError:
    # Если запускаем из папки MarketWatcher
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config
# --------------------------

def init_market_db():
    print(f"🔧 [Init] Настройка таблиц MarketWatcher на {config.DB_HOST}...")
    
    try:
        conn = psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            database=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASS
        )
        conn.autocommit = True
        
        with conn.cursor() as cur:
            # 1. Таблица товаров (items_to_watch)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS items_to_watch (
                    id SERIAL PRIMARY KEY,
                    platform VARCHAR(10) NOT NULL,
                    sku VARCHAR(50) NOT NULL,
                    name VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    scan_limit INT DEFAULT 20,
                    parse_all BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_checked TIMESTAMP,
                    UNIQUE(platform, sku)
                );
            """)
            
            # 2. Таблица статистики цен и рейтинга (daily_stats)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER REFERENCES items_to_watch(id) ON DELETE CASCADE,
                    price DECIMAL(10, 2),
                    rating_val DECIMAL(3, 2),
                    reviews_count INTEGER,
                    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 3. Таблица отзывов (reviews)
            # ВАЖНО: добавил ai_summary и ai_category, которые были в твоем коде
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER REFERENCES items_to_watch(id) ON DELETE CASCADE,
                    external_review_id VARCHAR(100),
                    text_content TEXT,
                    rating INT,
                    author_name VARCHAR(100),
                    created_date TIMESTAMP,
                    ai_summary TEXT,
                    ai_category VARCHAR(50),
                    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(item_id, external_review_id)
                );
            """)
            
        print("✅ Таблицы MarketWatcher успешно инициализированы.")
        conn.close()

    except Exception as e:
        print(f"❌ Ошибка при инициализации БД: {e}")

if __name__ == "__main__":
    init_market_db()