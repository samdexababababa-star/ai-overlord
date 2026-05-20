"""Episodic memory: append-only log of meaningful events.

Stored in SQLite for simplicity and full-text query. Each event carries:
  - ``ts``: epoch seconds
  - ``kind``: "user_msg", "assistant_msg", "tool_call", "tool_result", "council_turn", "decision"
  - ``actor``: which agent produced it (e.g. "planner", "critic", "user")
  - ``content``: free-form text
  - ``meta``: JSON blob
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from ..config import settings
from ..log import get_logger

log = get_logger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    kind    TEXT NOT NULL,
    actor   TEXT NOT NULL,
    content TEXT NOT NULL,
    meta    TEXT NOT NULL,
    session TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_episodes_session_ts ON episodes (session, ts);
CREATE INDEX IF NOT EXISTS idx_episodes_kind ON episodes (kind);
"""


class EpisodicMemory:
    def __init__(self, path=None):
        self.path = path or settings.sqlite_path
        self._init()

    def _init(self) -> None:
        with sqlite3.connect(self.path) as c:
            c.executescript(SCHEMA)
            c.commit()

    def record(
        self,
        *,
        kind: str,
        actor: str,
        content: str,
        meta: dict[str, Any] | None = None,
        session: str = "default",
    ) -> int:
        meta_str = json.dumps(meta or {}, ensure_ascii=False, default=str)
        with sqlite3.connect(self.path) as c:
            cur = c.execute(
                "INSERT INTO episodes (ts, kind, actor, content, meta, session) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), kind, actor, content, meta_str, session),
            )
            c.commit()
            return cur.lastrowid or 0

    def recent(
        self, session: str = "default", limit: int = 50, kinds: list[str] | None = None
    ) -> list[dict[str, Any]]:
        q = "SELECT id, ts, kind, actor, content, meta FROM episodes WHERE session = ?"
        params: list = [session]
        if kinds:
            q += " AND kind IN (" + ",".join("?" * len(kinds)) + ")"
            params.extend(kinds)
        q += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.path) as c:
            rows = c.execute(q, params).fetchall()
        out = []
        for row in reversed(rows):
            try:
                meta = json.loads(row[5])
            except Exception:
                meta = {}
            out.append(
                {
                    "id": row[0],
                    "ts": row[1],
                    "kind": row[2],
                    "actor": row[3],
                    "content": row[4],
                    "meta": meta,
                }
            )
        return out

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        like = f"%{query}%"
        with sqlite3.connect(self.path) as c:
            rows = c.execute(
                "SELECT id, ts, kind, actor, content, meta FROM episodes "
                "WHERE content LIKE ? ORDER BY ts DESC LIMIT ?",
                (like, limit),
            ).fetchall()
        return [
            {"id": r[0], "ts": r[1], "kind": r[2], "actor": r[3], "content": r[4]}
            for r in rows
        ]
