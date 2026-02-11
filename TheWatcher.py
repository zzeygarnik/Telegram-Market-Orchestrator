import asyncio
try: asyncio.get_event_loop()
except RuntimeError: asyncio.set_event_loop(asyncio.new_event_loop())

import os
import psycopg2
import sys
import signal
import logging
import threading
import time
import json
import re 
import traceback
from datetime import datetime
from collections import defaultdict
from pyrogram import Client
from pyrogram.errors import FloodWait, UserNotParticipant, ChannelPrivate, PeerIdInvalid, UserAlreadyParticipant
from openai import OpenAI, BadRequestError 

# === ПОДКЛЮЧАЕМ КОНФИГ ===
import config 
# =========================

# === ПУТИ ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BASE_DIR, "watcher.pid")
STATS_FILE = os.path.join(BASE_DIR, "session_stats.json")
CRASH_FILE = os.path.join(BASE_DIR, "crash_log.txt") 
DEBUG_FILE = os.path.join(BASE_DIR, "debug_log.txt") 
# ============

def log_to_file(text):
    msg = f"[{datetime.now().strftime('%H:%M:%S')}] {text}"
    print(msg) 
    try:
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except: pass

def log(msg): log_to_file(msg)
def log_error(msg): log_to_file(f"❌ {msg}")

STATS = { "scanned": 0, "processed": 0 }

def im_alive_check():
    if not os.path.exists(PID_FILE): return False
    try:
        with open(PID_FILE, 'r') as f:
            content = f.read().strip()
            pid_in_file = int(content.split("|")[0] if "|" in content else content)
            if pid_in_file != os.getpid():
                os._exit(0) 
    except: pass
    return True

def save_stats():
    im_alive_check()
    try:
        with open(STATS_FILE, 'w') as f: 
            json.dump(STATS, f)
            f.flush()
            os.fsync(f.fileno())
    except: pass

def keep_alive_thread():
    while True:
        try:
            if not os.path.exists(PID_FILE): break
            if not im_alive_check(): break
            os.utime(PID_FILE, None)
            time.sleep(5)
        except: break

def register_process():
    if os.path.exists(CRASH_FILE):
        try: os.remove(CRASH_FILE)
        except: pass
    if os.path.exists(DEBUG_FILE):
        try: os.remove(DEBUG_FILE)
        except: pass
    with open(PID_FILE, 'w') as f: f.write(f"{os.getpid()}|{time.time()}")
    STATS["scanned"] = 0; STATS["processed"] = 0; save_stats()
    threading.Thread(target=keep_alive_thread, daemon=True).start()

def cleanup_process():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip().split("|")[0])
            if pid == os.getpid():
                os.remove(PID_FILE)
        except: pass

signal.signal(signal.SIGINT, lambda s,f: (cleanup_process(), sys.exit(0)))
signal.signal(signal.SIGTERM, lambda s,f: (cleanup_process(), sys.exit(0)))

def get_db_connection():
    # БЕРЕМ ДАННЫЕ ИЗ CONFIG.PY
    conn = psycopg2.connect(
        host=config.DB_HOST,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASS,
        port=config.DB_PORT
    )
    conn.autocommit = True
    return conn

def get_chats_to_scan():
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SELECT chat_link, last_scan_id, depth, chat_title FROM monitored_chats WHERE is_active = TRUE")
        rows = cursor.fetchall(); conn.close()
        cleaned = []
        for r in rows: 
            cleaned.append((r[0].strip(), r[1], r[2], r[3]))
        return cleaned
    except Exception as e: log_error(f"DB Error: {e}"); return []

def update_chat_status(chat_link, status, progress, new_last_id=None):
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        chat_link = chat_link.strip()
        if new_last_id is not None:
            cursor.execute("UPDATE monitored_chats SET status_msg=%s, progress=%s, last_scan_id=%s WHERE chat_link=%s", (status, progress, new_last_id, chat_link))
        else:
            cursor.execute("UPDATE monitored_chats SET status_msg=%s, progress=%s WHERE chat_link=%s", (status, progress, chat_link))
        conn.close()
    except Exception as e: log_error(f"Status Error: {e}")

