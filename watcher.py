import asyncio
import os
import sys
import logging
import threading
import time
import json
import re
import traceback
from datetime import datetime
from collections import defaultdict

# === ГАРАНТИЯ ПУТЕЙ ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from pyrogram import Client, enums
from pyrogram.errors import UserAlreadyParticipant, FloodWait
from openai import OpenAI, BadRequestError
import aiofiles

# Локальные модули
try:
    import config
except ImportError:
    print("❌ ОШИБКА: Не найден файл config.py!")
    sys.exit(1)

from db_async import AsyncDatabase

# === НАСТРОЙКИ ===
sys.stdout.reconfigure(encoding='utf-8')
PID_FILE = os.path.join(BASE_DIR, "watcher.pid")
DEBUG_FILE = os.path.join(BASE_DIR, "debug_log.txt")

# Глобальная статистика
STATS = {"scanned": 0, "processed": 0}

# === АСИНХРОННОЕ ЛОГИРОВАНИЕ ===
async def log_to_file_async(text):
    timestamp = datetime.now().strftime('%H:%M:%S')
    msg = f"[{timestamp}] {text}"
    print(msg, flush=True)
    try:
        async with aiofiles.open(DEBUG_FILE, "a", encoding="utf-8") as f:
            await f.write(msg + "\n")
    except Exception:
        pass

# === УПРАВЛЕНИЕ ПРОЦЕССОМ ===
def check_if_alive():
    if not os.path.exists(PID_FILE): return False
    return True

def register_process():
    with open(PID_FILE, 'w') as f:
        f.write(f"{os.getpid()}|{time.time()}")
    # Фоновый поток keep-alive
    threading.Thread(target=lambda: (time.sleep(100000)), daemon=True).start()

def cleanup_process():
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except: pass

# === БАЗА ДАННЫХ ===
async def get_chats_to_scan(db):
    try:
        rows = await db.fetch("""
            SELECT chat_link, last_scan_id, depth, chat_title 
            FROM monitored_chats 
            WHERE is_active = TRUE 
            ORDER BY updated_at ASC
        """)
        return [(r['chat_link'].strip(), r['last_scan_id'], r['depth'], r['chat_title']) for r in rows]
    except Exception as e:
        await log_to_file_async(f"❌ DB Read Error: {e}")
        return []

async def update_chat_status(db, chat_link, status, progress, new_last_id=None):
    try:
        chat_link = chat_link.strip()
        if new_last_id is not None:
            await db.execute(
                """UPDATE monitored_chats 
                   SET status_msg=$1, progress=$2, last_scan_id=$3, updated_at=NOW() 
                   WHERE chat_link=$4""",
                status, progress, new_last_id, chat_link
            )
        else:
            await db.execute(
                """UPDATE monitored_chats 
                   SET status_msg=$1, progress=$2, updated_at=NOW() 
                   WHERE chat_link=$3""",
                status, progress, chat_link
            )
    except Exception as e:
        await log_to_file_async(f"Status Update Error: {e}")

