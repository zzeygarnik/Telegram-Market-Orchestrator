import psycopg2

DB_HOST = "192.168.31.250"
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASS = "postgres"

def fix_ratings():
    print("🚑 Начинаю лечение рейтингов...")
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
        conn.autocommit = True
        cur = conn.cursor()
        
        # Магический SQL запрос:
        # 1. Считает среднее (AVG) по всем отзывам для каждого товара.
        # 2. Обновляет таблицу daily_stats полученным числом.
        
        cur.execute("""
            UPDATE daily_stats ds
            SET rating_val = sub.avg_rating
            FROM (
                SELECT item_id, AVG(rating) as avg_rating
                FROM reviews
                WHERE rating > 0
                GROUP BY item_id
            ) sub
            WHERE ds.item_id = sub.item_id;
        """)
        
        print(f"✅ Обновлено записей статистики: {cur.rowcount}")
        conn.close()
        print("✨ База здорова! Обновите страницу Дашборда.")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    fix_ratings()