from __future__ import annotations

import argparse
import os
import sys
from typing import Any, List

from supportkit.config import ROOT, load_platform
from supportkit.text import token_set

APP_NAME = "northwind_concierge"

INSTRUCTION = """TASK: CONCIERGE
You are the Northwind customer support concierge built with Google ADK.
Transfer the customer to the single best specialist agent for their message using transfer_to_agent.
Only if no specialist fits, use the lookup_policy tool and answer from what it returns.
Never invent policy details.
"""


def concierge_service():
    p = load_platform()
    for name, c in p.services.items():
        if c.get("kind") == "adk_app":
            return name, p.service(name)
    raise KeyError("no service with kind adk_app in platform.yml")


def mock_concierge_llm(spec: str, specialists: List[Any]):
    from google.adk.models import BaseLlm, LlmResponse
    from google.genai import types

    descriptions = {a.name: f"{a.name.replace('_', ' ')} {a.description}" for a in specialists}

    class MockConciergeLlm(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            contents = llm_request.contents or []
            last_parts = contents[-1].parts if contents else []
            if any(getattr(p, "function_response", None) for p in last_parts):
                resp = next(p.function_response for p in last_parts if getattr(p, "function_response", None))
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=f"From our policy: {str(resp.response)[:400]}")]))
                return
            user = ""
            for c in reversed(contents):
                if c.role == "user":
                    user = "".join(p.text or "" for p in c.parts if getattr(p, "text", None))
                    if user:
                        break
            qt = token_set(user)
            best, score = None, 0
            for name, desc in descriptions.items():
                s = len(qt & token_set(desc))
                if s > score:
                    best, score = name, s
            if best:
                call = types.FunctionCall(name="transfer_to_agent", args={"agent_name": best})
            else:
                call = types.FunctionCall(name="lookup_policy", args={"query": user, "service": "billing"})
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=call)]))

    return MockConciergeLlm(model=spec)


def build_root_agent():
    from google.adk.agents import LlmAgent
    from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

    from supportkit import llm, models

    platform = load_platform()
    name, cfg = concierge_service()
    targets = cfg.get("routes_to") or [n for n, c in platform.services.items() if c.get("kind", "service") == "service"]
    specialists = [
        RemoteA2aAgent(
            name=t,
            description=platform.services[t].get("usecase", t),
            agent_card=f"{platform.url(t)}/a2a/.well-known/agent-card.json",
        )
        for t in targets
    ]
    tools: List[Any] = []
    mcp_service = next((n for n, c in platform.services.items() if c.get("kind") == "mcp"), None)
    if mcp_service:
        from google.adk.tools.mcp_tool import McpToolset
        from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

        tools.append(
            McpToolset(
                connection_params=StreamableHTTPConnectionParams(url=f"{platform.url(mcp_service)}/mcp"),
                tool_filter=["lookup_policy", "lookup_record"],
            )
        )
    spec = cfg["llm"].get("decision", "mock:default")
    model = mock_concierge_llm(spec, specialists) if llm.parse_spec(spec)[0] == "mock" else models.adk_model(spec)
    return LlmAgent(
        name=APP_NAME,
        model=model,
        description="Northwind support concierge that hands customers to specialist agents over A2A",
        instruction=INSTRUCTION,
        tools=tools,
        sub_agents=specialists,
    )


def main(argv=None) -> int:
    import uvicorn
    from google.adk.cli.fast_api import get_fast_api_app

    parser = argparse.ArgumentParser(prog="supportkit.adk_app")
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    platform = load_platform()
    name, cfg = concierge_service()
    port = args.port or int(cfg["port"])
    os.environ.setdefault("ADK_DISABLE_TELEMETRY", "true")
    app = get_fast_api_app(
        agents_dir=str(ROOT / "adk_apps"),
        web=True,
        a2a=False,
        host=platform.host,
        port=port,
        use_local_storage=False,
        auto_create_session=True,
    )
    uvicorn.run(app, host=platform.host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
