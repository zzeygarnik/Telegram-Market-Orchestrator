#!/bin/bash

python3 watcher.py &

# 2. Запускаем Дашборд (новое имя!)
streamlit run dashboard.py --server.port=8501 --server.address=0.0.0.0