def save_lead_eye(uid, uname, name, bio, prem, new_role, intent, final_source_name, msg):
    try:
        clean_msg = msg.replace('\x00', '')
        conn = get_db_connection(); cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("SELECT role, username FROM leads WHERE user_id = %s", (uid,))
        row = cursor.fetchone()
        
        final_uname_to_write = uname
        if uname == "NoUsername":
            if row and row[1] and row[1].startswith("@"):
                final_uname_to_write = row[1]
            else:
                final_uname_to_write = f"ID: {uid}"

        if row:
            current_role = row[0]
            role_weight = {"LEAD": 3, "EXPERT": 2, "SPAM": 1, "MIMO": 0}
            old_weight = role_weight.get(current_role, 0)
            new_weight = role_weight.get(new_role, 0)
            final_role = new_role 
            
            if old_weight > new_weight: final_role = current_role
            if new_role == "SPAM": final_role = "SPAM"

            cursor.execute('UPDATE leads SET username=%s, full_name=%s, bio=%s, is_premium=%s, role=%s, intent=%s, source_chat=%s, last_message=%s, updated_at=%s WHERE user_id=%s', (final_uname_to_write, name, bio, prem, final_role, intent, final_source_name, clean_msg, now, uid))
        else:
            cursor.execute('INSERT INTO leads (user_id, username, full_name, bio, is_premium, role, intent, source_chat, last_message, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', (uid, final_uname_to_write, name, bio, prem, new_role, intent, final_source_name, clean_msg, now))
        conn.close()
    except Exception as e:
        log_error(f"DB Save Error: {e}")

def clean_text_aggressive(text):
    return re.sub(r'[^\w\s.,!?-]', '', text)

def keyword_fallback(text):
    t = text.lower()
    if "kyc" in t or "wts" in t or "продам" in t or "аккаунт" in t or "документ" in t:
        return "ЛИД", "Продажа (Fallback)"
    if "wtb" in t or "куплю" in t or "ищу" in t or "надо" in t:
        return "ЛИД", "Покупка (Fallback)"
    if "работа" in t or "вакансия" in t or "требуется" in t or "зарплата" in t:
        return "СПАМ", "Вакансия (Fallback)"
    return "МИМО", "AI_Error_Fallback"

def analyze_with_ai(history):
    # БЕРЕМ КЛЮЧ ИЗ CONFIG
    if "sk-..." in config.DEEPSEEK_API_KEY or not config.DEEPSEEK_API_KEY: 
        return "MIMO", "NO KEY"
    
    if not history or not isinstance(history, str): return "MIMO", "Empty"
    
    clean_history = clean_text_aggressive(history)[:1200]
    
    text_check = clean_history.lower().strip()
    if len(text_check) < 4 and text_check in ["hi", "hello", "привет", "ку", "hey"]:
        return "MIMO", "Приветствие"

    # ИСПОЛЬЗУЕМ КЛЮЧ ИЗ CONFIG
    client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    
    system_prompt = """
Ты — классификатор сообщений Telegram.
ОТВЕЧАЙ СТРОГО В ФОРМАТЕ: РОЛЬ | ОПИСАНИЕ

СПИСОК РОЛЕЙ (ИСПОЛЬЗУЙ ТОЛЬКО ИХ):
- LEAD (если хотят купить, продать, ищут услугу, WTB, WTS)
- SPAM (если реклама канала, вакансия, скам)
- EXPERT (если дают технический совет)
- MIMO (если флуд, приветствия, мусор)

Пример:
LEAD | Хочет купить аккаунт
SPAM | Реклама казино
"""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=config.MODEL_NAME, # МОДЕЛЬ ИЗ CONFIG
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Txt:\n{clean_history}"}],
                temperature=0.0, stream=False, timeout=15 
            )
            t = resp.choices[0].message.content
            if not t: raise ValueError("Empty")
            
            raw_role = "MIMO"
            intent = "Auto"

            if "|" in t:
                parts = t.split("|", 1)
                raw_role = parts[0].strip().upper() 
                intent = parts[1].strip()
            else:
                raw_role = "MIMO"
                intent = t[:50]

            if "WTS" in raw_role or "WTB" in raw_role or "SELL" in raw_role or "BUY" in raw_role:
                final_role = "LEAD"
            elif "JOB" in raw_role or "WORK" in raw_role:
                final_role = "SPAM"
            elif raw_role in ["LEAD", "SPAM", "EXPERT", "MIMO"]:
                final_role = raw_role
            else:
                final_role = "MIMO"
            
            return final_role, intent
            
        except BadRequestError:
            return keyword_fallback(history)
            
        except Exception as e:
            if attempt == max_retries - 1:
                return keyword_fallback(history)
            time.sleep(1)
            
    return "MIMO", "AI:Unknown"

