import asyncio
import os
import random
import sys
import json
import re
import argparse # Добавили для работы с аргументами
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ===================================

import config

# Импорты
try:
    from db_async import AsyncMarketDB
    from market_ai import analyze_review
except ImportError:
    # Заглушки, если файлы не найдены (чтобы скрипт не падал сразу)
    print("⚠️ Warning: db_async or market_ai not found. Running in limited mode.")
    AsyncMarketDB = None
    analyze_review = lambda x: ("MIMO", 0.0, "No AI")

from playwright.async_api import async_playwright

# Импортируем маскировку
try:
    from playwright_stealth import stealth_async
except ImportError:
    print("⚠️ ОШИБКА: Не установлен playwright-stealth. Добавьте его в requirements.txt")
    stealth_async = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BASE_DIR, "market.pid")

# Расширенный список User-Agents
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
        """Попытка №1: API (Smart Fallback)"""
        try:
            _sku = int(sku)
            vol = _sku // 100000
            part = _sku // 1000
            
            predicted_host = self._get_basket_host(vol)
            hosts_to_try = [predicted_host]
            all_baskets = [f"basket-{i:02d}.wbbasket.ru" for i in range(1, 36)]
            if predicted_host in all_baskets: all_baskets.remove(predicted_host)
            queue = hosts_to_try + all_baskets
            
            headers = {
                "User-Agent": get_random_ua(),
                "Accept": "*/*",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }

            for host in queue:
                url = f"https://{host}/vol{vol}/part{part}/{sku}/info/ru/card.json"
                try:
                    response = await request_context.get(url, headers=headers)
                    if response.status == 200:
                        j = await response.json()
                        price_u = j.get('salePriceU') or j.get('priceU')
                        if not price_u:
                            ext = j.get('extended', {})
                            price_u = ext.get('basicPriceU') or ext.get('basicSalePriceU')

                        price_rub = int(price_u / 100) if price_u else 0
                        name = j.get('imt_name') or j.get('subj_name', 'Unknown')
                        root_id = j.get('imt_id')
                        rating = j.get('reviewRating', 0)
                        
                        return {'found': True, 'source': 'API', 'price': price_rub, 'name': name, 'root_id': root_id, 'rating': rating}
                    if response.status == 404: continue
                except: continue
            return {'found': False, 'source': 'API'}
        except: return {'found': False, 'source': 'API'}

    async def _fetch_from_html_fallback(self, page, sku, url):
        """Попытка №2: Stealth Browser"""
        print(f"   ⚓ Включаем Stealth HTML-парсинг...")
        try:
            if stealth_async:
                await stealth_async(page)
            
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            
            try:
                await page.wait_for_selector('.price-block__final-price, .mo-typography_color_danger', timeout=5000)
            except: pass 

            price = 0
            price_selectors = [
                '.mo-typography_variant_title2.mo-typography_color_danger', 
                '.price-block__final-price', 
                '.price-block__wallet-price',
                'div[class*="price-block"] span'
            ]
            
            for sel in price_selectors:
                try:
                    elements = await page.locator(sel).all()
                    for el in elements:
                        if await el.is_visible():
                            text = await el.inner_text()
                            clean = re.sub(r'[^\d]', '', text)
                            if clean:
                                price = int(clean)
                                print(f"   💰 Цена найдена (HTML): {price}")
                                break
                    if price > 0: break
                except: pass

            if price == 0:
                print("   📸 Цена не найдена. Делаю скриншот (debug_fail.png)...")
                await page.screenshot(path=os.path.join(BASE_DIR, "debug_fail.png"))

            rating = 0.0
            rating_selectors = ['.product-review__rating', '.address-rate-mini', '.user-scores__score']
            for sel in rating_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible():
                        text = await el.inner_text()
                        rating = float(text.replace(',', '.').strip())
                        break
                except: pass
            
            name = "WB Item"
            try: name = await page.locator('h1').inner_text()
            except: pass

            return {'found': True, 'source': 'HTML', 'price': price, 'rating': rating, 'name': name, 'root_id': 0}

        except Exception as e:
            print(f"   ❌ Ошибка HTML парсинга: {e}")
            return {'found': False, 'source': 'HTML'}

    async def _download_reviews(self, root_id, scan_limit, request_context):
        if not root_id: return []
        print(f"   📥 Сбор отзывов (Root: {root_id})...")
        headers = {"User-Agent": get_random_ua()}
        unique_reviews = {}
        servers = ["feedbacks1", "feedbacks2"]
        sorts = ["dateDesc", "rateDesc"]
        for srv in servers:
            for sort in sorts:
                if len(unique_reviews) >= scan_limit: break
                try:
                    url = f"https://{srv}.wb.ru/feedbacks/v1/{root_id}?order={sort}"
                    r = await request_context.get(url, headers=headers)
                    if r.status == 200:
                        j = await r.json()
                        for fb in j.get('feedbacks', []):
                            if fb.get('id'): unique_reviews[fb['id']] = fb
                except: pass
        return list(unique_reviews.values())

    async def _process_and_save(self, item_id, reviews):
        text_reviews = [r for r in reviews if r.get('text') and len(r.get('text')) > 1]
        calc_rating = 0.0
        if reviews:
            total = sum(int(r.get('valuation', 0)) for r in reviews)
            calc_rating = round(total / len(reviews), 2)

        if not text_reviews: return 0, calc_rating

        print(f"   🧠 Анализ {len(text_reviews)} отзывов...")
        if not self.db: return 0, calc_rating
        
        existing_ids = await self.db.get_existing_reviews_ids(item_id)
        new_batch = []
        
        for fb in text_reviews:
            r_id = str(fb.get('id'))
            if r_id in existing_ids: continue 

            val = int(fb.get('valuation', 0))
            r_text = fb.get('text', '')
            r_author = fb.get('wbUserDetails', {}).get('name', 'WB User')
            
            raw_date = fb.get('createdDate')
            r_date_obj = datetime.now()
            if raw_date:
                try:
                    clean_date = raw_date.replace("Z", "").split(".")[0]
                    r_date_obj = datetime.fromisoformat(clean_date)
                except: pass

            cat, sent, smry = analyze_review(r_text)
            new_batch.append((item_id, r_id, r_text, val, r_author, r_date_obj, cat, sent, smry))

        if new_batch: await self.db.save_reviews_batch(new_batch)
        print(f"   💾 Сохранено новых: {len(new_batch)} шт.")
        
        return len(new_batch), calc_rating

    async def parse_item(self, platform, sku, url, scan_limit=20, parse_all=False):
        if parse_all: scan_limit = 5000
        else: scan_limit = int(scan_limit)

        print(f"\n🔎 [{platform}] Парсинг SKU: {sku}...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True, 
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
            )
            ctx = await browser.new_context(user_agent=get_random_ua(), viewport={'width': 1920, 'height': 1080}, locale='ru-RU')
            page = await ctx.new_page()
            
            if platform == "WB":
                # 1. API
                data = await self._fetch_card_data_api(sku, ctx.request)
                
                # 2. Fallback HTML
                if data['found'] and (data['price'] == 0 or data['rating'] == 0):
                     print("   ⚠️ API не отдал цену. Пробуем Stealth HTML...")
                     html_data = await self._fetch_from_html_fallback(page, sku, url)
                     if html_data['found']:
                         if data['price'] == 0: data['price'] = html_data['price']
                         if data['rating'] == 0: data['rating'] = html_data['rating']
                         if not data['name'] or data['name'] == 'Unknown': data['name'] = html_data['name']

                if not data['found']:
                    data = await self._fetch_from_html_fallback(page, sku, url)

                # Итог
                if data['found']:
                    print(f"   ✅ НАЙДЕНО: {data['name']} | {data['price']} ₽")
                    if self.db:
                        item_id = await self.db.add_item_to_watch(platform, sku, data['name'])
                        if item_id:
                            reviews_list = []
                            if data.get('root_id'):
                                reviews_list = await self._download_reviews(data['root_id'], scan_limit, ctx.request)
                            
                            saved_cnt, calc_rating = await self._process_and_save(item_id, reviews_list)
                            final_rating = data['rating'] if data['rating'] > 0 else calc_rating
                            
                            await self.db.save_daily_stats(item_id, data['price'], final_rating, saved_cnt)
                            print(f"   🏁 Сохранено в БД: Цена {data['price']} ₽, Рейтинг {final_rating}")
                else:
                    print("   ❌ Не удалось распарсить товар.")
            
            elif platform == "OZON":
                 print("   ℹ️ Логика для OZON пока не реализована в полной мере (нужен Stealth + API bypass).")
                 # ТУТ МОЖНО БУДЕТ ДОБАВИТЬ ЛОГИКУ ДЛЯ ОЗОНА ПОЗЖЕ

            await browser.close()

