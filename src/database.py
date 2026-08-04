import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from datetime import datetime
import json

class Database:
    def __init__(self, db_path: str = "/data/payments.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema synchronously."""
        import sqlite3
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
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

db = Database()