def extract_best_username(user_obj):
    if not user_obj: return None
    if getattr(user_obj, "username", None): return user_obj.username
    if getattr(user_obj, "usernames", None):
        for u in user_obj.usernames:
            if getattr(u, "username", None): return u.username
    return None

def debug_dump_user(u, chat_title, msg_text):
    dump = f"\n💀 [DEBUG DUMP] X-RAY MODE\n"
    dump += f"   - Чат: {chat_title}\n"
    dump += f"   - Текст: {msg_text[:30]}...\n"
    dump += f"   - RAW OBJECT:\n{str(u)}\n"
    dump += "------------------------------------------------"
    log_to_file(dump)

def resolve_target(input_str):
    s = input_str.strip()
    if s.lstrip("-").isdigit(): return int(s)
    if "t.me/c/" in s:
        try:
            chat_id_part = s.split("t.me/c/")[-1].split("/")[0]
            return int(f"-100{chat_id_part}")
        except: pass
    if "t.me/" in s and "+" not in s: return s.split("t.me/")[-1].strip("/")
    return s.strip("@")

async def process_one_chat(app, chat_data):
    chat_link, last_id, depth, chat_title_db = chat_data
    
    target_chat = None
    try:
        if "t.me/+" in chat_link or "joinchat" in chat_link:
            try:
                await app.join_chat(chat_link)
                await asyncio.sleep(1) 
            except UserAlreadyParticipant: pass
            except Exception as e: log_error(f"Join Error: {e}") 

            chat_info = await app.get_chat(chat_link)
            target_chat = chat_info.id
        else:
            target_chat = resolve_target(chat_link)
    except Exception as e:
        log_error(f"Link Error ({chat_link}): {e}")
        return

    if not target_chat: return

    SCAN_LIMIT = depth if depth else 50
    safe_last_id = last_id if last_id else 0
    
    db_source_name = chat_title_db
    is_public_link = "t.me/" in chat_link and "+" not in chat_link and "joinchat" not in chat_link and "/c/" not in chat_link
    is_username = chat_link.startswith("@")
    if is_public_link or is_username: db_source_name = chat_link
    
    log(f"🔎 {db_source_name}")
    update_chat_status(chat_link, "Подключение...", 5)
    
    try:
        if isinstance(target_chat, int):
            try: await app.get_chat(target_chat)
            except: pass

        new_last_id = safe_last_id
        users_batch = defaultdict(list)
        fresh_users_map = {} 
        scanned_in_chat = 0
        
        async for msg in app.get_chat_history(target_chat, limit=SCAN_LIMIT):
            scanned_in_chat += 1
            STATS["scanned"] += 1
            if STATS["scanned"] % 5 == 0: save_stats()
            
            if scanned_in_chat % 50 == 0: await asyncio.sleep(0.01)
            if scanned_in_chat % 5 == 0:
                perc = 5 + int((scanned_in_chat / SCAN_LIMIT) * 80)
                update_chat_status(chat_link, f"Чтение ({scanned_in_chat})", perc)
            
            if not msg.id: continue
            if safe_last_id > 0 and msg.id <= safe_last_id: break 
            new_last_id = max(new_last_id, msg.id)
            
            if msg.sender_chat:
                users_batch[msg.sender_chat.id].append(msg)
                continue

            if not msg.from_user or msg.from_user.is_bot: continue
            text_content = msg.text or msg.caption or ""
            if not text_content.strip(): continue
            
            users_batch[msg.from_user.id].append(msg)

        save_stats()
        
        if users_batch:
            count = len(users_batch)
            update_chat_status(chat_link, f"Обновление ({count})...", 90)
            
            missing_info_ids = []
            for uid, msgs in users_batch.items():
                if msgs[0].from_user:
                    if not extract_best_username(msgs[0].from_user): missing_info_ids.append(uid)
                elif msgs[0].sender_chat:
                    if not extract_best_username(msgs[0].sender_chat): missing_info_ids.append(uid)
            
            if missing_info_ids:
                chunk_size = 100
                for i in range(0, len(missing_info_ids), chunk_size):
                    chunk = missing_info_ids[i:i + chunk_size]
                    try:
                        users_list = await app.get_users(chunk)
                        for usr in users_list: fresh_users_map[usr.id] = usr
                    except: pass
                    await asyncio.sleep(0.5)

            update_chat_status(chat_link, f"AI Analyze ({count})...", 95)
            
            for uid, msgs in users_batch.items():
                try:
                    STATS["processed"] += 1; save_stats()
                    
                    if msgs[0].from_user:
                        u_initial = msgs[0].from_user
                    else:
                        u_initial = msgs[0].sender_chat

                    u_fresh = fresh_users_map.get(uid)
                    u_final = u_fresh if u_fresh else u_initial
                    
                    final_username = extract_best_username(u_final)

                    if not final_username:
                        try:
                            full_peer = await app.get_chat(uid)
                            u_final = full_peer
                            final_username = extract_best_username(u_final)
                        except Exception: pass
                    
                    if not final_username and msgs[0].from_user:
                        try:
                            member = await app.get_chat_member(target_chat, uid)
                            if member.user:
                                u_final = member.user
                                final_username = extract_best_username(u_final)
                        except Exception: pass
                    
                    if not final_username:
                         try:
                             u_res = await app.get_users(uid)
                             u_final = u_res
                             final_username = extract_best_username(u_final)
                         except: pass

                    nm = f"@{final_username}" if final_username else "NoUsername"
                    
                    if not final_username:
                         debug_dump_user(u_final, db_source_name, msgs[0].text or "")

                    full_text = " | ".join([str(m.text or m.caption or "") for m in msgs])[:2000]

                    role, intent = analyze_with_ai(full_text)
                    
                    if hasattr(u_final, "first_name"):
                         full_name = u_final.first_name or ""
                         if u_final.last_name: full_name += f" {u_final.last_name}"
                    else:
                         full_name = getattr(u_final, "title", "Unknown")

                    bio = getattr(u_final, "bio", "") or getattr(u_final, "description", "") or "" 
                    is_prem = getattr(u_final, "is_premium", False)

                    save_lead_eye(uid, nm, full_name, bio, is_prem, role.strip().upper(), intent.strip(), db_source_name, full_text)
                    await asyncio.sleep(0.05)
                except Exception as e:
                    continue

        update_chat_status(chat_link, "✅ Ожидание", 100, new_last_id)
        
        if 'users_batch' in locals(): del users_batch
        if 'fresh_users_map' in locals(): del fresh_users_map
    
    except Exception as e:
        update_chat_status(chat_link, "❌ Ошибка", 0)
        log_error(f"CRITICAL: {e}")
        traceback.print_exc()

