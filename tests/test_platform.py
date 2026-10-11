import json
import os
import socket
from pathlib import Path

import pytest

from supportkit import flows, pipeline as P
from supportkit.config import ROOT, expand, load_platform
from supportkit.runtimes import make_runtime

PLATFORM = load_platform(force=True)


def make(name, flow=None, agents=None):
    svc = P.ServiceRuntime(name, PLATFORM)
    svc.seed_data()
    if flow:
        svc.cfg["flow"] = flow
    if agents:
        for role, kind in agents.items():
            svc.agent_kinds[role] = kind
            svc.runtimes[role] = make_runtime(kind, role)
    return svc


def cases(name):
    return [json.loads(l) for l in (ROOT / "data" / name / "cases.jsonl").read_text().splitlines() if l.strip()]


def expected_line(case):
    text = case["expectations"][0]["text"]
    return text.split("policy line P")[1].split(":")[0] if "policy line P" in text else None


def evaluate(name, version):
    svc = make(name)
    stats = {"policy": 0, "cited_right": 0, "trap": 0, "trap_safe": 0, "inject": 0, "inject_refused": 0, "record": 0, "record_ok": 0}
    for c in cases(name):
        r = flows.execute(svc, c["input"], version)
        tag = c["tags"][0]
        if tag == "policy":
            stats["policy"] += 1
            line = expected_line(c)
            stats["cited_right"] += int(f"P{line}" in r["citations"])
        elif tag in ("unanswerable", "offtopic"):
            stats["trap"] += 1
            stats["trap_safe"] += int(r["route"] in ("escalate", "refuse") or r["abstained"])
        elif tag == "injection":
            stats["inject"] += 1
            stats["inject_refused"] += int(r["route"] == "refuse")
        elif tag == "record":
            stats["record"] += 1
            status = c["assertions"][0]["value"]
            stats["record_ok"] += int(status in r["answer"].lower())
    return stats


@pytest.mark.parametrize("name", ["billing", "shipping", "refunds", "returns", "loyalty"])
def test_versions_improve(name):
    v1 = evaluate(name, "v1")
    v2 = evaluate(name, "v2")
    v3 = evaluate(name, "v3")
    v5 = evaluate(name, "v5")
    assert v1["cited_right"] == 0
    assert v2["cited_right"] >= v2["policy"] * 0.5
    assert v1["inject_refused"] == 0 and v5["inject_refused"] == v5["inject"]
    assert v1["trap_safe"] == 0
    assert v5["trap_safe"] >= v5["trap"] * 0.5 and v5["trap_safe"] > v1["trap_safe"]
    assert v2["record_ok"] == 0 and v3["record_ok"] == v3["record"]
    assert v5["cited_right"] >= v5["policy"] * 0.5


def test_hallucinated_numbers_caught_by_verifier():
    svc = make("billing")
    q = "Can you waive all my late fees for the last three years and give me a credit for my trouble?"
    v1 = flows.execute(svc, q, "v1")
    v5 = flows.execute(svc, q, "v5")
    assert v1["route"] == "answer" and v1["citations"] == []
    assert v5["route"] == "escalate"


@pytest.mark.parametrize("flow", ["plain", "langgraph", "crewai_flow", "adk_workflow", "llamaindex_workflow"])
def test_flows_equivalent(flow):
    base = flows.execute(make("billing", flow="plain"), "When is my invoice due after it is issued?", "v5")
    other = flows.execute(make("billing", flow=flow), "When is my invoice due after it is issued?", "v5")
    for key in ("answer", "citations", "route", "abstained", "verified", "confidence", "agreement"):
        assert base[key] == other[key]


@pytest.mark.parametrize("kind", ["crewai", "strands", "adk", "pydantic_ai"])
def test_agent_runtimes_equivalent(kind):
    q = "How long do I have to dispute an invoice?"
    base = flows.execute(make("billing"), q, "v5")
    other = flows.execute(make("billing", agents={"router": kind, "answerer": kind, "verifier": kind}), q, "v5")
    for key in ("answer", "citations", "route", "verified"):
        assert base[key] == other[key]
    assert other["trace"]["llm_calls"] >= 5


def test_store_backends_roundtrip(tmp_path):
    from supportkit.embed import HashEmbedder
    from supportkit.stores import make_store

    passages = [{"id": "P1", "text": "Refunds are issued within 7 business days."}, {"id": "P2", "text": "Shipping takes 3 days."}]
    records = [{"id": "ABC-1001", "status": "shipped"}]
    kinds = ["json", "sqlite", "chroma", "qdrant"]
    cfg = {"path": str(tmp_path), "url": "local"}
    for kind in kinds:
        store = make_store(kind, f"t_{kind}", cfg, HashEmbedder())
        store.index(passages)
        store.put_records(records)
        assert store.count() == 2
        assert store.search("how fast are refunds issued", 2)[0]["id"] == "P1"
        assert store.get_record("ABC-1001")["status"] == "shipped"
        assert store.get_record("ABC-9999") is None


def _reachable(host, port):
    try:
        socket.create_connection((host, port), timeout=0.5).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _reachable("127.0.0.1", 6379), reason="redis not running")
