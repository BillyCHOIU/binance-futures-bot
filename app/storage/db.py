from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class Store:
    """SQLite 事件/成交/权益快照。"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    kind TEXT NOT NULL,
                    message TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    symbol TEXT,
                    side TEXT,
                    amount REAL,
                    price REAL,
                    info TEXT
                );
                CREATE TABLE IF NOT EXISTS equity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    equity REAL NOT NULL,
                    peak REAL NOT NULL
                );
                """
            )

    def log_event(self, kind: str, message: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO events(ts, kind, message) VALUES (?,?,?)",
                (time.time(), kind, message),
            )

    def log_trade(
        self, symbol: str, side: str, amount: float, price: float, info: str = ""
    ) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO trades(ts, symbol, side, amount, price, info) VALUES (?,?,?,?,?,?)",
                (time.time(), symbol, side, amount, price, info),
            )

    def snapshot_equity(self, equity: float, peak: float) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO equity_snapshots(ts, equity, peak) VALUES (?,?,?)",
                (time.time(), equity, peak),
            )

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT ts, kind, message FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
