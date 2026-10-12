from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from typing import Any, List

from supportkit.config import ROOT, load_platform


def app_for(name: str) -> Any:
    platform = load_platform()
    cfg = platform.service(name)
    kind = cfg.get("kind", "service")
    if kind == "mcp":
        from supportkit.mcp_server import build

        version = os.environ.get("MCP_TOOLS_VERSION", "v5")
        return build(version, platform.host, int(cfg["port"])).streamable_http_app()
    if kind == "adk_app":
        from google.adk.cli.fast_api import get_fast_api_app

        return get_fast_api_app(
            agents_dir=str(ROOT / "adk_apps"),
            web=True,
            a2a=False,
            host=platform.host,
            port=int(cfg["port"]),
            use_local_storage=False,
            auto_create_session=True,
        )
    from supportkit.server import build_app

    return build_app(name)


def main(argv=None) -> int:
    import uvicorn

    parser = argparse.ArgumentParser(prog="supportkit.multi")
    parser.add_argument("services", nargs="+")
    args = parser.parse_args(argv)
    platform = load_platform()
    servers: List[uvicorn.Server] = []
    threads: List[threading.Thread] = []
    for name in args.services:
        try:
            app = app_for(name)
        except Exception as e:
            print(f"{name}: failed to build: {type(e).__name__}: {e}", flush=True)
            continue
        server = uvicorn.Server(uvicorn.Config(app, host=platform.host, port=int(platform.services[name]["port"]), log_level="warning"))
        server.install_signal_handlers = lambda: None
        t = threading.Thread(target=server.run, name=name, daemon=True)
        t.start()
        servers.append(server)
        threads.append(t)
        print(f"{name}: starting on {platform.url(name)}", flush=True)

    stop = threading.Event()

    def handle(signum, frame):
        stop.set()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)
    while not stop.is_set() and any(t.is_alive() for t in threads):
        time.sleep(0.5)
    for s in servers:
        s.should_exit = True
    for t in threads:
        t.join(timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
