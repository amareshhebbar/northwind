from __future__ import annotations

import asyncio
import json
from typing import Any, Dict


async def _call(url: str, tool: str, args: Dict[str, Any]) -> Any:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            text = "".join(getattr(c, "text", "") for c in result.content)
            if result.isError:
                raise RuntimeError(f"mcp tool {tool} failed: {text}")
            try:
                return json.loads(text)
            except ValueError:
                return text


def call_tool(url: str, tool: str, args: Dict[str, Any]) -> Any:
    try:
        return asyncio.run(_call(url, tool, args))
    except BaseException as e:
        inner = e
        while hasattr(inner, "exceptions") and inner.exceptions:
            inner = inner.exceptions[0]
        raise RuntimeError(f"MCP call {tool} at {url} failed: {inner}. Is support_tools running? ./run.sh up support_tools") from None


async def _list(url: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return [t.name for t in (await session.list_tools()).tools]


def list_tools(url: str):
    return asyncio.run(_list(url))
