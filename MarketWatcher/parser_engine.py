import asyncio
import os
import random
import sys
import json
import re
import argparse
import traceback
from datetime import datetime

# === 1. НАСТРОЙКА ПУТЕЙ (Чтобы видеть db_async в корне) ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # /app/MarketWatcher
ROOT_DIR = os.path.dirname(BASE_DIR)                  # /app
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

print(f"📍 МАРКЕР ПРОВЕРКИ: Скрипт запущен из: {BASE_DIR}")
print(f"📂 Корневая директория проекта: {ROOT_DIR}")

import config

# === 2. ИМПОРТЫ ЗАВИСИМОСТЕЙ ===
try:
    # Пытаемся импортировать класс AsyncDatabase из db_async.py
    from db_async import AsyncDatabase
    from market_ai import analyze_review
    print("✅ DB Module: Успешно импортирован.")
except ImportError as e:
    print(f"⚠️ Warning: Ошибка импорта модулей БД/AI: {e}")
    print(f"   Убедитесь, что файлы db_async.py и market_ai.py лежат в {ROOT_DIR}")
    AsyncDatabase = None
    analyze_review = lambda x: ("MIMO", 0.0, "No AI")

from playwright.async_api import async_playwright

# === 3. ВСТРОЕННАЯ МАСКИРОВКА (Вместо глючного playwright-stealth) ===
async def apply_stealth(page):
    """
    Внедряет JS-скрипты для скрытия факта автоматизации.
    Работает надежнее, чем внешняя библиотека.
    """
    await page.add_init_script("""
        // 1. Подменяем свойство webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        // 2. Эмулируем chrome
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };

        // 3. Подменяем плагины
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });

        // 4. Подменяем языки
        Object.defineProperty(navigator, 'languages', {
            get: () => ['ru-RU', 'ru', 'en-US', 'en']
        });
        
        // 5. Маскируем разрешения
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
        );
    """)

PID_FILE = os.path.join(BASE_DIR, "market.pid")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

def get_random_ua():
    return random.choice(USER_AGENTS)

