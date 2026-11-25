"""SQLite 持久层:睡眠记录与梦境。一天一条,重复写同一天会覆盖。"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date

DDL = """
CREATE TABLE IF NOT EXISTS sleeps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL UNIQUE,
    hours REAL NOT NULL,
    quality INTEGER NOT NULL DEFAULT 3,
    dream TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def _today() -> str:
    return date.today().isoformat()


class Database:
    def __init__(self, path: str = "data/mengji.db"):
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(DDL)
            self._conn.commit()

    def log(self, hours: float, quality: int = 3, dream: str = "", note: str = "",
            day: str | None = None) -> int:
        day = day or _today()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO sleeps (day, hours, quality, dream, note, created_at) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(day) DO UPDATE SET hours=excluded.hours, quality=excluded.quality,"
                " dream=excluded.dream, note=excluded.note RETURNING id",
                (day, float(hours), int(quality), dream, note, _today()),
            )
            row = cur.fetchone()
            self._conn.commit()
            return int(row["id"])

    def get(self, day: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sleeps WHERE day=?", (day,)).fetchone()
            return dict(row) if row else None

    def list(self, limit: int = 0) -> list[dict]:
        with self._lock:
            sql = "SELECT * FROM sleeps ORDER BY day DESC"
            if limit:
                sql += f" LIMIT {int(limit)}"
            rows = self._conn.execute(sql).fetchall()
            return [dict(r) for r in rows]

    def between(self, start: str, end: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sleeps WHERE day BETWEEN ? AND ? ORDER BY day", (start, end)
            ).fetchall()
            return [dict(r) for r in rows]

    def delete(self, day: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM sleeps WHERE day=?", (day,))
            self._conn.commit()
            return cur.rowcount > 0

    def seed(self, items: list[dict]) -> int:
        count = 0
        for item in items:
            off = int(item.get("days_ago", 0))
            day = date.fromordinal(date.today().toordinal() - off).isoformat()
            self.log(item["hours"], item.get("quality", 3), item.get("dream", ""),
                     item.get("note", ""), day)
            count += 1
        return count

    def stats(self) -> dict:
        with self._lock:
            c = self._conn
            return {
                "entries": c.execute("SELECT COUNT(*) FROM sleeps").fetchone()[0],
                "dreams": c.execute("SELECT COUNT(*) FROM sleeps WHERE dream<>''").fetchone()[0],
            }

    def close(self) -> None:
        with self._lock:
            self._conn.close()
