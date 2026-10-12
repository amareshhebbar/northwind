from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable, Dict, Optional

from supportkit.config import Platform


def build_card(platform: Platform, name: str):
    from a2a.types import a2a_pb2 as pb

    cfg = platform.service(name)
    base = platform.url(name)
    domain = cfg.get("domain", name)
    skills = [
        pb.AgentSkill(
            id="answer",
            name="Answer a support question",
            description=f"Answers {domain} questions grounded in the {cfg.get('company', '')} policy",
            tags=["support", name],
            examples=[f"A customer question about {domain}"],
        )
    ]
    if cfg.get("kind") != "gateway":
        skills.append(
            pb.AgentSkill(
                id="verify",
                name="Verify an answer against sources",
                description="Checks that every claim in an answer is supported by the given sources",
                tags=["verification", "hallucination-control"],
            )
        )
    return pb.AgentCard(
        name=name,
        description=f"{cfg.get('company', '')} {domain} support agent. {cfg.get('usecase', '')}",
        version="1.0.0",
        supported_interfaces=[pb.AgentInterface(url=f"{base}/a2a/", protocol_binding="JSONRPC", protocol_version="1.0")],
        capabilities=pb.AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=skills,
    )


def card_dict(card) -> Dict[str, Any]:
    from a2a.server.routes.agent_card_routes import agent_card_to_dict

    return agent_card_to_dict(card)


def make_executor(answer: Callable[[str, Optional[str]], Dict[str, Any]], verify: Optional[Callable[[str, str, Optional[str]], Dict[str, Any]]]):
    from a2a.helpers import get_data_parts, get_message_text, new_task_from_user_message, new_text_message, new_text_part
    from a2a.server.agent_execution import AgentExecutor
    from a2a.server.tasks import TaskUpdater
    from google.protobuf.json_format import MessageToDict

    class SupportAgentExecutor(AgentExecutor):
        async def execute(self, context, event_queue):
            msg = context.message
            text = get_message_text(msg)
            data: Dict[str, Any] = {}
            for part in get_data_parts(msg.parts):
                if isinstance(part, dict):
                    data.update(part)
            meta = MessageToDict(msg.metadata) if msg.HasField("metadata") else {}
            if context.metadata:
                try:
                    meta.update(dict(context.metadata))
                except Exception:
                    pass
            version = meta.get("version")
            task = context.current_task or new_task_from_user_message(msg)
            if not context.current_task:
                await event_queue.enqueue_event(task)
            updater = TaskUpdater(event_queue, task.id, task.context_id)
            try:
                if data.get("skill") == "verify" and verify is not None:
                    verdict = await asyncio.to_thread(verify, data.get("answer", ""), data.get("sources", ""), version)
                    label = "supported" if verdict.get("supported") else "not supported"
                    await updater.add_artifact([new_text_part(label)], name="verdict", metadata=verdict)
                else:
                    payload = await asyncio.to_thread(answer, text, version)
                    await updater.add_artifact([new_text_part(payload.get("answer", ""))], name="answer", metadata=payload)
                await updater.complete()
            except Exception as e:
                await updater.failed(message=new_text_message(f"{type(e).__name__}: {e}", context_id=task.context_id, task_id=task.id))

        async def cancel(self, context, event_queue):
            return None

    return SupportAgentExecutor()


def mount(app, card, executor) -> None:
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
    from a2a.server.tasks import InMemoryTaskStore
    from starlette.applications import Starlette

    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore(), agent_card=card)
    sub = Starlette(routes=create_agent_card_routes(card) + create_jsonrpc_routes(handler, rpc_url="/", enable_v0_3_compat=True))
    app.mount("/a2a", sub)


async def _send(base: str, text: str, data: Optional[Dict[str, Any]], metadata: Optional[Dict[str, Any]], timeout: float) -> Dict[str, Any]:
    import httpx
    from a2a.client import ClientConfig, create_client
    from a2a.helpers import new_data_part, new_text_part
    from a2a.types import a2a_pb2 as pb
    from google.protobuf.json_format import MessageToDict
    from google.protobuf.struct_pb2 import Struct

    async with httpx.AsyncClient(timeout=timeout) as http:
        client = await create_client(f"{base}/a2a", client_config=ClientConfig(streaming=False, httpx_client=http))
        parts = [new_text_part(text)]
        if data:
            parts.append(new_data_part(data))
        meta = Struct()
        meta.update(metadata or {})
        message = pb.Message(role=pb.ROLE_USER, message_id=uuid.uuid4().hex, parts=parts, metadata=meta)
        out: Dict[str, Any] = {"text": "", "result": {}, "state": ""}
        try:
            async for event in client.send_message(pb.SendMessageRequest(message=message)):
                ev = MessageToDict(event, preserving_proto_field_name=False)
                task = ev.get("task") or {}
                if task:
                    out["state"] = (task.get("status") or {}).get("state", "")
                    for art in task.get("artifacts", []):
                        out["text"] = "".join(p.get("text", "") for p in art.get("parts", []))
                        out["result"] = art.get("metadata", {})
                    status_msg = (task.get("status") or {}).get("message") or {}
                    if out["state"] == "TASK_STATE_FAILED":
                        out["error"] = "".join(p.get("text", "") for p in status_msg.get("parts", []))
                elif ev.get("message"):
                    out["text"] = "".join(p.get("text", "") for p in ev["message"].get("parts", []))
        finally:
            await client.close()
        return out


def _ints(o):
    if isinstance(o, float) and o.is_integer() and abs(o) < 2**53:
        return int(o)
    if isinstance(o, dict):
        return {k: _ints(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_ints(v) for v in o]
    return o


def send(base: str, text: str, data: Optional[Dict[str, Any]] = None, metadata: Optional[Dict[str, Any]] = None, timeout: float = 600) -> Dict[str, Any]:
    out = asyncio.run(_send(base, text, data, metadata, timeout))
    out["result"] = _ints(out.get("result") or {})
    if out.get("error"):
        raise RuntimeError(f"a2a task failed at {base}: {out['error']}")
    return out


def remote_verify(platform: Platform, peer: str, version: str, answer: str, sources: str) -> Dict[str, Any]:
    try:
        out = send(platform.url(peer), "verify", data={"skill": "verify", "answer": answer, "sources": sources}, metadata={"version": version})
    except Exception as e:
        return {"supported": None, "issues": [f"a2a verifier {peer} unreachable: {e}"]}
    verdict = out.get("result") or {}
    return {"supported": verdict.get("supported"), "issues": list(verdict.get("issues", []))}
