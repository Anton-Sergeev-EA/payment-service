import os
import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from datetime import datetime
import json

class Database:
    def __init__(self, db_path: str = None):
        # Раньше путь был жёстко зашит как "/data/payments.db" — работало
        # только внутри Docker-контейнера с примонтированным /data, и
        # ломало любой локальный запуск (включая тесты) на машине без
        # каталога /data в корне файловой системы. Теперь путь можно
        # переопределить через DATABASE_PATH (см. .env.example), а
        # дефолт остаётся прежним для обратной совместимости с
        # docker-compose.yml.
        self.db_path = db_path or os.getenv("DATABASE_PATH", "/data/payments.db")
        self._init_db()

    def _init_db(self):
        """Initialize database schema synchronously."""
        import sqlite3
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider_payment_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS receipts (
                    provider_payment_id TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL,
                    result TEXT NOT NULL,
                    message TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_receipts (
                    operation_id TEXT PRIMARY KEY,
                    provider_payment_id TEXT NOT NULL,
                    result TEXT NOT NULL,
                    FOREIGN KEY (operation_id) REFERENCES operations(operation_id)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        # timeout=30 (default is 5s): each concurrent request opens its own
        # SQLite connection, and BEGIN IMMEDIATE serializes them at the
        # whole-database level (SQLite has no row-level locking). Under
        # genuinely high concurrency (the test suite's own
        # test_race_condition_submit fires 100 simultaneous requests at one
        # operation_id) the default 5s busy-timeout can be exceeded purely
        # from OS thread-scheduling contention across that many connections
        # queueing for the same write lock — not a deadlock, just slower
        # than 5s to get through the queue. 30s gives enough headroom for
        # that without masking a genuine deadlock (which would hang
        # regardless of timeout length).
        async with aiosqlite.connect(self.db_path, timeout=30) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

db = Database()
