import psycopg2
import time
import sys
import os
import re
from openai import OpenAI

# --- ПОДКЛЮЧЕНИЕ CONFIG ---
try:
    import config
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config
# --------------------------

def clean_text(text):
    return re.sub(r'[^\w\s.,!?-]', '', text)[:1000]

def analyze_role(text, client):
    # Логика анализа через AI
    if not text or len(text) < 5: return "MIMO", "Short/Empty"
    
    system_prompt = """
    Ты — классификатор сообщений. Твоя цель — найти ЛИДЫ (покупка/продажа).
    Формат ответа: РОЛЬ | ОПИСАНИЕ
    Роли: LEAD, SPAM, EXPERT, MIMO.
    Пример: LEAD | Ищет разработчика
    """
    try:
        resp = client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.0
        )
        content = resp.choices[0].message.content
        if "|" in content:
            parts = content.split("|", 1)
            return parts[0].strip().upper(), parts[1].strip()
        return "MIMO", content[:50]
    except Exception as e:
        print(f"AI Error: {e}")
        return "MIMO", "Error"

def reanalyze_leads():
    print("♻️ Запуск Re-Analyzer...")
    
    # 1. Подключение
    try:
        conn = psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            database=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASS
        )
        conn.autocommit = True
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        return

    # 2. Клиент AI
    client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    cur = conn.cursor()
    # Берем тех, кто MIMO, чтобы дать им второй шанс
    cur.execute("SELECT user_id, last_message FROM leads WHERE role = 'MIMO' LIMIT 50")
    rows = cur.fetchall()
    
    print(f"Найдено {len(rows)} записей для проверки.")
    
    for row in rows:
        uid, text = row
        if not text: continue
        
        print(f"Checking {uid}...", end="")
        role, intent = analyze_role(clean_text(text), client)
        
        if role != "MIMO":
            print(f" -> FOUND {role}! Updating...")
            cur.execute("UPDATE leads SET role=%s, intent=%s, updated_at=NOW() WHERE user_id=%s", (role, intent, uid))
        else:
            print(" -> Still MIMO")
        
        time.sleep(0.5) # Anti-flood

    conn.close()
    print("✅ Готово.")

if __name__ == "__main__":
    reanalyze_leads()