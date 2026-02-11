import requests
import json
import os
import sys
import psycopg2
from datetime import datetime

# Подтягиваем пути и модули
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_market import MarketDB
from market_ai import analyze_review

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "ozon_api_config.json")

class OzonApiParser:
    def __init__(self):
        self.db = MarketDB()
        self.client_id, self.api_key = self.load_config()

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            print(f"❌ Конфиг {CONFIG_FILE} не найден!")
            return None, None
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
        return data.get("client_id"), data.get("api_key")

    def get_reviews(self):
        if not self.client_id or not self.api_key:
            return
        
        url = "https://api-seller.ozon.ru/v1/review/list"
        headers = {
            "Client-Id": str(self.client_id),
            "Api-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Получаем отзывы за все время (сортировка по дате)
        payload = {
            "page": 1,
            "limit": 100, # Максимум за раз
            "sort_dir": "DESC" 
        }

        print("⚡ Запрос к Ozon API...")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                print(f"❌ Ошибка API: {response.status_code} {response.text}")
                return

            data = response.json()
            reviews = data.get('result', [])
            print(f"✅ Получено {len(reviews)} отзывов через API")

            new_cnt = 0
            
            # Предварительно находим/создаем "виртуальный товар" для Ozon API отзывов
            # Так как API отдает отзывы на ВСЕ товары селлера, привяжем их к SKU
            
            for r in reviews:
                sku = str(r.get('sku', 'Unknown'))
                product_name = "Ozon Product " + sku # API не всегда отдает имя сразу
                
                # Добавляем товар в базу, если его нет
                item_id = self.db.add_item_to_watch("OZON_API", sku, product_name, item_type='SELF')
                
                # Данные отзыва
                r_id = str(r.get('id')) # ID отзыва на Ozon
                text_comment = r.get('comment', {}).get('comment', '')
                text_pros = r.get('comment', {}).get('pros', '')
                text_cons = r.get('comment', {}).get('cons', '')
                
                # Собираем полный текст
                full_text = f"{text_comment} {text_pros} {text_cons}".strip()
                if not full_text: full_text = "Без текста"
                
                rating = r.get('rating', 0)
                author = "Ozon Client" # API обезличивает данные покупателей
                created_at = r.get('published_at') # '2023-10-10T...'

                # Проверяем наличие в базе
                cur = self.db.get_cursor()
                cur.execute("SELECT id FROM reviews WHERE review_id_platform=%s", (r_id,))
                
                if not cur.fetchone():
                    # Анализируем AI (только если есть текст)
                    cat, sent, smry = "NONE", "NEUTRAL", ""
                    if len(full_text) > 5:
                        cat, sent, smry = analyze_review(full_text)
                    
                    # Сохраняем
                    saved = self.db.save_review(item_id, r_id, full_text, rating, author, created_at)
                    if saved:
                        cur.execute("""
                            UPDATE reviews SET ai_category=%s, ai_sentiment=%s, ai_summary=%s 
                            WHERE review_id_platform=%s
                        """, (cat, sent, smry, r_id))
                        new_cnt += 1
                        print(f"   🔹 [{cat}] {smry}")

            print(f"💾 Успешно сохранено {new_cnt} новых отзывов.")

        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    api = OzonApiParser()
    api.get_reviews()