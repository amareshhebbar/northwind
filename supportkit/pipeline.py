from __future__ import annotations

import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from supportkit import llm
from supportkit.config import ROOT, Platform, load_platform
from supportkit.embed import make_embedder
from supportkit.runtimes import make_runtime
from supportkit.stores import make_store
from supportkit.text import overlap, parse_json

RECORD_ID = re.compile(r"\b[A-Z]{3}-\d{3,6}\b")

STATE_KEYS = [
    "question", "version", "v", "route", "route_reason", "passages", "records", "candidate", "candidates", "agreement",
    "verdict", "verified", "issues", "retries", "answer", "citations", "confidence", "abstained", "fallback",
    "uncited", "trace", "tools_used", "insufficient", "result",
]

ROUTE_SET = {"answer", "escalate", "refuse"}


def new_state(question: str, version_cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "question": question.strip(),
        "version": version_cfg["name"],
        "v": version_cfg,
        "route": "answer",
        "route_reason": "",
        "passages": [],
        "records": [],
        "candidate": {"answer": "", "citations": []},
        "candidates": [],
        "agreement": 1.0,
        "verdict": "skip",
        "verified": None,
        "issues": [],
        "retries": 0,
        "answer": "",
        "citations": [],
        "confidence": 0.0,
        "abstained": False,
        "fallback": "",
        "uncited": False,
        "trace": [],
        "tools_used": [],
        "insufficient": False,
        "result": {},
    }


class ServiceRuntime:
    def __init__(self, name: str, platform: Optional[Platform] = None):
        self.platform = platform or load_platform()
        self.name = name
        self.cfg = self.platform.service(name)
        self.company = self.cfg.get("company", "Acme")
        self.domain = self.cfg.get("domain", name.replace("_", " "))
        self.scope = self.cfg.get("scope", self.domain)
        self.keywords = self.cfg.get("keywords", [])
        embed_spec = (self.platform.llm.get("embeddings") or "hash")
        host = (self.platform.llm.get("providers", {}).get("ollama", {}) or {}).get("host", "http://localhost:11434")
        self.embedder = make_embedder(embed_spec, host)
        store_kind = os.environ.get("SUPPORT_FORCE_STORE") or self.cfg.get("store", "json")
        self.store = make_store(store_kind, name, self.platform.stores.get(store_kind, {}), self.embedder)
        agents = self.cfg.get("agents", {})
        self.agent_kinds = {
            "router": agents.get("router", "direct"),
            "answerer": agents.get("answerer", "direct"),
            "verifier": agents.get("verifier", "direct"),
        }
        self.runtimes = {}
        for role, kind in self.agent_kinds.items():
            self.runtimes[role] = make_runtime("direct" if kind.startswith("a2a:") else kind, role)
        llm_cfg = self.cfg["llm"]
        self.specs = {
            "router": llm_cfg.get("decision", "mock:default"),
            "answerer": llm_cfg.get("answer", "mock:default"),
            "verifier": llm_cfg.get("verifier", "mock:default"),
        }
        self.sem = threading.Semaphore(int(self.cfg.get("max_inflight", 2)))
        tools_service = next((n for n, c in self.platform.services.items() if c.get("kind") == "mcp"), None)
        self.mcp_url = f"{self.platform.url(tools_service)}/mcp" if tools_service else ""

    def call(self, role: str, system: str, user: str, temperature: float = 0.0, json_mode: bool = False, seed: Optional[int] = None) -> str:
        return self.runtimes[role].call(self.specs[role], system, user, temperature=temperature, json_mode=json_mode, seed=seed)

    def seed_data(self, force: bool = False) -> Dict[str, int]:
        import json

        data_dir = ROOT / "data" / self.name
        passages = json.loads((data_dir / "passages.json").read_text(encoding="utf-8"))
        records = json.loads((data_dir / "records.json").read_text(encoding="utf-8"))
        if force or self.store.count() != len(passages):
            self.store.index(passages)
            self.store.put_records(records)
        return {"passages": len(passages), "records": len(records)}


