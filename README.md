# 🤖 Telegram & Market Semantic Orchestrator

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Container-2496ED?logo=docker&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-336791?logo=postgresql&logoColor=white)
![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B?logo=streamlit&logoColor=white)

Automated system for monitoring Telegram chats, AI-classifying leads, and tracking product prices on Russian marketplaces (Wildberries / Ozon). Containerized and ready for self-hosted deployment on TrueNAS Scale or any Linux server.

[ 🇬🇧 English](#-english) | [ 🇷🇺 Русский](#-русский)

---

## 🇬🇧 English

### 🏗️ Architecture

Three independent components communicating through a shared PostgreSQL database:

**1. 👁️ Watcher (`watcher.py`) — Telegram Parser**
- Built with Pyrogram (MTProto user-account API)
- Scans configured Telegram chats for new messages on a continuous loop
- Classifies each message with **DeepSeek AI** into one of four roles: `LEAD`, `SPAM`, `EXPERT`, `MIMO`
- Saves qualifying leads to the database and sends instant alerts to a designated Telegram channel
- Handles FloodWait automatically; manages its own lifecycle via a PID file

**2. 🛍️ MarketWatcher (`MarketWatcher/`) — Marketplace Parser**
- Built with Playwright (async headless browser)
- Tracks product prices and availability on Ozon and Wildberries
- Uses cookie-based session injection to bypass captcha and login screens
- AI-powered price analysis via `market_ai.py`

**3. 📊 Dashboard (`dashboard.py`) — Web Control Panel**
- Built with Streamlit
- Start / stop background processes directly from the UI (PID management)
- Real-time log viewer streamed from `debug_log.txt`
- Full CRUD for the monitored chat list
- Lead statistics and activity feed

![Dashboard screenshot](https://github.com/user-attachments/assets/304346e5-0d09-42a1-8e65-8130ecc4bd14)

---

### 🗂️ Project Structure

```
Telegram-Market-Orchestrator/
├── watcher.py              # Telegram parser + AI lead classifier
├── dashboard.py            # Streamlit control panel
├── db_async.py             # Async PostgreSQL wrapper (asyncpg)
├── config.py               # Reads settings from .env via python-dotenv
├── .env                    # ⚠️ Your secrets (not in repo — see below)
├── requirements.txt
├── Dockerfile
├── run.sh                  # Shell entrypoint
└── MarketWatcher/
    ├── parser_engine.py    # Playwright scraper for WB / Ozon
    ├── ozon_api_engine.py  # Ozon API integration
    ├── market_ai.py        # AI price analysis
    ├── db_market.py        # Market-specific DB operations
    ├── db_async.py         # Async DB wrapper (module copy)
    ├── reanalyzer.py       # Re-run AI analysis on existing data
    ├── stealth_patch.py    # Playwright stealth settings
    └── fix_ratings.py      # Data correction utility
```

> ⚠️ `config.py`, `*.session`, `ozon_cookies.json`, and `wb_cookies.json` are excluded from the repository and must never be committed.

---

### 💾 Database Structure

| Table | Purpose |
|---|---|
| `monitored_chats` | Target chat links, parsing depth, scan progress, active status |
| `leads` | Classified messages: user ID, username, AI-assigned role, intent summary, source chat |

---

### ⚙️ Configuration

**Step 1 — Create a `.env` file** in the project root:
```env
DB_HOST=your_postgres_host
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASS=your_password

API_ID=123456
API_HASH=your_hash
SESSION_STRING=...

DEEPSEEK_API_KEY=your_key
MODEL_NAME=deepseek-chat
HISTORY_DEPTH=200
```

`config.py` is already in the repo — it reads from `.env` automatically. You only need to create the `.env` file itself.

**Step 2 — Generate a `SESSION_STRING`**

The watcher uses a Pyrogram string session (no `.session` file needed). Run this snippet once locally:

```python
from pyrogram import Client

with Client("temp", api_id=API_ID, api_hash=API_HASH) as app:
    print(app.export_session_string())
```

Copy the output and paste it as SESSION_STRING in your .env

**Step 3 — Marketplace cookies (required for scraping)**

To bypass captcha on Ozon and Wildberries:
1. Log in to the marketplace in your browser
2. Export cookies as JSON using an extension like [EditThisCookie](https://editthiscookie.com/)
3. Save them in the project root as `ozon_cookies.json` and `wb_cookies.json`

---

### 🚀 Deployment

**Docker (recommended):**

```bash
docker build -t orchestrator-app .

docker run -d -p 8501:8501 \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/ozon_cookies.json:/app/ozon_cookies.json \
  -v $(pwd)/wb_cookies.json:/app/wb_cookies.json \
  orchestrator-app
```

**Local run:**

```bash
pip install -r requirements.txt
playwright install chromium
streamlit run dashboard.py
```

---

### 🖥️ Usage

Open [http://localhost:8501](http://localhost:8501) in your browser.

- **Dashboard** — lead statistics and recent activity feed
- **Chats** — add Telegram channels or groups to monitor; supports `t.me/...` links and `@username` handles
- **Logs** — live output from the watcher process

---

### 📦 Tech Stack

| Component | Technology |
|---|---|
| Telegram API | [Pyrogram](https://pyrogram.org/) (MTProto) |
| Marketplace scraping | [Playwright](https://playwright.dev/python/) (async) |
| AI classification | [DeepSeek](https://platform.deepseek.com/) via OpenAI SDK |
| Database | PostgreSQL via [asyncpg](https://github.com/MagicStack/asyncpg) |
| Dashboard | [Streamlit](https://streamlit.io/) |
| Containerization | Docker |
| Hosting | TrueNAS Scale / any Linux server |

---

### 🔒 Security Notes

- Never commit `config.py` — it contains your Telegram session and API keys
- `SESSION_STRING` provides full access to your Telegram account
- Cookie files (`*.json`) may contain active marketplace sessions — treat them as secrets

---
---

## 🇷🇺 Русский

### 🏗️ Архитектура

Три независимых компонента, взаимодействующих через общую базу данных PostgreSQL:

**1. 👁️ Watcher (`watcher.py`) — Парсер Telegram**
- Написан на Pyrogram (MTProto, пользовательский аккаунт)
- Циклически обходит список отслеживаемых Telegram-чатов
- Классифицирует каждое сообщение через **DeepSeek AI** по четырём ролям: `LEAD`, `SPAM`, `EXPERT`, `MIMO`
- Сохраняет квалифицированные лиды в БД и отправляет алерты в указанный Telegram-канал
- Автоматически обрабатывает FloodWait; управляет жизненным циклом через PID-файл

**2. 🛍️ MarketWatcher (`MarketWatcher/`) — Парсер маркетплейсов**
- Написан на Playwright (async headless-браузер)
- Отслеживает цены и остатки товаров на Ozon и Wildberries
- Использует инъекцию куков для обхода капчи и авторизации
- AI-анализ цен через `market_ai.py`

**3. 📊 Dashboard (`dashboard.py`) — Веб-панель управления**
- Написан на Streamlit
- Запуск / остановка фоновых процессов прямо из интерфейса (PID-менеджмент)
- Просмотр логов в реальном времени из `debug_log.txt`
- Полный CRUD для списка отслеживаемых чатов
- Статистика по лидам и лента активности

---

### 🗂️ Структура проекта

```
Telegram-Market-Orchestrator/
├── watcher.py              # Парсер Telegram + AI-классификатор лидов
├── dashboard.py            # Панель управления Streamlit
├── db_async.py             # Асинхронная обёртка PostgreSQL (asyncpg)
├── config.py               # Читает настройки из .env
├── .env                    # ⚠️ Твои секретные данные (не должны быть в репозитории)
├── requirements.txt
├── Dockerfile
├── run.sh                  # Shell-точка входа
└── MarketWatcher/
    ├── parser_engine.py    # Playwright-скрапер для WB / Ozon
    ├── ozon_api_engine.py  # Интеграция с API Ozon
    ├── market_ai.py        # AI-анализ цен
    ├── db_market.py        # DB-операции для маркетплейсов
    ├── db_async.py         # Копия обёртки БД для модуля
    ├── reanalyzer.py       # Повторный AI-анализ существующих данных
    ├── stealth_patch.py    # Stealth-настройки Playwright
    └── fix_ratings.py      # Утилита исправления данных
```

> ⚠️ Файлы `config.py`, `*.session`, `ozon_cookies.json` и `wb_cookies.json` исключены из репозитория и никогда не должны туда попадать.

---

### 💾 Структура базы данных

| Таблица | Назначение |
|---|---|
| `monitored_chats` | Ссылки на целевые чаты, глубина парсинга, прогресс сканирования, статус |
| `leads` | Классифицированные сообщения: ID пользователя, юзернейм, роль, AI-описание интента, источник |

---

### ⚙️ Конфигурация

**Шаг 1 — Создай `.env` файл** в корне проекта:
```env
DB_HOST=your_postgres_host
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASS=your_password

API_ID=123456
API_HASH=your_hash
SESSION_STRING=...

DEEPSEEK_API_KEY=your_key
MODEL_NAME=deepseek-chat
HISTORY_DEPTH=200
```

`config.py` уже в репозитории — он читается из `.env` автоматически. Тебе только нужно создать сам файл `.env`.

**Шаг 2 — Сгенерируй `SESSION_STRING`**

Watcher использует строковую сессию Pyrogram (файл `.session` не нужен). Запусти этот снипет один раз локально:

```python
from pyrogram import Client

with Client("temp", api_id=API_ID, api_hash=API_HASH) as app:
    print(app.export_session_string())
```

Скопируй вывод и вставь как `SESSION_STRING` в `.env`.

**Шаг 3 — Куки маркетплейсов (обязательно для парсинга)**

Для обхода капчи на Ozon и Wildberries:
1. Авторизуйся на маркетплейсе в браузере
2. Экспортируй куки в JSON через расширение [EditThisCookie](https://editthiscookie.com/)
3. Сохрани файлы в корне проекта: `ozon_cookies.json` и `wb_cookies.json`

---

### 🚀 Развёртывание

**Docker (рекомендуется):**

```bash
docker build -t orchestrator-app .

docker run -d -p 8501:8501 \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/ozon_cookies.json:/app/ozon_cookies.json \
  -v $(pwd)/wb_cookies.json:/app/wb_cookies.json \
  orchestrator-app
```

**Локальный запуск:**

```bash
pip install -r requirements.txt
playwright install chromium
streamlit run dashboard.py
```

---

### 🖥️ Использование

Открой [http://localhost:8501](http://localhost:8501) в браузере.

- **Dashboard** — статистика по лидам и лента последних событий
- **Чаты** — добавление каналов и групп для мониторинга; поддерживаются ссылки `t.me/...` и юзернеймы `@name`
- **Логи** — вывод watcher-процесса в реальном времени

---

### 📦 Технологии

| Компонент | Технология |
|---|---|
| Telegram API | [Pyrogram](https://pyrogram.org/) (MTProto) |
| Парсинг маркетплейсов | [Playwright](https://playwright.dev/python/) (async) |
| AI-классификация | [DeepSeek](https://platform.deepseek.com/) через OpenAI SDK |
| База данных | PostgreSQL через [asyncpg](https://github.com/MagicStack/asyncpg) |
| Дашборд | [Streamlit](https://streamlit.io/) |
| Контейнеризация | Docker |
| Хостинг | TrueNAS Scale / любой Linux-сервер |

---

### 🔒 Безопасность

- Никогда не коммить `config.py` — там хранятся сессия Telegram и ключи API
- `SESSION_STRING` даёт полный доступ к твоему аккаунту Telegram
- Файлы куков (`*.json`) могут содержать активные сессии маркетплейсов — обращайся с ними как с секретами
