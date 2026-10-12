from __future__ import annotations

import argparse
import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from supportkit.mock import mock_chat
from supportkit.text import token_set

app = FastAPI(title="fake ollama for offline tests")


def _content(msg: Dict[str, Any]) -> str:
    c = msg.get("content", "")
    if isinstance(c, list):
        return "".join(p.get("text", "") for p in c if isinstance(p, dict))
    return c or ""


def _split(messages: List[Dict[str, Any]]):
    system = "\n".join(_content(m) for m in messages if m.get("role") == "system")
    users = [m for m in messages if m.get("role") == "user"]
    user = _content(users[-1]) if users else ""
    return system, user


def _tool_names(tools: Optional[List[Dict[str, Any]]]) -> List[str]:
    out = []
    for t in tools or []:
        fn = t.get("function", t)
        if fn.get("name"):
            out.append(fn["name"])
    return out


def _concierge_choice(system: str, user: str) -> Optional[str]:
    agents = re.findall(r"Agent name:\s*([A-Za-z0-9_]+)\s*\n\s*Agent description:\s*(.*)", system)
    if not agents:
        agents = [(n, d) for n, d in re.findall(r"`([a-z_]+)`:\s*(.*)", system)]
    qt = token_set(user)
    best, best_s = None, 0
    for name, desc in agents:
        s = len(qt & token_set(name.replace("_", " ") + " " + desc))
        if s > best_s:
            best, best_s = name, s
    return best


def decide(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]], temperature: float, seed: Optional[int]):
    system, user = _split(messages)
    names = _tool_names(tools)
    already_called = any(m.get("role") in ("tool", "function") or m.get("tool_calls") for m in messages)
    if "TASK: CONCIERGE" in system and names and not already_called:
        if "transfer_to_agent" in names:
            target = _concierge_choice(system, user)
            if target:
                return None, {"name": "transfer_to_agent", "arguments": {"agent_name": target}}
        if "lookup_policy" in names:
            return None, {"name": "lookup_policy", "arguments": {"query": user, "service": "billing"}}
    if "TASK: CONCIERGE" in system and already_called:
        tool_out = [_content(m) for m in messages if m.get("role") in ("tool", "function")]
        return "From our policy: " + (tool_out[-1][:300] if tool_out else "no result"), None
    return mock_chat(system, user, temperature, seed), None


@app.get("/")
def root():
    return "Ollama is running"


@app.get("/api/tags")
def tags():
    return {"models": [{"name": "fake:latest", "model": "fake:latest"}]}


@app.post("/api/show")
async def show(request: Request):
    return {"modelfile": "", "parameters": "", "template": "", "details": {"family": "fake"}, "model_info": {}, "capabilities": ["completion", "tools"]}


@app.post("/api/chat")
async def api_chat(request: Request):
    body = await request.json()
    opts = body.get("options") or {}
    text, call = decide(body.get("messages", []), body.get("tools"), float(opts.get("temperature", 0) or 0), opts.get("seed"))
    message: Dict[str, Any] = {"role": "assistant", "content": text or ""}
    if call:
        message["tool_calls"] = [{"function": {"name": call["name"], "arguments": call["arguments"]}}]
    final = {
        "model": body.get("model", "fake"),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "message": message,
        "done": True,
        "done_reason": "stop",
        "total_duration": 1000,
        "prompt_eval_count": 10,
        "eval_count": max(1, len(text or "") // 4),
    }
    if body.get("stream", True) is False:
        return JSONResponse(final)

    def gen():
        if text:
            chunk = dict(final, message={"role": "assistant", "content": text}, done=False)
            chunk.pop("done_reason", None)
            yield json.dumps(chunk) + "\n"
        last = dict(final)
        last["message"] = {"role": "assistant", "content": "", **({"tool_calls": message["tool_calls"]} if call else {})}
        yield json.dumps(last) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/api/generate")
async def api_generate(request: Request):
    body = await request.json()
    text = mock_chat(body.get("system", ""), body.get("prompt", ""), 0.0, None)
    final = {"model": body.get("model", "fake"), "response": text, "done": True, "done_reason": "stop", "prompt_eval_count": 10, "eval_count": 10}
    if body.get("stream", True) is False:
        return JSONResponse(final)
    return StreamingResponse(iter([json.dumps(final) + "\n"]), media_type="application/x-ndjson")


@app.post("/api/embeddings")
async def api_embeddings(request: Request):
    from supportkit.embed import HashEmbedder

    body = await request.json()
    return {"embedding": HashEmbedder().embed(body.get("prompt", ""))}


@app.post("/v1/chat/completions")
async def openai_chat(request: Request):
    body = await request.json()
    text, call = decide(body.get("messages", []), body.get("tools"), float(body.get("temperature", 0) or 0), body.get("seed"))
    msg: Dict[str, Any] = {"role": "assistant", "content": text}
    finish = "stop"
    if call:
        msg["content"] = None
        msg["tool_calls"] = [{"id": "call_" + uuid.uuid4().hex[:8], "type": "function", "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])}}]
        finish = "tool_calls"
    resp = {
        "id": "chatcmpl-" + uuid.uuid4().hex[:10],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "fake"),
        "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }
    if body.get("stream"):
        def gen():
            delta: Dict[str, Any] = {"role": "assistant"}
            if call:
                delta["tool_calls"] = [dict(msg["tool_calls"][0], index=0)]
            else:
                delta["content"] = text
            chunk = {"id": resp["id"], "object": "chat.completion.chunk", "created": resp["created"], "model": resp["model"], "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
            yield f"data: {json.dumps(chunk)}\n\n"
            end = {"id": resp["id"], "object": "chat.completion.chunk", "created": resp["created"], "model": resp["model"], "choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": resp["usage"]}
            yield f"data: {json.dumps(end)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")
    return JSONResponse(resp)


def main(argv=None) -> int:
    import uvicorn

    p = argparse.ArgumentParser(prog="supportkit.fake_ollama")
    p.add_argument("--port", type=int, default=11435)
    args = p.parse_args(argv)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
