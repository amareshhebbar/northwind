import os
import socket
import threading
import time

import pytest

from supportkit import flows
from supportkit.config import load_platform


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def fake_ollama():
    import uvicorn

    from supportkit.fake_ollama import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    server.install_signal_handlers = lambda: None
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    old = {k: os.environ.get(k) for k in ("LLM_FORCE", "OLLAMA_HOST")}
    os.environ.pop("LLM_FORCE", None)
    os.environ["OLLAMA_HOST"] = f"http://127.0.0.1:{port}"
    load_platform(force=True)
    yield port
    server.should_exit = True
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    load_platform(force=True)


@pytest.mark.parametrize("kind", ["direct", "crewai", "strands", "adk", "pydantic_ai"])
def test_native_clients_over_ollama_protocol(fake_ollama, kind):
    from supportkit.pipeline import ServiceRuntime
    from supportkit.runtimes import make_runtime

    svc = ServiceRuntime("billing", load_platform())
    svc.seed_data()
    for role in svc.agent_kinds:
        svc.agent_kinds[role] = kind
        svc.runtimes[role] = make_runtime(kind, role)
    r = flows.execute(svc, "When is my invoice due after it is issued?", "v5")
    assert r["citations"] == ["P1"] and r["verified"] is True
    assert r["trace"]["llm_calls"] == 5


def test_adk_workflow_native(fake_ollama):
    from supportkit.pipeline import ServiceRuntime
    from supportkit.runtimes import make_runtime

    svc = ServiceRuntime("billing", load_platform())
    svc.seed_data()
    svc.cfg["flow"] = "adk_workflow"
    for role in svc.agent_kinds:
        svc.agent_kinds[role] = "adk"
        svc.runtimes[role] = make_runtime("adk", role)
    r = flows.execute(svc, "How long do I have to dispute an invoice?", "v3")
    assert r["route"] == "answer" and r["trace"]["llm_calls"] >= 3
