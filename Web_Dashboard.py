import streamlit as st
import pandas as pd
import psycopg2
import time
import os
import sys
import signal
import subprocess
import warnings
from datetime import datetime

# === ПОДАВЛЕНИЕ ПРЕДУПРЕЖДЕНИЙ ===
warnings.filterwarnings("ignore", category=UserWarning)

# === ПОДКЛЮЧАЕМ КОНФИГ ===
try:
    import config
except ImportError:
    st.error("Файл config.py не найден! Убедитесь, что он лежит рядом.")
    st.stop()

# === НАСТРОЙКИ ПУТЕЙ ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BASE_DIR, "watcher.pid")
BOT_LOG_FILE = os.path.join(BASE_DIR, "bot_output.log")
BOT_SCRIPT = os.path.join(BASE_DIR, "TheWatcher.py")

# Пути для MarketWatcher
MARKET_DIR = os.path.join(BASE_DIR, "MarketWatcher")
MARKET_SCRIPT = os.path.join(MARKET_DIR, "parser_engine.py")
MARKET_LOG_FILE = os.path.join(BASE_DIR, "market_output.log")
MARKET_PID_FILE = os.path.join(BASE_DIR, "market.pid")

st.set_page_config(page_title="ZGRNK Control Center", page_icon="👁", layout="wide")

if 'session_start' not in st.session_state:
    st.session_state['session_start'] = pd.Timestamp.now()

# --- ФУНКЦИИ ---
def get_connection():
    return psycopg2.connect(
        host=config.DB_HOST, database=config.DB_NAME,
        user=config.DB_USER, password=config.DB_PASS, port=config.DB_PORT
    )

def load_data():
    try:
        conn = get_connection()
        query = "SELECT * FROM leads ORDER BY updated_at DESC LIMIT 500"
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception: return pd.DataFrame()

def get_global_stats():
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM leads")
        total_processed = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM leads WHERE role='SPAM'")
        total_spam = cur.fetchone()[0]
        conn.close()
        return total_processed, total_spam
    except Exception: return 0, 0

def load_chats():
    try:
        conn = get_connection()
        query = "SELECT chat_link, chat_title, is_active, status_msg, progress, depth FROM monitored_chats ORDER BY is_active DESC, chat_title"
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception: return pd.DataFrame()

def add_new_chat(link, title, depth):
    try:
        conn = get_connection(); cur = conn.cursor()
        if not title: title = link.split('/')[-1] if '/' in link else link
        cur.execute("INSERT INTO monitored_chats (chat_link, chat_title, is_active, depth, last_scan_id) VALUES (%s, %s, TRUE, %s, 0)", (link, title, depth))
        conn.commit(); conn.close()
        return True
    except Exception as e:
        st.error(f"Ошибка добавления: {e}"); return False

def save_changes(edited_df):
    try:
        conn = get_connection(); cur = conn.cursor()
        to_delete = edited_df[edited_df['delete'] == True]
        for index, row in to_delete.iterrows():
            cur.execute("DELETE FROM monitored_chats WHERE chat_link=%s", (row['chat_link'],))
        to_update = edited_df[edited_df['delete'] == False]
        for index, row in to_update.iterrows():
            cur.execute("UPDATE monitored_chats SET is_active=%s, depth=%s, chat_title=%s WHERE chat_link=%s", (bool(row['is_active']), int(row['depth']), str(row['chat_title']), row['chat_link']))
        conn.commit(); conn.close()
        st.success(f"Сохранено!"); time.sleep(1); return True
    except Exception as e:
        st.error(f"Ошибка сохранения: {e}"); return False

def get_pid_status(pid_file):
    if not os.path.exists(pid_file): return False, "Выключено"
    try:
        with open(pid_file, 'r') as f:
            content = f.read().strip()
            pid = int(content.split("|")[0] if "|" in content else content)
        os.kill(pid, 0)
        return True, f"Работает (PID {pid})"
    except: return False, "PID мертв/Завершен"

