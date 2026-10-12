from __future__ import annotations

import argparse
import json
import sys
import threading
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request

from supportkit import __version__, a2a
from supportkit.config import ROOT, load_platform
from supportkit.stores.base import StoreError


def build_app(name: str) -> FastAPI:
    platform = load_platform()
    cfg = platform.service(name)
    app = FastAPI(title=f"support {name}", version=__version__)
    state: Dict[str, Any] = {"svc": None, "gateway": None, "error": None, "seeded": None}
    lock = threading.Lock()

    def boot() -> None:
        try:
            if cfg.get("kind") == "gateway":
                from supportkit.gateway import GatewayRuntime

                state["gateway"] = GatewayRuntime(name, platform)
            else:
                from supportkit.pipeline import ServiceRuntime

                svc = ServiceRuntime(name, platform)
                svc.store.ping()
                state["seeded"] = svc.seed_data()
                state["svc"] = svc
            state["error"] = None
        except StoreError as e:
            state["error"] = str(e)
        except Exception as e:
            state["error"] = f"{type(e).__name__}: {e}"

    boot()

    def runtime():
        if state["error"]:
            with lock:
                if state["error"]:
                    boot()
        if state["error"]:
            raise HTTPException(status_code=503, detail=state["error"])
        return state["gateway"] or state["svc"]

    def pick_version(*candidates: Optional[str]) -> str:
        chosen = next((c for c in candidates if c), None) or platform.active_version(name)
        if chosen not in platform.versions:
            raise HTTPException(status_code=400, detail=f"unknown version '{chosen}'; use one of {platform.version_order}")
        return chosen

    def answer(question: str, version: Optional[str]) -> Dict[str, Any]:
        v = pick_version(version)
        rt = runtime()
        if state["gateway"]:
            return rt.ask(question, v)
        from supportkit.flows import execute

        return execute(rt, question, v)

    def verify(answer_text: str, sources: str, version: Optional[str]) -> Dict[str, Any]:
        from supportkit.pipeline import run_verifier

        return run_verifier(runtime(), pick_version(version), answer_text, sources)

    card = a2a.build_card(platform, name)
    a2a.mount(app, card, a2a.make_executor(answer, None if cfg.get("kind") == "gateway" else verify))

    @app.get("/.well-known/agent-card.json")
    def agent_card():
        return a2a.card_dict(card)

    @app.get("/health")
    def health():
        if state["error"]:
            boot()
        return {
            "service": name,
            "ok": state["error"] is None,
            "error": state["error"],
            "active_version": platform.active_version(name),
            "seeded": state["seeded"],
        }

    @app.get("/info")
    def info():
        rt = runtime()
        base = {
            "service": name,
            "port": cfg["port"],
            "usecase": cfg.get("usecase"),
            "flow": cfg.get("flow"),
            "agents": cfg.get("agents"),
            "tools_via": cfg.get("tools_via", "store"),
            "models": cfg["llm"],
            "active_version": platform.active_version(name),
            "versions": platform.version_order,
            "a2a_card": f"{platform.url(name)}/a2a/.well-known/agent-card.json",
        }
        if state["svc"]:
            base["store"] = rt.store.describe()
        return base

    @app.post("/ask")
    async def ask(request: Request, x_support_version: Optional[str] = Header(default=None), version: Optional[str] = Query(default=None)):
        try:
            body = await request.json()
        except Exception:
            body = {}
        question = (body.get("message") or body.get("question") or "").strip()
        if not question:
            raise HTTPException(status_code=422, detail='send JSON like {"message": "your question"}')
        v = pick_version(x_support_version, version, body.get("version"))
        try:
            return await run_in_thread(answer, question, v)
        except HTTPException:
            raise
        except StoreError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    @app.post("/verify")
    async def verify_route(request: Request, x_support_version: Optional[str] = Header(default=None)):
        if cfg.get("kind") == "gateway":
            raise HTTPException(status_code=404, detail="gateway has no verifier")
        body = await request.json()
        return await run_in_thread(verify, body.get("answer", ""), body.get("sources", ""), x_support_version or body.get("version"))

    @app.get("/policy")
    def policy():
        if cfg.get("kind") == "gateway":
            raise HTTPException(status_code=404, detail="gateway has no policy")
        return json.loads((ROOT / "data" / name / "passages.json").read_text(encoding="utf-8"))

    @app.get("/records/{record_id}")
    def record(record_id: str):
        rt = runtime()
        if state["gateway"]:
            raise HTTPException(status_code=404, detail="gateway has no records")
        rec = rt.store.get_record(record_id)
        if not rec:
            raise HTTPException(status_code=404, detail="record not found")
        return rec

    @app.post("/admin/reindex")
    def reindex():
        rt = runtime()
        if state["gateway"]:
            raise HTTPException(status_code=404, detail="gateway has no store")
        return rt.seed_data(force=True)

    return app


async def run_in_thread(fn, *args):
    import anyio

    return await anyio.to_thread.run_sync(lambda: fn(*args))


def main(argv=None) -> int:
    import uvicorn

    parser = argparse.ArgumentParser(prog="supportkit.server")
    parser.add_argument("service")
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    platform = load_platform()
    cfg = platform.service(args.service)
    kind = cfg.get("kind", "service")
    if kind == "mcp":
        from supportkit.mcp_server import main as mcp_main

        return mcp_main(["--http", "--port", str(args.port or cfg["port"])])
    if kind == "adk_app":
        from supportkit.adk_app import main as adk_main

        return adk_main(["--port", str(args.port or cfg["port"])])
    app = build_app(args.service)
    uvicorn.run(app, host=platform.host, port=args.port or cfg["port"], log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