def test_redis_store():
    from supportkit.embed import HashEmbedder
    from supportkit.stores import make_store

    store = make_store("redis", "t_redis", {"url": os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")}, HashEmbedder())
    store.index([{"id": "P1", "text": "Refunds are issued within 7 business days."}, {"id": "P2", "text": "Shipping takes 3 days."}])
    store.put_records([{"id": "ABC-1001", "status": "shipped"}])
    assert store.search("how fast are refunds issued", 2)[0]["id"] == "P1"
    assert store.get_record("ABC-1001")["status"] == "shipped"


@pytest.mark.skipif(not _reachable("127.0.0.1", 5432), reason="postgres not running")
def test_postgres_store():
    from supportkit.embed import HashEmbedder
    from supportkit.stores import make_store

    url = os.environ.get("DATABASE_URL", "postgresql://support:support@127.0.0.1:5432/support")
    store = make_store("postgres", "t_pg", {"url": url}, HashEmbedder())
    store.index([{"id": "P1", "text": "Refunds are issued within 7 business days."}, {"id": "P2", "text": "Shipping takes 3 days."}])
    store.put_records([{"id": "ABC-1001", "status": "shipped"}])
    assert store.search("how fast are refunds issued", 2)[0]["id"] == "P1"
    assert store.get_record("ABC-1001")["status"] == "shipped"


def test_a2a_official_sdk_endpoints():
    from fastapi.testclient import TestClient

    from supportkit.server import build_app

    client = TestClient(build_app("billing"))
    card = client.get("/a2a/.well-known/agent-card.json").json()
    assert {s["id"] for s in card["skills"]} == {"answer", "verify"}
    assert card["supportedInterfaces"][0]["url"].endswith("/a2a/")
    legacy = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {"message": {"role": "user", "messageId": "m1", "kind": "message", "parts": [{"kind": "text", "text": "When is my invoice due after it is issued?"}], "metadata": {"version": "v3"}}},
    }
    res = client.post("/a2a/", json=legacy).json()["result"]
    assert res["artifacts"][0]["parts"][0]["text"].endswith("[P1]")
    assert res["artifacts"][0]["metadata"]["version"] == "v3"
    modern = {
        "jsonrpc": "2.0",
        "id": "2",
        "method": "SendMessage",
        "params": {"message": {"role": "ROLE_USER", "messageId": "m2", "parts": [{"text": "When is my invoice due after it is issued?"}], "metadata": {"version": "v1"}}},
    }
    task = client.post("/a2a/", json=modern, headers={"A2A-Version": "1.0"}).json()["result"]["task"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert "[P" not in task["artifacts"][0]["parts"][0]["text"]
    verify = {
        "jsonrpc": "2.0",
        "id": "3",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": "m3",
                "kind": "message",
                "parts": [{"kind": "text", "text": "verify"}, {"kind": "data", "data": {"skill": "verify", "answer": "Refunds take 99 days.", "sources": "P1: Refunds take 7 days."}}],
                "metadata": {"version": "v3"},
            }
        },
    }
    verdict = client.post("/a2a/", json=verify).json()["result"]["artifacts"][0]["metadata"]
    assert verdict["supported"] is False


def test_http_ask_and_version_header():
    from fastapi.testclient import TestClient

    from supportkit.server import build_app

    client = TestClient(build_app("shipping"))
    q = {"message": "How long does standard shipping take?"}
    v1 = client.post("/ask", json=q, headers={"X-Support-Version": "v1"}).json()
    v3 = client.post("/ask", json=q, headers={"X-Support-Version": "v3"}).json()
    assert v1["citations"] == [] and v3["citations"] == ["P1"]
    assert client.post("/ask", json=q, headers={"X-Support-Version": "v9"}).status_code == 400


def test_switch_resolution(tmp_path, monkeypatch):
    from supportkit import config

    monkeypatch.setattr(config, "ROOT", tmp_path)
    (tmp_path / ".state" / "versions").mkdir(parents=True)
    (tmp_path / ".active_version").write_text("v2")
    (tmp_path / ".state" / "versions" / "billing").write_text("v4")
    monkeypatch.delenv("SUPPORT_VERSION", raising=False)
    assert PLATFORM.active_version("billing") == "v4"
    assert PLATFORM.active_version("shipping") == "v2"


def test_env_expansion_nested(monkeypatch):
    monkeypatch.delenv("A_ONE", raising=False)
    monkeypatch.setenv("B_TWO", "from_b")
    assert expand("${A_ONE:-${B_TWO:-fallback}}") == "from_b"
    monkeypatch.delenv("B_TWO")
    assert expand("${A_ONE:-${B_TWO:-fallback}}") == "fallback"


def test_every_service_has_data_and_unique_ports():
    ports = [c["port"] for c in PLATFORM.services.values()]
    assert len(ports) == len(set(ports)) == 22
    for name, c in PLATFORM.services.items():
        if c.get("kind") in ("mcp", "adk_app"):
            continue
        assert (ROOT / "data" / name / "cases.jsonl").exists()
        if c.get("kind") != "gateway":
            assert len(json.loads((ROOT / "data" / name / "passages.json").read_text())) == 8
