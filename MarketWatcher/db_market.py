import psycopg2
from psycopg2.extras import RealDictCursor
import sys
import os
import logging

# --- ПОДКЛЮЧЕНИЕ CONFIG ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config 
# --------------------------

class DatabaseMarket:
    def __init__(self):
        self.host = config.DB_HOST
        self.port = config.DB_PORT
        self.database = config.DB_NAME
        self.user = config.DB_USER
        self.password = config.DB_PASS
        self.conn = None

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            self.conn.autocommit = True
            # logging.info("✅ [Market DB] Sync connection established")
        except Exception as e:
            logging.error(f"❌ [Market DB] Sync connection error: {e}")
            raise e

    def get_cursor(self):
        if not self.conn or self.conn.closed:
            self.connect()
        return self.conn.cursor(cursor_factory=RealDictCursor)

    def execute_query(self, query, params=None):
        try:
            cur = self.get_cursor()
            cur.execute(query, params)
            return cur
        except Exception as e:
            logging.error(f"Query Error: {e}")
            if self.conn: self.conn.rollback()
            return None

    def fetch_all(self, query, params=None):
        cur = self.execute_query(query, params)
        if cur:
            return cur.fetchall()
        return []

    def fetch_one(self, query, params=None):
        cur = self.execute_query(query, params)
        if cur:
            return cur.fetchone()
        return None

    def close(self):
        if self.conn:
            self.conn.close()