from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from supportkit.config import ROOT
from supportkit.stores.base import Store


class ChromaStore(Store):
    kind = "chroma"

    def __init__(self, service, cfg, embedder):
        super().__init__(service, cfg, embedder)
        import chromadb
        from chromadb.config import Settings

        base = Path(cfg.get("path", ".state/chroma")) / service
        base = base if base.is_absolute() else ROOT / base
        base.mkdir(parents=True, exist_ok=True)
        self.path = base
        self.client = chromadb.PersistentClient(path=str(base), settings=Settings(anonymized_telemetry=False))
        self.kb = self.client.get_or_create_collection(f"{service}_kb", metadata={"hnsw:space": "cosine"})
        self.rec = self.client.get_or_create_collection(f"{service}_rec", metadata={"hnsw:space": "cosine"})

    def describe(self) -> str:
        return f"chroma {self.path} (embedder {self.embedder.name})"

    def count(self) -> int:
        return self.kb.count()

    def index(self, passages):
        existing = self.kb.get()
        if existing["ids"]:
            self.kb.delete(ids=existing["ids"])
        if passages:
            self.kb.add(
                ids=[p["id"] for p in passages],
                documents=[p["text"] for p in passages],
                embeddings=[self.embedder.embed(p["text"]) for p in passages],
            )

    def search(self, query, k):
        n = self.kb.count()
        if not n:
            return []
        res = self.kb.query(query_embeddings=[self.embedder.embed(query)], n_results=min(k, n))
        out = []
        for pid, doc, dist in zip(res["ids"][0], res["documents"][0], res["distances"][0]):
            out.append({"id": pid, "text": doc, "score": 1.0 - float(dist)})
        return out

    def put_records(self, records):
        existing = self.rec.get()
        if existing["ids"]:
            self.rec.delete(ids=existing["ids"])
        if records:
            self.rec.add(
                ids=[r["id"] for r in records],
                documents=[json.dumps(r) for r in records],
                embeddings=[self.embedder.embed(r["id"]) for r in records],
            )

    def get_record(self, record_id):
        res = self.rec.get(ids=[record_id])
        if res["ids"]:
            return json.loads(res["documents"][0])
        return None

    def reset(self):
        for name in (f"{self.service}_kb", f"{self.service}_rec"):
            try:
                self.client.delete_collection(name)
            except Exception:
                pass
        self.kb = self.client.get_or_create_collection(f"{self.service}_kb", metadata={"hnsw:space": "cosine"})
        self.rec = self.client.get_or_create_collection(f"{self.service}_rec", metadata={"hnsw:space": "cosine"})
