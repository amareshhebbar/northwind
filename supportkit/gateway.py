from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from supportkit import a2a, llm
from supportkit.config import ROOT, Platform
from supportkit.runtimes import make_runtime
from supportkit.text import parse_json, token_set


def cfg_targets(platform: Platform, cfg: Dict[str, Any]) -> List[str]:
    listed = cfg.get("routes_to")
    if listed:
        return list(listed)
    return [s for s, c in platform.services.items() if c.get("kind", "service") == "service"]


class GatewayRuntime:
    def __init__(self, name: str, platform: Platform):
        self.name = name
        self.platform = platform
        self.cfg = platform.service(name)
        self.targets: List[str] = cfg_targets(platform, self.cfg)
        self.transport = self.cfg.get("transport", "a2a")
        kind = (self.cfg.get("agents") or {}).get("router", "direct")
        self.runtime = make_runtime(kind, "router")
        self.kind = kind
        self.spec = self.cfg["llm"].get("decision", "mock:default")

    def keyword_route(self, question: str) -> str:
        qt = token_set(question)
        best, best_score = self.targets[0], -1.0
        for t in self.targets:
            c = self.platform.services[t]
            words = token_set(" ".join(c.get("keywords", [])) + " " + t.replace("_", " "))
            score = len(qt & words)
            if score > best_score:
                best, best_score = t, score
        return best

    def llm_route(self, question: str) -> Optional[str]:
        template = (ROOT / "prompts" / "gateway.txt").read_text(encoding="utf-8")
        listing = "\n".join(
            f"- {t}: {self.platform.services[t].get('usecase', '')} Keywords: {', '.join(self.platform.services[t].get('keywords', []))}"
            for t in self.targets
        )
        system = template.replace("{{services}}", listing)
        user = f"Customer message: {question}\n###END"
        raw = self.runtime.call(self.spec, system, user, json_mode=True)
        data = parse_json(raw) or {}
        choice = str(data.get("service", "")).strip().lower()
        if choice in self.targets:
            return choice
        for t in self.targets:
            if re.search(rf"\b{re.escape(t)}\b", raw.lower()):
                return t
        return None

    def ask(self, question: str, version: str) -> Dict[str, Any]:
        calls = llm.begin_calls()
        started = time.perf_counter()
        vcfg = self.platform.version(version)
        mode = "keyword"
        target: Optional[str] = None
        if vcfg.get("gateway") == "llm":
            target = self.llm_route(question)
            mode = "decision_ai"
        if not target:
            target = self.keyword_route(question)
        decision_ms = round((time.perf_counter() - started) * 1000, 1)
        base = self.platform.url(target)
        if self.transport == "a2a":
            result = a2a.send(base, question, metadata={"version": version})
            payload = dict(result.get("result") or {})
            if not payload:
                payload = {"answer": result.get("text", "")}
        else:
            import httpx

            r = httpx.post(f"{base}/ask", json={"message": question, "version": version}, timeout=300)
            r.raise_for_status()
            payload = r.json()
        out = dict(payload)
        out["service"] = target
        out["routed_by"] = mode
        out["gateway"] = {
            "transport": self.transport,
            "decision_ms": decision_ms,
            "decision_model": self.spec if mode == "decision_ai" else "keyword",
            "decision_agent": self.kind,
            "decision_calls": len(calls),
        }
        return out
