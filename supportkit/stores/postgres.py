from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from supportkit.stores.base import Store, StoreError
from supportkit.text import tokens


class PostgresStore(Store):
    kind = "postgres"

    def __init__(self, service, cfg, embedder):
        super().__init__(service, cfg, embedder)
        self.url = cfg.get("url")
        self._schema()

    def describe(self) -> str:
        return f"postgres {self.url.split('@')[-1] if self.url else '?'} (full text search)"

    def _conn(self):
        import psycopg

        try:
            return psycopg.connect(self.url, autocommit=True, connect_timeout=5)
        except Exception as e:
            raise StoreError(f"postgres unreachable ({self.url.split('@')[-1]}): {e}. Run: docker compose up -d")

    def ping(self) -> None:
        with self._conn() as c:
            c.execute("SELECT 1")

    def _schema(self) -> None:
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS support_passages("
                "service text, pid text, body text, tsv tsvector, PRIMARY KEY(service, pid))"
            )
            c.execute("CREATE TABLE IF NOT EXISTS support_records(service text, rid text, data jsonb, PRIMARY KEY(service, rid))")

    def count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT count(*) FROM support_passages WHERE service = %s", (self.service,)).fetchone()[0]

    def index(self, passages):
        with self._conn() as c:
            c.execute("DELETE FROM support_passages WHERE service = %s", (self.service,))
            for p in passages:
                c.execute(
                    "INSERT INTO support_passages(service, pid, body, tsv) VALUES (%s, %s, %s, to_tsvector('english', %s))",
                    (self.service, p["id"], p["text"], p["text"]),
                )

    def search(self, query, k):
        terms = [re.sub(r"[^a-z0-9]", "", t) for t in sorted(set(tokens(query)))]
        terms = [t for t in terms if t]
        if not terms:
            return []
        tsq = " | ".join(terms)
        with self._conn() as c:
            rows = c.execute(
                "SELECT pid, body, ts_rank(tsv, to_tsquery('english', %s)) AS r FROM support_passages "
                "WHERE service = %s AND tsv @@ to_tsquery('english', %s) ORDER BY r DESC LIMIT %s",
                (tsq, self.service, tsq, k),
            ).fetchall()
        return [{"id": r[0], "text": r[1], "score": float(r[2])} for r in rows]

    def put_records(self, records):
        with self._conn() as c:
            c.execute("DELETE FROM support_records WHERE service = %s", (self.service,))
            for r in records:
                c.execute(
                    "INSERT INTO support_records(service, rid, data) VALUES (%s, %s, %s::jsonb)",
                    (self.service, r["id"], json.dumps(r)),
                )

    def get_record(self, record_id):
        with self._conn() as c:
            row = c.execute(
                "SELECT data FROM support_records WHERE service = %s AND rid = %s", (self.service, record_id)
            ).fetchone()
        if not row:
            return None
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])

    def reset(self):
        with self._conn() as c:
            c.execute("DELETE FROM support_passages WHERE service = %s", (self.service,))
            c.execute("DELETE FROM support_records WHERE service = %s", (self.service,))
