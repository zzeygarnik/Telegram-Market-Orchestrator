import streamlit as st
import pandas as pd
import psycopg2
import time
import os
import sys
import signal
import subprocess
import warnings

# === ПОДАВЛЕНИЕ ПРЕДУПРЕЖДЕНИЙ (ЧИСТИМ ЛОГИ) ===
warnings.filterwarnings("ignore", category=UserWarning)
# ===============================================

# === ПОДКЛЮЧАЕМ КОНФИГ ===
try:
    import config
except ImportError:
    st.error("Файл config.py не найден! Убедитесь, что он лежит рядом.")
    st.stop()

# === НАСТРОЙКИ ПУТЕЙ ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BASE_DIR, "watcher.pid")
BOT_LOG_FILE = os.path.join(BASE_DIR, "bot_output.log") # Файл для логов бота
BOT_SCRIPT = os.path.join(BASE_DIR, "TheWatcher.py")

# Пути для MarketWatcher
MARKET_DIR = os.path.join(BASE_DIR, "MarketWatcher")
MARKET_SCRIPT = os.path.join(MARKET_DIR, "parser_engine.py")

st.set_page_config(page_title="ZGRNK Control Center", page_icon="👁", layout="wide")

# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---
def get_connection():
    return psycopg2.connect(
        host=config.DB_HOST,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASS,
        port=config.DB_PORT
    )

def load_data():
    try:
        conn = get_connection()
        query = "SELECT * FROM leads ORDER BY updated_at DESC LIMIT 500"
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

def load_chats():
    try:
        conn = get_connection()
        query = "SELECT chat_link, chat_title, is_active, status_msg, progress, depth FROM monitored_chats ORDER BY is_active DESC, chat_title"
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

