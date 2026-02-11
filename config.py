import os
import sys
from dotenv import load_dotenv

# Загружаем переменные из .env файла (если он есть)
load_dotenv()

def get_env(key, default=None, required=False):
    value = os.getenv(key, default)
    if required and not value:
        print(f"❌ CRITICAL ERROR: Variable {key} is missing in .env!")
        sys.exit(1)
    return value

# --- БАЗА ДАННЫХ ---
DB_HOST = get_env("DB_HOST", required=True)
DB_PORT = get_env("DB_PORT", "5432")
DB_NAME = get_env("DB_NAME", "postgres")
DB_USER = get_env("DB_USER", "postgres")
DB_PASS = get_env("DB_PASS", required=True)

# --- TELEGRAM API ---
API_ID = get_env("API_ID", required=True)
API_HASH = get_env("API_HASH", required=True)
SESSION_STRING = get_env("SESSION_STRING", required=True)

# --- AI & SETTINGS ---
DEEPSEEK_API_KEY = get_env("DEEPSEEK_API_KEY", "")
MODEL_NAME = get_env("MODEL_NAME", "deepseek-chat")
HISTORY_DEPTH = int(get_env("HISTORY_DEPTH", 200))

SOURCE_CHANNEL = -1001691898040