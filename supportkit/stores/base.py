from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional


class StoreError(RuntimeError):
    pass


class Store:
    kind = "base"

    def __init__(self, service: str, cfg: Dict[str, Any], embedder: Any):
        self.service = service
        self.cfg = cfg
        self.embedder = embedder

    def describe(self) -> str:
        return self.kind

    def ping(self) -> None:
        return None

    def count(self) -> int:
        raise NotImplementedError

    def index(self, passages: List[Dict[str, str]]) -> None:
        raise NotImplementedError

    def search(self, query: str, k: int) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def put_records(self, records: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError


def point_id(service: str, key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{service}/{key}"))
