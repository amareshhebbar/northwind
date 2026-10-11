from __future__ import annotations

import hashlib
import math
import os
import re
from typing import List

import httpx


class HashEmbedder:
    name = "hash"

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _features(self, text: str) -> List[str]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        feats = list(words)
        for w in words:
            padded = f"#{w}#"
            feats.extend(padded[i : i + 3] for i in range(max(1, len(padded) - 2)))
        return feats

    def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for f in self._features(text):
            h = int(hashlib.md5(f.encode()).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 20) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class OllamaEmbedder:
    def __init__(self, model: str, host: str):
        self.name = f"ollama:{model}"
        self.model = model
        self.host = host.rstrip("/")
        self.dim = len(self.embed("dimension probe"))

    def embed(self, text: str) -> List[float]:
        r = httpx.post(f"{self.host}/api/embeddings", json={"model": self.model, "prompt": text}, timeout=60)
        r.raise_for_status()
        return r.json()["embedding"]


def make_embedder(spec: str, host: str = "http://localhost:11434"):
    spec = (spec or "hash").strip()
    if spec in ("hash", "mock"):
        return HashEmbedder()
    if spec.startswith("ollama:"):
        return OllamaEmbedder(spec.split(":", 1)[1], host or os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    return HashEmbedder()
