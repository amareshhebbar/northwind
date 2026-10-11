from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from supportkit.config import ROOT
from supportkit.stores.base import Store
from supportkit.text import tokens


class SqliteStore(Store):
    kind = "sqlite"

    def __init__(self, service, cfg, embedder):
        super().__init__(service, cfg, embedder)
        base = Path(cfg.get("path", ".state/sqlite"))
        base = base if base.is_absolute() else ROOT / base
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / f"{service}.db"
        self.lock = threading.Lock()
        self.fts = True
        with self._conn() as c:
            try:
                c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(pid UNINDEXED, body)")
            except sqlite3.OperationalError:
                self.fts = False
                c.execute("CREATE TABLE IF NOT EXISTS passages(pid TEXT, body TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS records(rid TEXT PRIMARY KEY, data TEXT)")

    def _conn(self):
        return sqlite3.connect(str(self.path), timeout=30)

    def describe(self) -> str:
        return f"sqlite {self.path} ({'fts5' if self.fts else 'like'})"

    def count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT count(*) FROM passages").fetchone()[0]

    def index(self, passages):
        with self.lock, self._conn() as c:
            c.execute("DELETE FROM passages")
            c.executemany("INSERT INTO passages(pid, body) VALUES (?, ?)", [(p["id"], p["text"]) for p in passages])

    def search(self, query, k):
        terms = sorted(set(tokens(query)))
        terms = [re.sub(r"[^a-z0-9]", "", t) for t in terms]
        terms = [t for t in terms if t]
        if not terms:
            return []
        with self._conn() as c:
            if self.fts:
                match = " OR ".join(f'"{t}"*' for t in terms)
                rows = c.execute(
                    "SELECT pid, body, bm25(passages) FROM passages WHERE passages MATCH ? ORDER BY bm25(passages) LIMIT ?",
                    (match, k),
                ).fetchall()
                return [{"id": r[0], "text": r[1], "score": -float(r[2])} for r in rows]
            rows = c.execute("SELECT pid, body FROM passages").fetchall()
        scored = []
        for pid, body in rows:
            hits = sum(1 for t in terms if t in body.lower())
            if hits:
                scored.append({"id": pid, "text": body, "score": float(hits)})
        return sorted(scored, key=lambda x: -x["score"])[:k]

    def put_records(self, records):
        with self.lock, self._conn() as c:
            c.execute("DELETE FROM records")
            c.executemany("INSERT INTO records(rid, data) VALUES (?, ?)", [(r["id"], json.dumps(r)) for r in records])

    def get_record(self, record_id):
        with self._conn() as c:
            row = c.execute("SELECT data FROM records WHERE rid = ?", (record_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def reset(self):
        with self.lock, self._conn() as c:
            c.execute("DELETE FROM passages")
            c.execute("DELETE FROM records")
