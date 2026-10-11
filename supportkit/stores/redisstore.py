from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from supportkit.stores.base import Store, StoreError
from supportkit.text import token_set, tokens


class RedisStore(Store):
    kind = "redis"

    def __init__(self, service, cfg, embedder):
        super().__init__(service, cfg, embedder)
        import redis

        self.url = cfg.get("url")
        self.r = redis.Redis.from_url(self.url, decode_responses=True, socket_connect_timeout=5)
        self.p = f"support:{service}"

    def describe(self) -> str:
        return f"redis {self.url} (hash plus inverted index)"

    def ping(self) -> None:
        try:
            self.r.ping()
        except Exception as e:
            raise StoreError(f"redis unreachable at {self.url}: {e}. Run: docker compose up -d")

    def count(self) -> int:
        return int(self.r.hlen(f"{self.p}:passages"))

    def _wipe(self, suffixes) -> None:
        for key in self.r.scan_iter(match=f"{self.p}:*"):
            if any(key.startswith(f"{self.p}:{s}") for s in suffixes):
                self.r.delete(key)

    def index(self, passages):
        self._wipe(["passages", "tok:"])
        pipe = self.r.pipeline()
        for p in passages:
            pipe.hset(f"{self.p}:passages", p["id"], p["text"])
            for t in token_set(p["text"]):
                pipe.sadd(f"{self.p}:tok:{t}", p["id"])
        pipe.execute()

    def search(self, query, k):
        n = max(1, self.count())
        scores: Dict[str, float] = {}
        for t in set(tokens(query)):
            members = self.r.smembers(f"{self.p}:tok:{t}")
            if not members:
                continue
            w = math.log(1 + n / len(members))
            for pid in members:
                scores[pid] = scores.get(pid, 0.0) + w
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:k]
        return [{"id": pid, "text": self.r.hget(f"{self.p}:passages", pid), "score": s} for pid, s in ranked]

    def put_records(self, records):
        self._wipe(["records"])
        if records:
            self.r.hset(f"{self.p}:records", mapping={r["id"]: json.dumps(r) for r in records})

    def get_record(self, record_id):
        raw = self.r.hget(f"{self.p}:records", record_id)
        return json.loads(raw) if raw else None

    def reset(self):
        self._wipe(["passages", "tok:", "records"])
