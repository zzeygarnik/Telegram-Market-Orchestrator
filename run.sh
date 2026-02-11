#!/bin/bash
cd /app
pip install --no-cache-dir -r requirements.txt
streamlit run Web_Dashboard.py --server.port=8501 --server.address=0.0.0.0
