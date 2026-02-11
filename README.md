# Telegram & Market Semantic Orchestrator

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Container-2496ED?logo=docker&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-336791?logo=postgresql&logoColor=white)
![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B?logo=streamlit&logoColor=white)

Automated system for monitoring Telegram chats and analyzing marketplace data (Wildberries/Ozon).
Containerized deployment ready for TrueNAS Scale.

[ 🇬🇧 English Version ](#-english-version) | [ 🇷🇺 Русская версия ](#-русская-версия)


🇬🇧 English Version

🏗 System Architecture

The system consists of three main components that interact via a PostgreSQL database:

1.  👁️ The Watcher (Telegram Parser)
    * Built with `Pyrogram` (MTProto).
    * Supports both real-time monitoring (`OnNewMessage`) and deep history parsing.
    * FloodWait Handler: Automatically manages Telegram API rate limits.
    * Smart Filtering: Distinguishes between Leads and Spam based on internal logic.

2.  🛍️ Market Watcher
    * Built with Playwright (Async) and Python.
    * Headless browser automation for parsing product prices and availability on marketplaces.

3.  📊 Web Dashboard (Control Center)
    * Built with `Streamlit`.
    * Process Management: Start/stop background processes via GUI (PID management).
    * Observability: Displays real-time logs and system status.
    * CRUD Operations: Manage the monitored chat list directly from the interface.


![Снимок экрана 2026-02-11 060606](https://github.com/user-attachments/assets/304346e5-0d09-42a1-8e65-8130ecc4bd14)


💾 Database Structure
The project uses PostgreSQL for persistent storage:
1. monitored_chats: Stores target chat links, parsing depth, and active status.
2. leads: Stores captured messages that passed the filter, including metadata (sender, timestamp, content).

🛠 Installation & Setup
1. Clone the repository:
git clone [https://github.com/zzeygarnik/Telegram-Market-Orchestrator.git](https://github.com/zzeygarnik/Telegram-Market-Orchestrator.git)
cd Telegram-Market-Orchestrator

2. Configuration
⚠️ **Important:** Configuration files and session cookies are excluded from the repository for security reasons.

**Step A: Create `config.py`**
Create a file named `config.py` in the root directory:

```python
# config.py
DB_HOST = "your_postgres_host"
DB_NAME = "your_db_name"
DB_USER = "your_db_user"
DB_PASS = "your_db_password"
DB_PORT = "5432"

API_ID = 123456          # From my.telegram.org
API_HASH = "your_hash"   # From my.telegram.org
SESSION_STRING = "..."   # Pyrogram session string (generated via helper script)
DEEPSEEK_API_KEY = "..." # (Optional) For AI Analysis

**Step B: Marketplace Cookies (Required for Parsing) To bypass captchas and login screens on Ozon/Wildberries, you must provide valid session cookies.**

   1. Log in to the marketplace in your browser.

   2. Use an extension like EditThisCookie to export cookies as JSON.

   3. Save them in the root directory as:
      ozon_cookies.json
      wb_cookies.json


**2. Обнови раздел "Docker Deployment" (добавили проброс куков):**

```markdown
3. Docker Deployment
The project includes a Dockerfile for building the image.

# Build the image
docker build -t orchestrator-app .

# Run the container
# We mount config.py AND cookie files to persist sessions
docker run -d -p 8501:8501 \
  -v $(pwd)/config.py:/app/config.py \
  -v $(pwd)/ozon_cookies.json:/app/ozon_cookies.json \
  -v $(pwd)/wb_cookies.json:/app/wb_cookies.json \
  orchestrator-app

3. Docker Deployment
The project includes a Dockerfile for building the image.

# Build the image
docker build -t orchestrator-app .

# Run the container (ensure config.py is mounted correctly)
docker run -d -p 8501:8501 -v $(pwd)/config.py:/app/config.py orchestrator-app

🖥 Usage:
   access the dashboard via your browser at http://localhost:8501 (or your server IP).
   dashboard Tab: View statistics on collected leads and recent activity.
   chats Tab: Add new Telegram channels/groups. Supports standard links (t.me/...) and usernames (@name).
   logs: Monitor backend process output directly from the web interface.




🇷🇺 Русская версия
   🏗 Архитектура системы
   Проект представляет собой оркестратор из трех компонентов, взаимодействующих через базу данных PostgreSQL:

👁️ The Watcher (Парсер Telegram)
   Написан на Pyrogram (MTProto).
   Поддерживает мониторинг в реальном времени и глубокий парсинг истории.
   Автоматическая обработка ограничений Telegram (FloodWait).
   Фильтрация сообщений (Лиды vs Спам) и сохранение результатов в БД.

🛍️ Market Watcher
   Использует Playwright (Async) и Python.
   Headless-автоматизация браузера для сбора цен и остатков товаров с маркетплейсов.

📊 Web Dashboard (Панель управления)
   Реализована на Streamlit.
   Управление процессами: Запуск/остановка фоновых задач (PID менеджмент).
   Логи: просмотр статуса и вывода консоли в реальном времени.
   Управление чатами: Добавление и настройка отслеживаемых каналов через GUI.

💾 Структура Базы Данных
monitored_chats: Ссылки на целевые чаты, настройки глубины парсинга, статус активности.
leads: Отфильтрованные сообщения с метаданными (отправитель, время, текст).

🛠 Установка и запуск
1. Клонирование репозитория
git clone [https://github.com/zzeygarnik/Telegram-Market-Orchestrator.git](https://github.com/zzeygarnik/Telegram-Market-Orchestrator.git)
cd Telegram-Market-Orchestrator

2. Конфигурация
⚠️ **Важно:** Файлы конфигурации и куки сессий исключены из репозитория в целях безопасности.

**Шаг А: Создание `config.py`**
Создайте файл `config.py` в корне проекта:

```python
# config.py
DB_HOST = "your_postgres_host"
DB_NAME = "your_db_name"
DB_USER = "your_db_user"
DB_PASS = "your_db_password"
DB_PORT = "5432"

API_ID = 123456          # Получить на my.telegram.org
API_HASH = "your_hash"   # Получить на my.telegram.org
SESSION_STRING = "..."   # Строка сессии Pyrogram (генерируется скриптом)
DEEPSEEK_API_KEY = "..." # (Опционально) Для AI-анализа

Шаг Б: Куки для Маркетплейсов Для обхода капчи и авторизации на Ozon/Wildberries необходимы актуальные куки.
   1. Авторизуйтесь на маркетплейсе в браузере.

   2. Используйте расширение (например, EditThisCookie) для экспорта куков в JSON.

   3. Сохраните файлы в корне проекта под именами:
      ozon_cookies.json
      wb_cookies.json


**2. Обнови раздел "Развертывание в Docker":**

```markdown
3. Развертывание в Docker
Проект готов к сборке через Dockerfile.

# Сборка образа
docker build -t orchestrator-app .

# Запуск контейнера
# Пробрасываем конфиг И файлы куков внутрь контейнера
docker run -d -p 8501:8501 \
  -v $(pwd)/config.py:/app/config.py \
  -v $(pwd)/ozon_cookies.json:/app/ozon_cookies.json \
  -v $(pwd)/wb_cookies.json:/app/wb_cookies.json \
  orchestrator-app
3. Развертывание в Docker
Проект готов к сборке через Dockerfile.
# Сборка образа
docker build -t orchestrator-app .

# Запуск контейнера (убедитесь, что config.py актуализирован)
docker run -d -p 8501:8501 -v $(pwd)/config.py:/app/config.py orchestrator-app

🖥 Использование
   Дашборд доступен по адресу http://localhost:8501 (или IP вашего сервера).
   Вкладка Dashboard: Статистика по лидам и лента событий.
   Вкладка Чаты: Добавление каналов для мониторинга. Поддерживаются ссылки (t.me/...) и юзернеймы (@name).
   Логи: Просмотр логов бота прямо в интерфейсе.

Tech Stack
Python 3.10+ Pyrogram Streamlit Pandas Psycopg2 Playwright Docker TrueNAS Scale

