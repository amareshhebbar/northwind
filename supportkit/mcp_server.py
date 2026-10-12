from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

from supportkit.config import ROOT, load_platform


def build(version: str, host: str = "127.0.0.1", port: int = 9200):
    from mcp.server.fastmcp import FastMCP

    platform = load_platform()
    vcfg = platform.version(version)
    defs = {t["name"]: t for t in json.loads((ROOT / "prompts" / version / "tools.json").read_text(encoding="utf-8"))}
    mcp = FastMCP(f"northwind-support-{version}", host=host, port=port, streamable_http_path="/mcp")
    runtimes: Dict[str, Any] = {}

    def store(service: str):
        if service not in runtimes:
            from supportkit.pipeline import ServiceRuntime

            svc = ServiceRuntime(service, platform)
            svc.seed_data()
            runtimes[service] = svc
        return runtimes[service].store

    def lookup_policy(query: str, service: str = "billing") -> str:
        hits = store(service).search(query, int(vcfg.get("retrieval_k", 4)))
        return json.dumps([{"id": h["id"], "text": h["text"], "score": h["score"]} for h in hits])

    def lookup_record(record_id: str, service: str = "billing") -> str:
        return json.dumps(store(service).get_record(record_id))

    def escalate_to_human(reason: str, summary: str = "", service: str = "billing") -> str:
        return json.dumps({"escalated": True, "service": service, "reason": reason, "summary": summary})

    impl = {"lookup_policy": lookup_policy, "lookup_record": lookup_record, "escalate_to_human": escalate_to_human}
    for name in vcfg.get("tools", []):
        mcp.add_tool(impl[name], name=name, description=defs[name]["description"])
    return mcp


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="supportkit.mcp_server")
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    platform = load_platform()
    if args.http:
        version = os.environ.get("MCP_TOOLS_VERSION", "v5")
        cfg = platform.services.get("support_tools", {})
        port = args.port or int(cfg.get("port", 9200))
        build(version, platform.host, port).run(transport="streamable-http")
    else:
        version = os.environ.get("SUPPORT_VERSION") or platform.active_version()
        build(version).run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
