from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

import httpx

from supportkit.config import load_platform


def cmd_list(args) -> int:
    p = load_platform()
    for name, c in p.services.items():
        agents = c.get("agents", {})
        mix = "/".join(str(agents.get(r, "-")) for r in ("router", "answerer", "verifier"))
        store = c.get("store", "-")
        flow = c.get("flow") or c.get("kind", "-")
        print(f"{name} {c['port']} {flow} {store} {mix}")
    return 0


def cmd_names(args) -> int:
    p = load_platform()
    kind = args.group
    for name, c in p.services.items():
        store = c.get("store", "")
        docker = store in ("postgres", "redis", "qdrant")
        if kind == "all" or (kind == "lite" and not docker) or (kind == "docker" and docker):
            print(name)
    return 0


def cmd_health(args) -> int:
    c = load_platform().services[args.service]
    kind = c.get("kind", "service")
    path = {"mcp": "/mcp", "adk_app": "/list-apps"}.get(kind, "/health")
    print(f"{kind} {c['port']} {path}")
    return 0


def cmd_port(args) -> int:
    print(load_platform().services[args.service]["port"])
    return 0


def cmd_active(args) -> int:
    p = load_platform()
    print(f"{'service':<18} {'version':<8}")
    for name in p.services:
        print(f"{name:<18} {p.active_version(name):<8}")
    return 0


def show(data: Dict[str, Any], verbose: bool) -> None:
    t = data.get("trace", {})
    head = f"service={data.get('service')} version={data.get('version')}"
    if data.get("routed_by"):
        g = data.get("gateway", {})
        head += f" routed_by={data['routed_by']} via={g.get('transport')} decision_model={g.get('decision_model')}"
    print(head)
    print(
        f"route={data.get('route')} abstained={data.get('abstained')} verified={data.get('verified')} "
        f"confidence={data.get('confidence')} agreement={data.get('agreement')} "
        f"llm_calls={t.get('llm_calls')} latency_ms={t.get('latency_ms')}"
    )
    print(f"flow={t.get('flow')} agents={t.get('agents')} store={t.get('store')}")
    print(f"answer: {data.get('answer')}")
    print(f"citations: {data.get('citations')}")
    if data.get("tools_used"):
        print(f"tools_used: {data.get('tools_used')}")
    if verbose:
        for line in data.get("context", []):
            print(f"  context {line}")
        for step in t.get("steps", []):
            print(f"  step {json.dumps(step)}")


def ask_adk(p, args) -> int:
    import uuid

    c = p.services[args.service]
    base = p.url(args.service)
    app = c.get("app_name", "northwind_concierge")
    sid = uuid.uuid4().hex
    try:
        httpx.post(f"{base}/apps/{app}/users/cli/sessions/{sid}", json={}, timeout=30).raise_for_status()
        r = httpx.post(
            f"{base}/run",
            json={"app_name": app, "user_id": "cli", "session_id": sid, "new_message": {"role": "user", "parts": [{"text": args.question}]}},
            timeout=900,
        )
    except httpx.TransportError as e:
        print(f"cannot reach {base}: {e}. Start it with: ./run.sh up {args.service}")
        return 2
    if r.status_code >= 400:
        print(f"HTTP {r.status_code}: {r.text}")
        return 1
    events = r.json()
    if args.raw:
        print(json.dumps(events, indent=2))
        return 0
    print(f"service={args.service} app={app} session={sid} events={len(events)}")
    for e in events:
        for part in (e.get("content") or {}).get("parts") or []:
            if part.get("functionCall"):
                fc = part["functionCall"]
                print(f"  {e.get('author')} calls {fc.get('name')} {json.dumps(fc.get('args'))}")
            elif part.get("functionResponse") and args.verbose:
                print(f"  {e.get('author')} got {str(part['functionResponse'].get('response'))[:200]}")
            elif part.get("text"):
                print(f"answer from {e.get('author')}: {part['text']}")
    return 0


def cmd_ask(args) -> int:
    p = load_platform()
    if p.services[args.service].get("kind") == "adk_app":
        return ask_adk(p, args)
    base = p.url(args.service)
    versions: List[Optional[str]]
    if args.version == "all":
        versions = list(p.version_order)
    else:
        versions = [args.version]
    for v in versions:
        headers = {"X-Support-Version": v} if v else {}
        try:
            r = httpx.post(f"{base}/ask", json={"message": args.question}, headers=headers, timeout=600)
        except httpx.TransportError as e:
            print(f"cannot reach {base}: {e}. Start it with: ./run.sh up {args.service}")
            return 2
        if r.status_code >= 400:
            print(f"HTTP {r.status_code}: {r.text}")
            return 1
        if args.raw:
            print(json.dumps(r.json(), indent=2))
        else:
            show(r.json(), args.verbose)
        if len(versions) > 1:
            print("-" * 72)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="supportkit.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("active").set_defaults(fn=cmd_active)
    n = sub.add_parser("names")
    n.add_argument("group", choices=["all", "lite", "docker"])
    n.set_defaults(fn=cmd_names)
    h = sub.add_parser("health")
    h.add_argument("service")
    h.set_defaults(fn=cmd_health)
    pt = sub.add_parser("port")
    pt.add_argument("service")
    pt.set_defaults(fn=cmd_port)
    a = sub.add_parser("ask")
    a.add_argument("service")
    a.add_argument("question")
    a.add_argument("--version", default=None)
    a.add_argument("--raw", action="store_true")
    a.add_argument("--verbose", "-v", action="store_true")
    a.set_defaults(fn=cmd_ask)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