def add_new_chat(link, title, depth):
    try:
        conn = get_connection()
        cur = conn.cursor()
        if not title:
            title = link.split('/')[-1] if '/' in link else link
        
        cur.execute(
            "INSERT INTO monitored_chats (chat_link, chat_title, is_active, depth, last_scan_id) VALUES (%s, %s, TRUE, %s, 0)",
            (link, title, depth)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Ошибка добавления: {e}")
        return False

def save_changes(edited_df):
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        to_delete = edited_df[edited_df['delete'] == True]
        for index, row in to_delete.iterrows():
            cur.execute("DELETE FROM monitored_chats WHERE chat_link=%s", (row['chat_link'],))
        
        to_update = edited_df[edited_df['delete'] == False]
        for index, row in to_update.iterrows():
            cur.execute(
                """
                UPDATE monitored_chats 
                SET is_active=%s, depth=%s, chat_title=%s 
                WHERE chat_link=%s
                """,
                (bool(row['is_active']), int(row['depth']), str(row['chat_title']), row['chat_link'])
            )
            
        conn.commit()
        conn.close()
        st.success(f"Сохранено! Удалено: {len(to_delete)}, Обновлено: {len(to_update)}")
        time.sleep(1)
        return True
    except Exception as e:
        st.error(f"Ошибка сохранения: {e}")
        return False

# --- ФУНКЦИИ УПРАВЛЕНИЯ ПРОЦЕССОМ ---
def get_pid_status():
    if not os.path.exists(PID_FILE): return False, "Выключено"
    try:
        with open(PID_FILE, 'r') as f:
            content = f.read().strip()
            pid = int(content.split("|")[0] if "|" in content else content)
        try:
            os.kill(pid, 0)
        except OSError:
            return False, "PID мертв (Crash)"
        return True, f"Работает (PID {pid})"
    except:
        return False, "Ошибка чтения PID"

def start_bot():
    # Очищаем старый лог перед новым запуском
    if os.path.exists(BOT_LOG_FILE):
        open(BOT_LOG_FILE, 'w').close()
        
    # Запускаем бота и перенаправляем его вывод в файл
    with open(BOT_LOG_FILE, "a") as log:
        subprocess.Popen([sys.executable, BOT_SCRIPT], cwd=BASE_DIR, stdout=log, stderr=log)
    time.sleep(2)

def stop_bot():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                content = f.read().strip()
                pid = int(content.split("|")[0] if "|" in content else content)
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
        except: pass
        if os.path.exists(PID_FILE): os.remove(PID_FILE)

# Функция для чтения последних строк лога
def read_bot_logs():
    if not os.path.exists(BOT_LOG_FILE):
        return ["Лог-файл пока пуст или не создан."]
    try:
        with open(BOT_LOG_FILE, "r") as f:
            lines = f.readlines()
            return lines[-20:] # Возвращаем последние 20 строк
    except Exception as e:
        return [f"Ошибка чтения лога: {e}"]

# --- ИНТЕРФЕЙС ---
st.title("🚀 ZGRNK Orchestrator")

# Боковая панель
with st.sidebar:
    st.header("Управление")
    is_running, status_msg = get_pid_status()
    
    st.metric("Статус Orchestrator", status_msg, delta="ON" if is_running else "OFF", delta_color="normal" if is_running else "off")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶ СТАРТ", disabled=is_running, type="primary"):
            start_bot()
            st.rerun()
    with col2:
        if st.button("⏹ СТОП", disabled=not is_running):
            stop_bot()
            st.rerun()

    st.divider()
    
    # === ПРОСМОТР ЛОГОВ (НОВОЕ) ===
    st.subheader("📋 Логи бота")
    if st.button("🔄 Обновить логи"):
        st.rerun()
    
    logs = read_bot_logs()
    st.code("".join(logs), language="text")

# Основной экран
tab1, tab2, tab3 = st.tabs(["📊 Дашборд", "⚙️ Чаты", "🛍 Market Watcher"])

with tab1:
    df = load_data()
    if not df.empty:
        total = len(df)
        leads = len(df[df['role'] == 'LEAD'])
        spam = len(df[df['role'] == 'SPAM'])
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Всего сообщений", total)
        m2.metric("🔥 ЛИДЫ", leads)
        m3.metric("🗑 СПАМ", spam)
        
        st.subheader("Лента последних событий")
        st.dataframe(
            df[['role', 'intent', 'source_chat', 'username', 'last_message', 'updated_at']],
            use_container_width=True, # Исправлено предупреждение
            column_config={
                "updated_at": st.column_config.DatetimeColumn("Время", format="HH:mm:ss"),
                "last_message": st.column_config.TextColumn("Текст", width="large")
            }
        )
    else:
        st.info("База данных пуста или недоступна.")

with tab2:
    st.subheader("Управление чатами")
    
    with st.expander("➕ Добавить новый чат", expanded=False):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            new_link = st.text_input("Ссылка или юзернейм", key="add_link", placeholder="https://t.me/durov")
        with c2:
            new_title = st.text_input("Название (необязательно)", key="add_title", placeholder="Мой рабочий чат")
            new_depth = st.number_input("Глубина поиска", min_value=1, value=500, step=100, key="add_depth")
        with c3:
            st.write("") 
            st.write("") 
            if st.button("Добавить", type="primary"):
                if new_link:
                    if add_new_chat(new_link, new_title, new_depth):
                        st.success("Чат добавлен!")
                        time.sleep(0.5)
                        st.rerun()
                else:
                    st.warning("Введите ссылку!")
    
    st.divider()

    chats_df = load_chats()
    if not chats_df.empty:
        chats_df['delete'] = False
        
        edited_df = st.data_editor(
            chats_df,
            column_config={
                "delete": st.column_config.CheckboxColumn("Удалить?", default=False),
                "is_active": st.column_config.CheckboxColumn("Вкл?"),
                "chat_link": st.column_config.TextColumn("Ссылка", disabled=True),
                "chat_title": st.column_config.TextColumn("Название", disabled=False),
                "progress": st.column_config.ProgressColumn("Прогресс", min_value=0, max_value=100),
                "depth": st.column_config.NumberColumn("Глубина", min_value=1, step=500),
            },
            use_container_width=True, # Исправлено предупреждение
            hide_index=True,
            disabled=["status_msg", "chat_link", "progress"]
        )
        
        if st.button("💾 Применить изменения"):
            if save_changes(edited_df):
                st.rerun()
    else:
        st.warning("Нет чатов в базе.")

with tab3:
    st.header("🛍 Market Watcher")
    st.info("Здесь будет интерфейс для Wildberries/Ozon.")
    if st.button("Запустить парсер Маркета"):
        subprocess.Popen([sys.executable, MARKET_SCRIPT], cwd=MARKET_DIR)
        st.success("Команда запуска отправлена!")