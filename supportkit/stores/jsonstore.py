from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from supportkit.config import ROOT
from supportkit.stores.base import Store
from supportkit.text import bm25_rank


class JsonStore(Store):
    kind = "json"

    def __init__(self, service, cfg, embedder):
        super().__init__(service, cfg, embedder)
        base = Path(cfg.get("path", ".state/json"))
        base = base if base.is_absolute() else ROOT / base
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / f"{service}.json"
        self.lock = threading.Lock()

    def describe(self) -> str:
        return f"json file {self.path}"

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"passages": [], "records": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def count(self) -> int:
        return len(self._load()["passages"])

    def index(self, passages: List[Dict[str, str]]) -> None:
        with self.lock:
            data = self._load()
            data["passages"] = passages
            self._save(data)

    def search(self, query: str, k: int) -> List[Dict[str, Any]]:
        passages = self._load()["passages"]
        scores = bm25_rank(query, [p["text"] for p in passages])
        ranked = sorted(zip(passages, scores), key=lambda x: -x[1])
        return [{"id": p["id"], "text": p["text"], "score": s} for p, s in ranked[:k] if s > 0]

    def put_records(self, records: List[Dict[str, Any]]) -> None:
        with self.lock:
            data = self._load()
            data["records"] = {r["id"]: r for r in records}
            self._save(data)

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        return self._load()["records"].get(record_id)

    def reset(self) -> None:
        if self.path.exists():
            self.path.unlink()