# === ФУНКЦИЯ ДЛЯ ИЗВЛЕЧЕНИЯ SKU ИЗ ССЫЛКИ ===
def extract_sku(input_str):
    # Пытаемся найти цифры, если это ссылка
    match = re.search(r'catalog/(\d+)', input_str) # Для WB
    if match: return match.group(1)
    
    match_oz = re.search(r'product/.*-(\d+)', input_str) # Для Ozon
    if match_oz: return match_oz.group(1)

    # Если просто цифры
    if input_str.isdigit(): return input_str
    
    return input_str # Возвращаем как есть, если не поняли

async def main():
    print("--- 🚀 MARKET WATCHER V2.4 (Stealth Docker) ---")
    
    # 1. ПАРСИНГ АРГУМЕНТОВ ОТ ДАШБОРДА
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=str, help='Ссылка на товар или SKU')
    parser.add_argument('--market', type=str, help='WB или OZON')
    args, unknown = parser.parse_known_args() # Чтобы не падал от лишних аргументов

    with open(PID_FILE, 'w') as f: f.write(str(os.getpid()))
    
    market_parser = MarketParser()
    if market_parser.db: await market_parser.db.connect()
    
    try:
        # РЕЖИМ 1: ЗАПУСК ИЗ ДАШБОРДА (ОДИН ТОВАР)
        if args.target:
            sku = extract_sku(args.target)
            platform = "WB"
            if args.market and "ozon" in args.market.lower(): platform = "OZON"
            elif "ozon" in args.target.lower(): platform = "OZON"
            
            url = args.target if "http" in args.target else f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            
            print(f"🎯 Режим одиночного сканирования: {platform} | SKU: {sku}")
            await market_parser.parse_item(platform, sku, url, scan_limit=50, parse_all=True)

        # РЕЖИМ 2: РАБОТА ПО РАСПИСАНИЮ (ИЗ БАЗЫ)
        else:
            if not market_parser.db:
                print("❌ Нет подключения к БД и нет цели для сканирования.")
                return

            items = await market_parser.db.get_active_items()
            if items:
                print(f"📋 Задач в базе: {len(items)}")
                for row in items:
                    try:
                        url = f"https://www.wildberries.ru/catalog/{row['sku']}/detail.aspx" if row['platform'] == "WB" else ""
                        if url:
                            await market_parser.parse_item(row['platform'], row['sku'], url, row.get('scan_limit', 20), row.get('parse_all', False))
                            await asyncio.sleep(3)
                    except Exception as e: print(f"Err: {e}")
            else:
                print("📭 База пуста.")

    finally:
        if market_parser.db: await market_parser.db.close()
        if os.path.exists(PID_FILE): os.remove(PID_FILE)

if __name__ == "__main__":
    if sys.platform == 'win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())