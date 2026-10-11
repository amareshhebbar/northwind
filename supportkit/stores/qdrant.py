from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from supportkit.config import ROOT
from supportkit.stores.base import Store, StoreError, point_id


class QdrantStore(Store):
    kind = "qdrant"

    def __init__(self, service, cfg, embedder):
        super().__init__(service, cfg, embedder)
        from qdrant_client import QdrantClient

        url = cfg.get("url")
        self.url = url
        try:
            if url and url != "local":
                self.client = QdrantClient(url=url, timeout=30)
            else:
                base = Path(cfg.get("path", ".state/qdrant")) / service
                base = base if base.is_absolute() else ROOT / base
                base.mkdir(parents=True, exist_ok=True)
                self.client = QdrantClient(path=str(base))
        except Exception as e:
            raise StoreError(f"qdrant unreachable at {url}: {e}. Run: docker compose up -d")
        self.kb = f"{service}_kb"
        self.rec = f"{service}_rec"

    def describe(self) -> str:
        return f"qdrant {self.url or 'local'} (embedder {self.embedder.name})"

    def ping(self) -> None:
        try:
            self.client.get_collections()
        except Exception as e:
            raise StoreError(f"qdrant unreachable at {self.url}: {e}. Run: docker compose up -d")

    def _ensure(self, name: str) -> None:
        from qdrant_client.models import Distance, VectorParams

        existing = {c.name for c in self.client.get_collections().collections}
        if name not in existing:
            self.client.create_collection(name, vectors_config=VectorParams(size=self.embedder.dim, distance=Distance.COSINE))

    def count(self) -> int:
        self._ensure(self.kb)
        return self.client.count(self.kb, exact=True).count

    def index(self, passages):
        from qdrant_client.models import PointStruct

        self.reset_collection(self.kb)
        self.client.upsert(
            self.kb,
            points=[
                PointStruct(id=point_id(self.service, p["id"]), vector=self.embedder.embed(p["text"]), payload=p)
                for p in passages
            ],
        )

    def reset_collection(self, name: str) -> None:
        existing = {c.name for c in self.client.get_collections().collections}
        if name in existing:
            self.client.delete_collection(name)
        self._ensure(name)

    def search(self, query, k):
        self._ensure(self.kb)
        res = self.client.query_points(self.kb, query=self.embedder.embed(query), limit=k, with_payload=True)
        return [{"id": p.payload["id"], "text": p.payload["text"], "score": float(p.score)} for p in res.points]

    def put_records(self, records):
        from qdrant_client.models import PointStruct

        self.reset_collection(self.rec)
        if records:
            self.client.upsert(
                self.rec,
                points=[
                    PointStruct(id=point_id(self.service, r["id"]), vector=self.embedder.embed(r["id"]), payload=r)
                    for r in records
                ],
            )

    def get_record(self, record_id):
        self._ensure(self.rec)
        got = self.client.retrieve(self.rec, ids=[point_id(self.service, record_id)], with_payload=True)
        return dict(got[0].payload) if got else None

    def reset(self):
        self.reset_collection(self.kb)
        self.reset_collection(self.rec)