async def save_lead(db, uid, uname, name, bio, prem, new_role, intent, source, msg):
    try:
        clean_msg = msg.replace('\x00', '')[:3000]
        now = datetime.now()
        
        row = await db.fetchrow("SELECT role FROM leads WHERE user_id = $1", uid)
        should_notify = False

        if row:
            await db.execute(
                """
                UPDATE leads 
                SET username=$1, full_name=$2, bio=$3, is_premium=$4, 
                    intent=$6, source_chat=$7, last_message=$8, updated_at=$9 
                WHERE user_id=$10
                """,
                uname, name, bio, prem, new_role, intent, source, clean_msg, now, uid
            )
            should_notify = True 
        else:
            await db.execute(
                """
                INSERT INTO leads 
                (user_id, username, full_name, bio, is_premium, role, intent, source_chat, last_message, updated_at) 
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                uid, uname, name, bio, prem, new_role, intent, source, clean_msg, now
            )
            should_notify = True
            
        return should_notify
    except Exception as e:
        await log_to_file_async(f"❌ DB Save Error (UID {uid}): {e}")
        return False

# === AI LOGIC ===
def clean_text_aggressive(text):
    return re.sub(r'[^\w\s.,!?-]', '', text)

def analyze_with_ai(history):
    if not config.DEEPSEEK_API_KEY or len(config.DEEPSEEK_API_KEY) < 5:
        return "LEAD", "No AI Key (Auto-Lead)"

    clean_history = clean_text_aggressive(history)[:1200]
    client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    
    try:
        resp = client.chat.completions.create(
            model=config.MODEL_NAME, 
            messages=[
                {"role": "system", "content": "Classify Telegram msg. Output format: ROLE | SHORT_SUMMARY. Roles: LEAD (buyer/seller), SPAM (ads/crypto/jobs), EXPERT, MIMO (chatting)."},
                {"role": "user", "content": clean_history}
            ],
            temperature=0.1, timeout=10
        )
        content = resp.choices[0].message.content
        if "|" in content:
            parts = content.split("|", 1)
            return parts[0].strip().upper(), parts[1].strip()
        return "LEAD", content[:50] 
    except Exception as e:
        return "LEAD", f"AI Error: {str(e)[:20]}"

# === MAIN LOGIC ===
async def process_chat(app, db, chat_data):
    link, last_id, depth, title_db = chat_data
    
    target_chat = None
    try:
        if "t.me/+" in link or "joinchat" in link:
            try: await app.join_chat(link) 
            except: pass
            chat_info = await app.get_chat(link)
            target_chat = chat_info.id
        else:
            s = link.replace("https://t.me/", "").replace("@", "").strip()
            target_chat = int(s) if s.lstrip("-").isdigit() else s
            try: await app.get_chat(target_chat)
            except Exception: 
                try: await app.join_chat(target_chat)
                except: pass
    except Exception as e:
        await log_to_file_async(f"⚠️ Link error {link}: {e}")
        return

    if not target_chat: return

    scan_limit = depth if depth else 50
    safe_last_id = last_id if last_id else 0
    new_last_id = safe_last_id
    users_batch = defaultdict(list)
    
    try:
        count_found = 0
        async for msg in app.get_chat_history(target_chat, limit=scan_limit):
            if not msg.id: continue
            if safe_last_id > 0 and msg.id <= safe_last_id: break
            new_last_id = max(new_last_id, msg.id)
            if msg.from_user and not msg.from_user.is_bot:
                text = msg.text or msg.caption or ""
                if len(text.strip()) > 1:
                    users_batch[msg.from_user.id].append(msg)
                    count_found += 1
        
        if count_found == 0:
            await update_chat_status(db, link, "💤 Нет новых", 100, new_last_id)
            return

        await log_to_file_async(f"📦 {title_db}: Обработка {len(users_batch)} авторов...")
        
        processed_cnt = 0
        sent_cnt = 0
        
        for uid, msgs in users_batch.items():
            try:
                user = msgs[0].from_user
                full_text = " | ".join([m.text or m.caption or "" for m in msgs])
                
                role, intent = analyze_with_ai(full_text)
                
                uname = f"@{user.username}" if user.username else "NoUsername"
                display_name = f"{user.first_name} {user.last_name or ''}".strip()
                
                saved = await save_lead(
                    db, uid, uname, display_name, 
                    user.bio or "", user.is_premium or False, 
                    role, intent, title_db or link, full_text
                )
                
                if saved:
                    processed_cnt += 1
                    target_roles = ["LEAD", "EXPERT"] 
                    
                    if role in target_roles:
                        try:
                            alert_text = (
                                f"<b>#{role} detected!</b>\n"
                                f"👤 <b>{display_name}</b> ({uname})\n"
                                f"🎯 <b>Intent:</b> {intent}\n"
                                f"📂 <b>Source:</b> {title_db or link}\n"
                                f"📝 <b>Text:</b> {full_text[:200]}..."
                            )
                            dest_id = getattr(config, 'SOURCE_CHANNEL', None)
                            if dest_id:
                                await app.send_message(dest_id, alert_text, parse_mode=enums.ParseMode.HTML)
                                sent_cnt += 1
                        except Exception as e:
                            await log_to_file_async(f"⚠️ Send Error: {e}")
            except Exception as e:
                continue

        status_msg = f"✅ Scanned {len(users_batch)}"
        if sent_cnt > 0:
            status_msg += f" | 🚀 Sent {sent_cnt}"
            
        await update_chat_status(db, link, status_msg, 100, new_last_id)
        
    except Exception as e:
        await update_chat_status(db, link, "❌ Ошибка", 0)
        await log_to_file_async(f"CRITICAL {title_db}: {e}")
        traceback.print_exc()

async def watcher_loop():
    print("\n--- 🚀 WATCHER STARTED ---", flush=True)
    register_process()
    
    db = AsyncDatabase()
    if not await db.connect():
        print("❌ Failed to connect to DB. Exiting.")
        return

    app = Client(
        "memory_session", 
        api_id=config.API_ID, 
        api_hash=config.API_HASH, 
        session_string=config.SESSION_STRING, 
        in_memory=True
    )
    
    try: 
        await app.start()
        await log_to_file_async("✅ Bot started & connected to Telegram.")
    except Exception as e: 
        await log_to_file_async(f"LOGIN FAIL: {e}")
        await db.close()
        cleanup_process()
        return

    try:
        while True:
            if not check_if_alive():
                print("💀 PID file missing, shutting down.")
                break
            
            chats = await get_chats_to_scan(db)
            if not chats: 
                await log_to_file_async("💤 Список чатов пуст. Жду 30 сек...")
                await asyncio.sleep(30)
                continue

            for chat_data in chats:
                if not check_if_alive(): break
                await process_chat(app, db, chat_data)
                await asyncio.sleep(2)
            
            await asyncio.sleep(15)
            
    finally:
        try: await app.stop()
        except: pass
        await db.close()
        cleanup_process()

if __name__ == "__main__":
    try:
        asyncio.run(watcher_loop())
    except KeyboardInterrupt:
        pass