_prompt_cache: Dict[str, str] = {}


def load_prompt(version: str, role: str) -> str:
    key = f"{version}/{role}"
    if key not in _prompt_cache:
        _prompt_cache[key] = (ROOT / "prompts" / version / f"{role}.txt").read_text(encoding="utf-8")
    return _prompt_cache[key]


def render(template: str, svc: ServiceRuntime, extra: Optional[Dict[str, str]] = None) -> str:
    values = {
        "company": svc.company,
        "domain": svc.domain,
        "scope": svc.scope,
        "keywords": ", ".join(svc.keywords),
    }
    values.update(extra or {})
    out = template
    for k, val in values.items():
        out = out.replace("{{" + k + "}}", str(val))
    return out


def note(st: Dict[str, Any], step: str, **info: Any) -> None:
    st["trace"].append({"step": step, **info})


def step_route(svc: ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    v = st["v"]
    if not v["route"]:
        st["route"] = "answer"
        note(st, "route", skipped=True)
        return st
    system = render(load_prompt(v["name"], "route"), svc)
    user = f"Customer message: {st['question']}\n###END"
    raw = svc.call("router", system, user, json_mode=True)
    data = parse_json(raw) or {}
    route = str(data.get("route", "answer")).lower()
    st["route"] = route if route in ROUTE_SET else "answer"
    st["route_reason"] = str(data.get("reason", ""))[:200]
    note(st, "route", route=st["route"], agent=svc.agent_kinds["router"])
    return st


def step_retrieve(svc: ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    v = st["v"]
    if not v["retrieve"]:
        note(st, "retrieve", skipped=True)
        return st
    k = int(v.get("retrieval_k", 4))
    via_mcp = svc.cfg.get("tools_via") == "mcp"
    if via_mcp:
        from supportkit.mcp_client import call_tool

        hits = call_tool(svc.mcp_url, "lookup_policy", {"query": st["question"], "service": svc.name})[:k]
        st["tools_used"].append({"tool": "lookup_policy", "via": "mcp"})
    else:
        hits = svc.store.search(st["question"], k)
    passages = [
        {"id": h["id"], "text": h["text"], "score": round(float(h["score"]), 4), "support": round(overlap(st["question"], h["text"]), 3)}
        for h in hits
    ]
    records: List[Dict[str, Any]] = []
    if "lookup_record" in v.get("tools", []):
        for i, rid in enumerate(list(dict.fromkeys(RECORD_ID.findall(st["question"])))[:2], start=1):
            if via_mcp:
                rec = call_tool(svc.mcp_url, "lookup_record", {"record_id": rid, "service": svc.name})
            else:
                rec = svc.store.get_record(rid)
            if rec:
                body = ", ".join(f"{k}={val}" for k, val in rec.items() if k != "id")
                records.append({"id": f"R{i}", "text": f"Record {rid}: {body}", "score": 1.0, "support": 1.0})
                st["tools_used"].append({"tool": "lookup_record", "record_id": rid, "via": "mcp" if via_mcp else "store"})
    st["passages"] = passages + records
    st["records"] = records
    note(st, "retrieve", store=svc.store.kind, via="mcp" if via_mcp else "store", hits=[p["id"] for p in st["passages"]])
    return st


def _context_block(st: Dict[str, Any]) -> str:
    if not st["passages"]:
        return "CONTEXT:\n(none)\n"
    return "CONTEXT:\n" + "\n".join(f"{p['id']}: {p['text']}" for p in st["passages"]) + "\n"


def _parse_candidate(raw: str, st: Dict[str, Any]) -> Dict[str, Any]:
    v = st["v"]
    if not v["cite"]:
        return {"answer": raw.strip(), "citations": []}
    data = parse_json(raw)
    ids = {p["id"] for p in st["passages"]}
    if isinstance(data, dict) and "answer" in data:
        answer = str(data.get("answer", "")).strip()
        cites = data.get("citations") or []
        if isinstance(cites, str):
            cites = re.findall(r"[PR]\d+", cites)
    else:
        answer = re.sub(r"\[[PR]\d+\]", "", raw).strip()
        cites = re.findall(r"[PR]\d+", raw)
    cites = [str(c).strip("[] ") for c in cites]
    cites = [c for c in dict.fromkeys(cites) if c in ids]
    return {"answer": answer, "citations": cites}


def _generate(svc: ServiceRuntime, st: Dict[str, Any], temperature: float, seed: Optional[int], feedback: str = "") -> Dict[str, Any]:
    v = st["v"]
    system = render(load_prompt(v["name"], "answer"), svc)
    if v["cite"]:
        user = _context_block(st) + f"\nQUESTION: {st['question']}\n"
    else:
        user = f"QUESTION: {st['question']}\n"
    if feedback:
        user += f"\nYour previous answer was rejected by a fact checker: {feedback}\nAnswer again using only the context.\n"
    user += "###END"
    raw = svc.call("answerer", system, user, temperature=temperature, json_mode=bool(v["cite"]), seed=seed)
    return _parse_candidate(raw, st)


def step_generate(svc: ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    cand = _generate(svc, st, 0.0, None)
    st["candidate"] = cand
    st["candidates"] = [cand]
    note(st, "generate", agent=svc.agent_kinds["answerer"], citations=cand["citations"])
    return st


def _key(c: Dict[str, Any]):
    return (tuple(sorted(c["citations"])), tuple(sorted(re.findall(r"\d+", c["answer"]))))


def step_vote(svc: ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    v = st["v"]
    n = int(v.get("votes", 1))
    if n <= 1:
        st["agreement"] = 1.0
        note(st, "vote", skipped=True)
        return st
    cands = list(st["candidates"])
    for i in range(1, n):
        cands.append(_generate(svc, st, float(v.get("vote_temperature", 0.7)), i))
    groups: Dict[Any, List[int]] = {}
    for idx, c in enumerate(cands):
        groups.setdefault(_key(c), []).append(idx)
    best_key = max(groups, key=lambda k: (len(groups[k]), 1 if 0 in groups[k] else 0))
    winner = groups[best_key][0]
    st["candidates"] = cands
    st["candidate"] = cands[winner]
    st["agreement"] = round(len(groups[best_key]) / len(cands), 3)
    note(st, "vote", samples=len(cands), agreement=st["agreement"])
    return st


def _verify_sources(st: Dict[str, Any]) -> str:
    cited = [p for p in st["passages"] if p["id"] in st["candidate"]["citations"]]
    pool = cited or st["passages"]
    return "\n".join(f"{p['id']}: {p['text']}" for p in pool)


def run_verifier(svc: ServiceRuntime, version: str, answer: str, sources: str) -> Dict[str, Any]:
    system = render(load_prompt(version, "verify"), svc)
    user = f"SOURCES:\n{sources}\n\nANSWER: {answer}\n###END"
    raw = svc.call("verifier", system, user, json_mode=True)
    data = parse_json(raw)
    if not isinstance(data, dict) or "supported" not in data:
        return {"supported": None, "issues": ["verifier output was not valid JSON"]}
    supported = data.get("supported")
    if isinstance(supported, str):
        supported = supported.strip().lower() == "true"
    issues = data.get("issues") or []
    if not isinstance(issues, list):
        issues = [str(issues)]
    return {"supported": bool(supported), "issues": [str(i)[:200] for i in issues]}


def verify_needed(st: Dict[str, Any]) -> bool:
    return bool(st["v"]["verify"]) and st["route"] == "answer" and st["candidate"]["answer"].strip().upper() != "INSUFFICIENT"


def step_verify(svc: ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    if not verify_needed(st):
        st["verdict"] = "skip"
        return st
    kind = svc.agent_kinds["verifier"]
    sources = _verify_sources(st)
    if kind.startswith("a2a:"):
        from supportkit.a2a import remote_verify

        out = remote_verify(svc.platform, kind.split(":", 1)[1], st["version"], st["candidate"]["answer"], sources)
    else:
        out = run_verifier(svc, st["version"], st["candidate"]["answer"], sources)
    st["issues"] = out["issues"]
    if out["supported"] is True:
        st["verdict"], st["verified"] = "ok", True
    elif out["supported"] is False:
        st["verdict"], st["verified"] = "bad", False
    else:
        st["verdict"], st["verified"] = "unknown", None
    note(st, "verify", agent=kind, verdict=st["verdict"], issues=out["issues"])
    return st


def verify_decision(st: Dict[str, Any]) -> str:
    if st["verdict"] != "bad":
        return "done"
    return "retry" if st["retries"] < int(st["v"].get("verify_retries", 1)) else "fail"


def step_regenerate(svc: ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    st["retries"] += 1
    cand = _generate(svc, st, 0.0, None, feedback="; ".join(st["issues"]) or "claims not supported by the context")
    st["candidate"] = cand
    st["candidates"] = [cand]
    note(st, "regenerate", retry=st["retries"])
    return st


def step_fail(svc: ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    st["route"] = "escalate"
    st["fallback"] = "verifier_rejected"
    st["candidate"] = {"answer": "", "citations": []}
    note(st, "fallback", reason="verifier_rejected")
    return st


def step_gate(svc: ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    v = st["v"]
    cand = st["candidate"]
    insufficient = cand["answer"].strip().upper() == "INSUFFICIENT"
    st["insufficient"] = insufficient
    if st["route"] == "answer" and v["retrieve"]:
        cited = [p for p in st["passages"] if p["id"] in cand["citations"]]
        pool = cited or st["passages"][:1]
        support = max([p["support"] for p in pool], default=0.0)
        support = min(1.0, support / 0.6)
        if st["verified"] is True:
            ver = 1.0
        elif st["verified"] is False:
            ver = 0.0
        else:
            ver = 0.5
        st["confidence"] = round(0.4 * support + 0.3 * st["agreement"] + 0.3 * ver, 3)
    elif st["route"] == "answer":
        st["confidence"] = 0.5
    else:
        st["confidence"] = 1.0
    if st["route"] == "answer" and v["abstain"]:
        if insufficient or st["confidence"] < float(v.get("abstain_threshold", 0.55)):
            st["abstained"] = True
    note(st, "gate", confidence=st["confidence"], abstained=st["abstained"])
    return st


def finalize(svc: ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    route = st["route"]
    cand = st["candidate"]
    if route == "refuse":
        answer = f"I can't help with that request. If you have a question about {svc.domain}, I'm happy to help."
        citations: List[str] = []
    elif route == "escalate":
        if st["fallback"]:
            answer = "I can't confirm that from our policy, so I'm passing this to a human agent who can check it for you."
        else:
            answer = f"I want to make sure you get the right answer, so I'm passing this to a human agent on the {svc.company} {svc.domain} team."
        citations = []
    elif st["abstained"]:
        answer = "I don't have enough information in our policy to answer that confidently, so I'm escalating it to a human agent."
        citations = []
    else:
        answer = cand["answer"].strip()
        citations = list(cand["citations"])
        if st["v"]["cite"] and citations:
            answer = f"{answer} " + " ".join(f"[{c}]" for c in citations)
    context = [f"{p['id']}: {p['text']}" for p in st["passages"]]
    st["answer"], st["citations"] = answer, citations
    st["result"] = {
        "service": svc.name,
        "version": st["version"],
        "answer": answer,
        "citations": citations,
        "route": "escalate" if (st["abstained"] and route == "answer") else route,
        "abstained": st["abstained"],
        "verified": st["verified"],
        "confidence": st["confidence"],
        "agreement": st["agreement"],
        "context": context,
        "tools_used": st["tools_used"],
    }
    return st


def build_result(svc: ServiceRuntime, st: Dict[str, Any], started: float, calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    result = dict(st["result"])
    result["trace"] = {
        "steps": st["trace"],
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "llm_calls": len(calls),
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "flow": svc.cfg.get("flow", "plain"),
        "agents": svc.agent_kinds,
        "store": svc.store.describe(),
        "models": svc.specs,
    }
    return result
