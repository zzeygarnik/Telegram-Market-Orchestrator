import streamlit as st
import pandas as pd
import psycopg2
import time
import os
import sys
import signal
import subprocess
from datetime import datetime

# === КОНФИГУРАЦИЯ ===
st.set_page_config(page_title="ZGRNK Control Center", page_icon="🎛️", layout="wide")

# Пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BASE_DIR, "watcher.pid")
BOT_SCRIPT = os.path.join(BASE_DIR, "watcher.py")
BOT_LOG = os.path.join(BASE_DIR, "debug_log.txt") 

MARKET_DIR = os.path.join(BASE_DIR, "MarketWatcher")
MARKET_SCRIPT = os.path.join(MARKET_DIR, "parser_engine.py")
MARKET_PID_FILE = os.path.join(BASE_DIR, "market.pid")
MARKET_LOG = os.path.join(BASE_DIR, "market_output.log")

try:
    import config
except ImportError:
    st.error("❌ config.py не найден!")
    st.stop()

# === БД ===
def get_conn():
    return psycopg2.connect(
        host=config.DB_HOST, port=config.DB_PORT, 
        database=config.DB_NAME, user=config.DB_USER, password=config.DB_PASS
    )

def run_query(query, params=None, fetch=True):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            data = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
            df = pd.DataFrame(data, columns=cols)
            conn.close()
            return df
        else:
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        print(f"DB Error: {e}") 
        return None

# Функция для сохранения изменений из редактора
def save_chat_changes(df_source, edited_rows):
    conn = get_conn()
    cur = conn.cursor()
    try:
        for index, changes in edited_rows.items():
            # Получаем реальный ID из исходного датафрейма по индексу строки
            chat_id = int(df_source.iloc[int(index)]['id'])
            
            for key, value in changes.items():
                if key == "is_active":
                    cur.execute("UPDATE monitored_chats SET is_active = %s WHERE id = %s", (bool(value), chat_id))
                elif key == "chat_title":
                    cur.execute("UPDATE monitored_chats SET chat_title = %s WHERE id = %s", (str(value), chat_id))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Ошибка сохранения: {e}")
        return False
    finally:
        conn.close()

# === ПРОЦЕССЫ ===
def check_pid(pid_file):
    if os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                content = f.read().strip()
                if not content: return False, None
                pid = int(content.split("|")[0])
            os.kill(pid, 0)
            return True, pid
        except: return False, None
    return False, None

# === ИНТЕРФЕЙС ===
st.title("🎛️ ZGRNK Orchestrator")

tab_tg, tab_leads, tab_market = st.tabs(["🤖 Telegram Watcher", "👥 База Лидов", "🛍️ Market Watcher"])

