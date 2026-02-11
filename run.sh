#!/bin/bash

# 1. Запускаем основного Telegram-бота в фоне
python3 TheWatcher.py &

# 2. Запускаем Дашборд (он будет держать контейнер активным)
streamlit run Web_Dashboard.py --server.port=8501 --server.address=0.0.0.0