def start_bot():
    if os.path.exists(BOT_LOG_FILE): open(BOT_LOG_FILE, 'w').close()
    with open(BOT_LOG_FILE, "a") as log:
        subprocess.Popen([sys.executable, "-u", BOT_SCRIPT], cwd=BASE_DIR, stdout=log, stderr=log)
    time.sleep(2)

def stop_bot():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip().split("|")[0])
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
        except: pass
        if os.path.exists(PID_FILE): os.remove(PID_FILE)

def stop_market():
    if os.path.exists(MARKET_PID_FILE):
        try:
            with open(MARKET_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            st.warning("Процесс Market Watcher остановлен принудительно.")
        except: pass
        if os.path.exists(MARKET_PID_FILE): os.remove(MARKET_PID_FILE)

def read_logs(file_path):
    if not os.path.exists(file_path): return ["Лог-файл пуст или не создан."]
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()[-100:] 
    except Exception as e: return [f"Ошибка: {e}"]

# --- UI START ---
st.title("🚀 ZGRNK Orchestrator")

# === SIDEBAR (Только кнопки управления) ===
with st.sidebar:
    st.header("🤖 Telegram Watcher")
    is_running, status_msg = get_pid_status(PID_FILE)
    st.metric("Статус бота", status_msg, delta="ON" if is_running else "OFF", help="Показывает, запущен ли фоновый процесс парсинга чатов.")
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ СТАРТ", disabled=is_running, type="primary", help="Запустить процесс мониторинга Telegram"):
            start_bot(); st.rerun()
    with c2:
        if st.button("⏹ СТОП", disabled=not is_running, help="Остановить процесс мониторинга"):
            stop_bot(); st.rerun()

# === TABS ===
tab1, tab2, tab3 = st.tabs(["📊 Дашборд & Логи", "⚙️ Чаты", "🛍 Market Watcher"])

# === TAB 1: DASHBOARD + TELEGRAM LOGS ===
with tab1:
    st.header("📊 Статистика")
    df = load_data()
    total_processed, total_spam = get_global_stats()
    
    session_parsed = 0
    session_leads = 0
    
    if not df.empty:
        if not pd.api.types.is_datetime64_any_dtype(df['updated_at']):
            df['updated_at'] = pd.to_datetime(df['updated_at'])
        mask = df['updated_at'] > st.session_state['session_start']
        session_parsed = len(df[mask])
        session_leads = len(df[mask][df[mask]['role'] == 'LEAD'])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Спаршено (сессия)", session_parsed, help="Сообщений обработано с момента открытия этой страницы.")
    c2.metric("Обработано (всего)", total_processed, help="Всего сообщений в базе данных за всё время.")
    c3.metric("🔥 Лиды (сессия)", session_leads, delta=f"+{session_leads}", help="Новые целевые сообщения (Лиды), найденные прямо сейчас.")
    c4.metric("🗑 Спам (всего)", total_spam, help="Общее количество отфильтрованного мусора.")

    st.divider()
    
    # === ЛОГИ ТЕЛЕГРАМА ===
    with st.expander("🖥️ КОНСОЛЬ ТЕЛЕГРАМ БОТА", expanded=True):
        col_l1, col_l2 = st.columns([1, 5])
        with col_l1:
            if st.button("🔄 Обновить логи TG", help="Нажмите, если логи не обновляются автоматически"):
                st.rerun()
        with col_l2:
            st.download_button("📥 Скачать лог", "".join(read_logs(BOT_LOG_FILE)), "bot_log.txt", help="Скачать полный файл логов себе на компьютер")
        
        st.text_area("Вывод бота:", "".join(read_logs(BOT_LOG_FILE)), height=300, disabled=True, help="Здесь отображается живой вывод процесса. Можно выделять и копировать текст.")

    st.divider()
    if not df.empty:
        st.subheader("Лента событий")
        st.dataframe(
            df[['role', 'intent', 'source_chat', 'username', 'last_message', 'updated_at']],
            use_container_width=True,
            column_config={
                "updated_at": st.column_config.DatetimeColumn("Время", format="HH:mm:ss"),
                "last_message": st.column_config.TextColumn("Текст", width="large"),
                "role": st.column_config.TextColumn("Роль", help="Классификация: ЛИД, СПАМ, МИМО"),
                "intent": st.column_config.TextColumn("Намерение", help="Что хотел автор (кратко)")
            }
        )
    else: st.info("Нет данных.")

# === TAB 2: CHATS ===
with tab2:
    st.subheader("Управление чатами")
    with st.expander("➕ Добавить чат"):
        c1, c2, c3 = st.columns([2, 2, 1])
        new_link = c1.text_input("Ссылка", placeholder="https://t.me/...", help="публичные ссылки (t.me/chat), юзернеймы (@chat) и приватные ссылки (t.me/joinchat)")
        new_title = c2.text_input("Название", placeholder="Рабочий чат", help="Название для удобства в таблице (необязательно)")
        new_depth = c2.number_input("Глубина", value=200, step=100, help="Сколько последних сообщений проверять при каждом заходе")
        c3.write(""); c3.write("")
        if c3.button("Добавить", type="primary", help="Сохранить чат в базу мониторинга"):
            if new_link: 
                add_new_chat(new_link, new_title, new_depth)
                st.success("ОК"); time.sleep(0.5); st.rerun()

    st.divider()
    chats_df = load_chats()
    if not chats_df.empty:
        chats_df['delete'] = False
        edited = st.data_editor(
            chats_df, 
            use_container_width=True, 
            hide_index=True, 
            column_config={
                "delete": st.column_config.CheckboxColumn("Удалить?", help="Отметьте, чтобы удалить чат из базы"), 
                "chat_link": st.column_config.TextColumn("Ссылка", disabled=True),
                "is_active": st.column_config.CheckboxColumn("Вкл?", help="Снимите галочку, чтобы временно остановить парсинг этого чата")
            }, 
            disabled=["status_msg", "chat_link"]
        )
        if st.button("💾 Сохранить изменения", help="Применить удаления и изменения настроек"):
            save_changes(edited); st.rerun()
    else: st.warning("Список пуст.")

# === TAB 3: MARKET WATCHER + MARKET LOGS ===
with tab3:
    st.header("🛍 Market Watcher")
    
    st.info("💡 Парсер автоматически определяет маркетплейс (Ozon/WB) и использует ваши Cookies для входа.")
    
    target = st.text_input(
        "Ссылка на товар Ozon/WB", 
        placeholder="https://www.wildberries.ru/catalog/...",
        help="Вставьте полную ссылку на карточку товара."
    )
    
    col_m1, col_m2 = st.columns([1, 4])
    with col_m1:
        if st.button("🔎 ЗАПУСТИТЬ СКАН", type="primary", help="Начать сбор данных о цене и остатках"):
            if not target: st.warning("Нет ссылки!")
            else:
                m = "wb" if "wildberries" in target or "wb.ru" in target else "ozon" if "ozon" in target else None
                if m:
                    open(MARKET_LOG_FILE, 'w').close()
                    log_file = open(MARKET_LOG_FILE, "a")
                    process = subprocess.Popen(
                        [sys.executable, "-u", MARKET_SCRIPT, "--target", target, "--market", m], 
                        cwd=MARKET_DIR, stdout=log_file, stderr=log_file
                    )
                    with open(MARKET_PID_FILE, 'w') as f: f.write(str(process.pid))
                    st.toast(f"Процесс запущен (PID {process.pid})!")
                    time.sleep(1); st.rerun()
                else: st.error("Неизвестный маркетплейс. Используйте ссылки Ozon или Wildberries.")
    
    with col_m2:
        if st.button("⏹ ОСТАНОВИТЬ СКАН", help="Принудительно завершить процесс парсинга"):
            stop_market(); st.rerun()

    st.divider()

    # === ЛОГИ МАРКЕТА ===
    st.subheader("📋 Логи парсера товаров")
    col_ml1, col_ml2 = st.columns([1, 5])
    with col_ml1:
        if st.button("🔄 Обновить логи маркета", help="Обновить вывод консоли"):
            st.rerun()
            
    market_logs = "".join(read_logs(MARKET_LOG_FILE))
    
    if not market_logs:
        st.info("Ожидание запуска...")
    else:
        st.code(market_logs, language="log")