async def watcher_loop():
    global STATS
    print("\n--- 🚀 ZGRNK WATCHER (CONFIG MODE) ---")
    
    # ПРОВЕРЯЕМ СЕССИЮ ИЗ КОНФИГА
    if "ЗДЕСЬ_ТВОЯ" in config.SESSION_STRING or len(config.SESSION_STRING) < 50:
        log_error("ОШИБКА: Нет SESSION_STRING в config.py!"); return

    register_process()
    # ИНИЦИАЛИЗАЦИЯ КЛИЕНТА С ДАННЫМИ ИЗ КОНФИГА
    app = Client(
        "memory_session", 
        api_id=config.API_ID, 
        api_hash=config.API_HASH, 
        session_string=config.SESSION_STRING, 
        in_memory=True
    )
    
    try: await app.start(); log("✅ Login OK")
    except Exception as e: log_error(f"LOGIN FAIL: {e}"); cleanup_process(); return

    try:
        while True:
            if not im_alive_check(): break
            chats = get_chats_to_scan()
            if not chats: await asyncio.sleep(5); continue

            for chat_data in chats:
                if not im_alive_check(): break 
                await process_one_chat(app, chat_data)
                await asyncio.sleep(1)
            await asyncio.sleep(5)
    finally:
        try: await app.stop()
        except: pass
        cleanup_process()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(watcher_loop())