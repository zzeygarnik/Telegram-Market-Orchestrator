import asyncio
import os
import random
import sys
import json
import re
import argparse
import traceback
from datetime import datetime

# === ДИАГНОСТИКА ПУТЕЙ ===
print(f"📍 МАРКЕР ПРОВЕРКИ: Скрипт запущен из: {os.path.abspath(__file__)}")
print(f"🐍 Python исполняемый файл: {sys.executable}")

# Настраиваем пути для импорта локальных модулей
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.append(ROOT_DIR)

import config

# === ИМПОРТЫ ЗАВИСИМОСТЕЙ ===
try:
    from db_async import AsyncMarketDB
    from market_ai import analyze_review
except ImportError:
    print("⚠️ Warning: db_async or market_ai not found. Running in limited mode.")
    AsyncMarketDB = None
    analyze_review = lambda x: ("MIMO", 0.0, "No AI")

from playwright.async_api import async_playwright

# === УНИВЕРСАЛЬНЫЙ ИМПОРТ STEALTH ===
stealth_async = None
try:
    # Вариант 1: Стандартный для новых версий
    from playwright_stealth import stealth_async
    print("✅ СИСТЕМА: stealth_async найден напрямую.")
except ImportError:
    try:
        # Вариант 2: Если функция лежит внутри модуля stealth
        from playwright_stealth.stealth import stealth_async
        print("✅ СИСТЕМА: stealth_async найден в подмодуле .stealth")
    except ImportError:
        try:
            # Вариант 3: Пробуем импортировать как обычный stealth (он часто работает и там, и там)
            from playwright_stealth import stealth
            stealth_async = stealth
            print("✅ СИСТЕМА: Использован базовый stealth вместо async-версии")
        except ImportError:
            print("❌ КРИТИЧЕСКАЯ ОШИБКА: Ни один из методов импорта не сработал.")

if stealth_async:
    print("🚀 Stealth-маскировка готова к работе!")
else:
    import traceback
    traceback.print_exc()

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
        self.db = AsyncMarketDB() if AsyncMarketDB else None

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
        print(f"   ⚓ Включаем Stealth HTML-парсинг...")
        try:
            if stealth_async:
                await stealth_async(page)
            
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            
            # Ждем появления цены
            try:
                await page.wait_for_selector('.price-block__final-price, .product-page__price', timeout=10000)
            except: pass 

            price = 0
            # Актуальные селекторы
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
            return {'found': False}

    async def parse_item(self, platform, sku, url, scan_limit=20, parse_all=False):
        print(f"\n🔎 [{platform}] Парсинг SKU: {sku}...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = await browser.new_context(user_agent=get_random_ua(), viewport={'width': 1920, 'height': 1080})
            
            # ЗАГРУЗКА КУКОВ
            await self._load_cookies(ctx, platform)
            
            page = await ctx.new_page()
            
            if platform == "WB":
                # 1. API
                data = await self._fetch_card_data_api(sku, ctx.request)
                
                # 2. HTML Fallback
                if not data.get('found') or data.get('price') == 0:
                     html_data = await self._fetch_from_html_fallback(page, sku, url)
                     if html_data['found']:
                         data.update(html_data)

                if data.get('found'):
                    print(f"   ✅ НАЙДЕНО: {data.get('name')} | {data.get('price')} ₽")
                    if self.db:
                        item_id = await self.db.add_item_to_watch(platform, sku, data.get('name'))
                        if item_id:
                            await self.db.save_daily_stats(item_id, data.get('price'), data.get('rating', 0), 0)
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
    print("--- 🚀 MARKET WATCHER V2.4 (Stealth Docker) ---")
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=str)
    parser.add_argument('--market', type=str)
    args, _ = parser.parse_known_args()

    with open(PID_FILE, 'w') as f: f.write(str(os.getpid()))
    
    market_parser = MarketParser()
    if market_parser.db: await market_parser.db.connect()
    
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