class MarketParser:
    def __init__(self):
        # Инициализируем правильный класс
        self.db = AsyncDatabase() if AsyncDatabase else None

    async def _load_cookies(self, context, platform):
        """Загрузка куков из корня проекта"""
        cookie_file = "wb_cookies.json" if platform == "WB" else "ozon_cookies.json"
        cookie_path = os.path.join(ROOT_DIR, cookie_file)

        if os.path.exists(cookie_path):
            try:
                with open(cookie_path, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                    clean_cookies = []
                    for c in cookies:
                        clean_c = {
                            "name": c.get("name"),
                            "value": c.get("value"),
                            "domain": c.get("domain"),
                            "path": c.get("path", "/"),
                            "secure": c.get("secure", True)
                        }
                        # Исправление SameSite для Playwright
                        if "sameSite" in c and c["sameSite"] in ["Strict", "Lax", "None"]:
                            clean_c["sameSite"] = c["sameSite"]
                        else:
                            clean_c["sameSite"] = "Lax"
                        clean_cookies.append(clean_c)
                    
                    await context.add_cookies(clean_cookies)
                print(f"   🍪 Куки загружены ({len(clean_cookies)} шт) из {cookie_file}")
            except Exception as e:
                print(f"   ⚠️ Ошибка чтения куков: {e}")
        else:
            print(f"   ⚠️ Файл куков не найден: {cookie_path}")

    def _get_basket_host(self, vol: int) -> str:
        if 0 <= vol <= 143: return "basket-01.wbbasket.ru"
        if 144 <= vol <= 287: return "basket-02.wbbasket.ru"
        if 288 <= vol <= 431: return "basket-03.wbbasket.ru"
        if 432 <= vol <= 719: return "basket-04.wbbasket.ru"
        if 720 <= vol <= 1007: return "basket-05.wbbasket.ru"
        if 1008 <= vol <= 1061: return "basket-06.wbbasket.ru"
        if 1062 <= vol <= 1115: return "basket-07.wbbasket.ru"
        if 1116 <= vol <= 1169: return "basket-08.wbbasket.ru"
        if 1170 <= vol <= 1313: return "basket-09.wbbasket.ru"
        if 1314 <= vol <= 1601: return "basket-10.wbbasket.ru"
        if 1602 <= vol <= 1655: return "basket-11.wbbasket.ru"
        if 1656 <= vol <= 1919: return "basket-12.wbbasket.ru"
        if 1920 <= vol <= 2045: return "basket-13.wbbasket.ru"
        if 2046 <= vol <= 2189: return "basket-14.wbbasket.ru"
        if 2190 <= vol <= 2405: return "basket-15.wbbasket.ru"
        if 2406 <= vol <= 2621: return "basket-16.wbbasket.ru"
        if 2622 <= vol <= 2837: return "basket-17.wbbasket.ru"
        return "basket-18.wbbasket.ru" 

    async def _fetch_card_data_api(self, sku, request_context):
        try:
            _sku = int(sku)
            vol = _sku // 100000
            part = _sku // 1000
            host = self._get_basket_host(vol)
            
            headers = {
                "User-Agent": get_random_ua(),
                "Accept": "*/*",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }

            url = f"https://{host}/vol{vol}/part{part}/{sku}/info/ru/card.json"
            response = await request_context.get(url, headers=headers)
            if response.status == 200:
                j = await response.json()
                price_u = j.get('salePriceU') or j.get('priceU')
                price_rub = int(price_u / 100) if price_u else 0
                return {'found': True, 'price': price_rub, 'name': j.get('imt_name', 'WB Item'), 'root_id': j.get('imt_id'), 'rating': j.get('reviewRating', 0)}
            return {'found': False}
        except: return {'found': False}

    async def _fetch_from_html_fallback(self, page, sku, url):
        print(f"   ⚓ Включаем Stealth HTML-парсинг (Native JS)...")
        try:
            # ПРИМЕНЯЕМ ВСТРОЕННЫЙ STEALTH
            await apply_stealth(page)
            
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            
            try:
                await page.wait_for_selector('.price-block__final-price, .product-page__price', timeout=10000)
            except: pass 

            price = 0
            price_selectors = [
                'ins.price-block__final-price', 
                '.price-block__final-price', 
                '.price-block__wallet-price',
                '.product-page__price-currency',
                'span[class*="price-block"]'
            ]
            
            for sel in price_selectors:
                try:
                    element = page.locator(sel).first
                    if await element.is_visible():
                        text = await element.inner_text()
                        clean = re.sub(r'[^\d]', '', text)
                        if clean and int(clean) > 0:
                            price = int(clean)
                            print(f"   💰 Цена найдена ({sel}): {price}")
                            break
                except: continue

            if price == 0:
                print("   📸 Цена не найдена. Скриншот: debug_fail.png")
                await page.screenshot(path=os.path.join(BASE_DIR, "debug_fail.png"), full_page=True)

            return {'found': True, 'price': price, 'rating': 0.0, 'name': 'WB Item'}
        except Exception as e:
            print(f"   ❌ Ошибка HTML: {e}")
            traceback.print_exc()
            return {'found': False}

    # === РАБОТА С БД (ОБЕРТКИ) ===
    async def add_item_to_watch(self, platform, sku, name):
        if not self.db: return None
        try:
            await self.db.execute("""
                INSERT INTO items_to_watch (platform, sku, name, last_checked) 
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (platform, sku) DO NOTHING
            """, platform, str(sku), name)
            
            row = await self.db.fetchrow("SELECT id FROM items_to_watch WHERE platform=$1 AND sku=$2", platform, str(sku))
            return row['id'] if row else None
        except Exception as e:
            print(f"DB Error: {e}")
            return None

    async def save_daily_stats(self, item_id, price, rating, reviews_count):
        if not self.db: return
        try:
            await self.db.execute("""
                INSERT INTO daily_stats (item_id, price, rating_val, reviews_count)
                VALUES ($1, $2, $3, $4)
            """, item_id, price, rating, reviews_count)
        except Exception as e:
            print(f"Stats Error: {e}")

    async def parse_item(self, platform, sku, url, scan_limit=20, parse_all=False):
        print(f"\n🔎 [{platform}] Парсинг SKU: {sku}...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = await browser.new_context(user_agent=get_random_ua(), viewport={'width': 1920, 'height': 1080})
            
            await self._load_cookies(ctx, platform)
            
            page = await ctx.new_page()
            
            if platform == "WB":
                # 1. Сначала пробуем быстрое API
                data = await self._fetch_card_data_api(sku, ctx.request)
                
                # 2. Если API подвело или цена 0, включаем HTML парсинг
                if not data.get('found') or data.get('price') == 0:
                     html_data = await self._fetch_from_html_fallback(page, sku, url)
                     if html_data['found'] and html_data.get('price') > 0:
                         data.update(html_data)

                if data.get('found'):
                    print(f"   ✅ НАЙДЕНО: {data.get('name')} | {data.get('price')} ₽")
                    if self.db:
                        item_id = await self.add_item_to_watch(platform, sku, data.get('name'))
                        if item_id:
                            await self.save_daily_stats(item_id, data.get('price'), data.get('rating', 0), 0)
                    else:
                        print("   ⚠️ Данные не сохранены (нет подключения к БД)")
                else:
                    print("   ❌ Не удалось распарсить товар.")

            await browser.close()

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def extract_sku(input_str):
    match = re.search(r'catalog/(\d+)', input_str)
    if match: return match.group(1)
    if input_str.isdigit(): return input_str
    return input_str

async def main():
    print("--- 🚀 MARKET WATCHER V2.4 (Stealth Native) ---")
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=str)
    parser.add_argument('--market', type=str)
    args, _ = parser.parse_known_args()

    with open(PID_FILE, 'w') as f: f.write(str(os.getpid()))
    
    market_parser = MarketParser()
    
    # Попытка подключения к БД
    if market_parser.db: 
        try:
            await market_parser.db.connect()
        except Exception as e:
            print(f"❌ Ошибка соединения с БД: {e}")
    
    try:
        if args.target:
            sku = extract_sku(args.target)
            url = args.target if "http" in args.target else f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            await market_parser.parse_item("WB", sku, url)
    finally:
        if market_parser.db: await market_parser.db.close()
        if os.path.exists(PID_FILE): os.remove(PID_FILE)

if __name__ == "__main__":
    asyncio.run(main())