# ---------------------------------------------------------------------
# TAB 1: TELEGRAM
# ---------------------------------------------------------------------
with tab_tg:
    # --- Status Panel ---
    alive, pid = check_pid(PID_FILE)
    c1, c2 = st.columns([3, 1])
    with c1:
        if alive: st.success(f"Telegram Bot: **ONLINE** (PID {pid})")
        else: st.error("Telegram Bot: **OFFLINE**")
    with c2:
        if alive:
            if st.button("⏹ STOP TG", use_container_width=True):
                os.kill(pid, signal.SIGTERM)
                if os.path.exists(PID_FILE): os.remove(PID_FILE)
                st.rerun()
        else:
            if st.button("▶️ START TG", type="primary", use_container_width=True):
                subprocess.Popen([sys.executable, BOT_SCRIPT], cwd=BASE_DIR)
                time.sleep(1)
                st.rerun()
    
    st.divider()

    # --- ЛОГИ БОТА ---
    st.subheader("📜 Логи Бота")
    c_log1, c_log2 = st.columns([6, 1])
    with c_log2:
        if st.button("🔄 Обновить"): st.rerun()
        if st.button("🗑 Очистить"):
            open(BOT_LOG, 'w').close()
            st.rerun()
            
    if os.path.exists(BOT_LOG):
        with open(BOT_LOG, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            st.code("".join(lines[-40:]), language="text")
    else:
        st.info("Файл логов пуст.")

    st.divider()

    # --- Add Chat ---
    with st.expander("➕ Добавить чат", expanded=False):
        with st.form("add_chat"):
            col_a, col_b = st.columns([3, 1])
            new_link = col_a.text_input("Ссылка", placeholder="https://t.me/...")
            new_title = col_b.text_input("Название")
            new_depth = st.number_input("Глубина", value=100, step=10)
            
            if st.form_submit_button("Добавить"):
                if new_link:
                    sql = "INSERT INTO monitored_chats (chat_link, chat_title, depth, is_active) VALUES (%s, %s, %s, TRUE) ON CONFLICT (chat_link) DO NOTHING"
                    run_query(sql, (new_link, new_title, new_depth), fetch=False)
                    st.rerun()

    # --- Chat List (FIXED SAVING) ---
    st.subheader("📋 Активные чаты")
    
    # 1. Загружаем данные
    df_chats = run_query("SELECT id, is_active, chat_title, chat_link, updated_at, status_msg FROM monitored_chats ORDER BY id ASC")
    
    if df_chats is not None and not df_chats.empty:
        # 2. Показываем редактор
        edited_df = st.data_editor(
            df_chats,
            key="chats_editor",
            use_container_width=True,
            column_config={
                "is_active": st.column_config.CheckboxColumn("Вкл?", width="small"),
                "chat_link": st.column_config.LinkColumn("Ссылка", disabled=True),
                "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                "chat_title": st.column_config.TextColumn("Название", width="medium"),
                "updated_at": st.column_config.DatetimeColumn("Посл. скан", format="HH:mm DD.MM"),
                "status_msg": st.column_config.TextColumn("Статус", disabled=True)
            },
            hide_index=True
        )
        
        # 3. ЛОВИМ ИЗМЕНЕНИЯ И СОХРАНЯЕМ!
        # Проверяем состояние виджета (session_state)
        if st.session_state["chats_editor"]["edited_rows"]:
            # Если есть изменения - сохраняем
            if save_chat_changes(df_chats, st.session_state["chats_editor"]["edited_rows"]):
                st.toast("✅ Изменения сохранены!")
                time.sleep(0.5)
                st.rerun() # Перезагрузка, чтобы сбросить "edited_rows"

        # 4. Удаление
        chat_options = {row['id']: f"{row['chat_title']} ({row['chat_link']})" for i, row in df_chats.iterrows()}
        del_ids = st.multiselect("Удалить чаты:", options=chat_options.keys(), format_func=lambda x: chat_options[x])
        
        if del_ids and st.button("🗑 Удалить выбранные"):
            for did in del_ids:
                run_query("DELETE FROM monitored_chats WHERE id=%s", (did,), fetch=False)
            st.rerun()
            
    else:
        st.info("Список чатов пуст.")

# ---------------------------------------------------------------------
# TAB 2: LEADS
# ---------------------------------------------------------------------
with tab_leads:
    st.subheader("👥 База Лидов")
    
    col_f1, col_f2 = st.columns([3, 1])
    search_query = col_f1.text_input("🔍 Поиск", placeholder="python developer...")
    role_filter = col_f2.multiselect("Роль", ["LEAD", "EXPERT", "MIMO", "SPAM"], default=["LEAD", "EXPERT"])
    
    try:
        sql = "SELECT * FROM leads WHERE role = ANY(%s) "
        params = [role_filter if role_filter else ["LEAD", "EXPERT", "MIMO", "SPAM"]]
        
        if search_query:
            sql += " AND (last_message ILIKE %s OR full_name ILIKE %s)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
            
        sql += " ORDER BY updated_at DESC LIMIT 100"
        
        df_leads = run_query(sql, tuple(params))
        
        if df_leads is not None:
            st.dataframe(df_leads, use_container_width=True)
    except: pass

# ---------------------------------------------------------------------
# TAB 3: MARKET WATCHER
# ---------------------------------------------------------------------
with tab_market:
    m_alive, m_pid = check_pid(MARKET_PID_FILE)
    mc1, mc2 = st.columns([3, 1])
    with mc1:
        if m_alive: st.success(f"Market Parser: **ONLINE** (PID {m_pid})")
        else: st.warning("Market Parser: **OFFLINE**")
    with mc2:
        if m_alive:
            if st.button("⏹ STOP MARKET", use_container_width=True):
                os.kill(m_pid, signal.SIGTERM)
                if os.path.exists(MARKET_PID_FILE): os.remove(MARKET_PID_FILE)
                st.rerun()
        else:
            if st.button("▶️ START MARKET", type="primary", use_container_width=True):
                log = open(MARKET_LOG, "a")
                proc = subprocess.Popen([sys.executable, MARKET_SCRIPT], cwd=MARKET_DIR, stdout=log, stderr=log)
                with open(MARKET_PID_FILE, "w") as f: f.write(str(proc.pid))
                time.sleep(1)
                st.rerun()
    
    st.divider()

    st.subheader("🛍 Добавить товар")
    with st.form("add_market_item"):
        c_p1, c_p2, c_p3 = st.columns([3, 1, 1])
        p_url = c_p1.text_input("Ссылка (WB/Ozon)")
        p_name = c_p2.text_input("Название")
        p_price = c_p3.number_input("Целевая цена", min_value=0, step=100)
        
        if st.form_submit_button("✅ Отслеживать"):
            if p_url:
                run_query(
                    "INSERT INTO market_items (url, name, target_price) VALUES (%s, %s, %s) ON CONFLICT (url) DO NOTHING",
                    (p_url, p_name, p_price), fetch=False
                )
                st.rerun()

    st.divider()

    df_items = run_query("SELECT id, name, url, last_price, target_price, status, updated_at FROM market_items ORDER BY id DESC")
    if df_items is not None and not df_items.empty:
        st.data_editor(df_items, use_container_width=True, hide_index=True) # Пока только просмотр для маркета, чтобы не перегружать
        
        item_opts = {row['id']: f"{row['name']} ({row['last_price']} ₽)" for i, row in df_items.iterrows()}
        del_items = st.multiselect("Удалить товары:", options=item_opts.keys(), format_func=lambda x: item_opts[x])
        if del_items and st.button("🗑 Удалить товары"):
            for i in del_items:
                run_query("DELETE FROM market_items WHERE id=%s", (i,), fetch=False)
            st.rerun()
    
    with st.expander("📜 Логи Парсера", expanded=True):
        if st.button("Обновить лог маркета"): st.rerun()
        if os.path.exists(MARKET_LOG):
            with open(MARKET_LOG, "r", encoding="utf-8", errors="ignore") as f:
                 st.code("".join(f.readlines()[-20:]))