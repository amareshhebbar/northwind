from __future__ import annotations

from typing import Any, Dict

from supportkit.stores.base import Store, StoreError


def make_store(kind: str, service: str, cfg: Dict[str, Any], embedder: Any) -> Store:
    if kind == "json":
        from supportkit.stores.jsonstore import JsonStore

        return JsonStore(service, cfg, embedder)
    if kind == "sqlite":
        from supportkit.stores.sqlite import SqliteStore

        return SqliteStore(service, cfg, embedder)
    if kind == "chroma":
        from supportkit.stores.chroma import ChromaStore

        return ChromaStore(service, cfg, embedder)
    if kind == "qdrant":
        from supportkit.stores.qdrant import QdrantStore

        return QdrantStore(service, cfg, embedder)
    if kind == "postgres":
        from supportkit.stores.postgres import PostgresStore

        return PostgresStore(service, cfg, embedder)
    if kind == "redis":
        from supportkit.stores.redisstore import RedisStore

        return RedisStore(service, cfg, embedder)
    raise StoreError(f"unknown store '{kind}'")


__all__ = ["Store", "StoreError", "make_store"]
