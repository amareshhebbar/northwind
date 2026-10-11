from __future__ import annotations

import asyncio
import os

os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("ADK_DISABLE_TELEMETRY", "true")
os.environ.setdefault("LITELLM_LOG", "ERROR")

import logging
import time
import uuid

for _name in ("google_adk", "google.adk", "LiteLLM", "litellm", "httpx", "strands", "crewai"):
    logging.getLogger(_name).setLevel(logging.ERROR)
from typing import Any, Dict, Optional

from supportkit import llm, models


def bound_chat(calls):
    def run(*args, **kwargs):
        llm.CALLS.set(calls)
        return llm.chat(*args, **kwargs)

    return run


def is_mock(spec: str) -> bool:
    return llm.parse_spec(spec)[0] == "mock"


class Runtime:
    kind = "direct"

    def __init__(self, role: str):
        self.role = role

    def call(self, spec: str, system: str, user: str, temperature: float = 0.0, json_mode: bool = False, seed: Optional[int] = None) -> str:
        if self.kind == "direct" or is_mock(spec):
            return self.shim(spec, system, user, temperature, json_mode, seed)
        started = time.perf_counter()
        out = self.native(spec, system, user, temperature, json_mode, seed)
        calls = llm.CALLS.get()
        if calls is not None:
            provider, model = llm.parse_spec(spec)
            calls.append({"provider": provider, "model": model, "ms": round((time.perf_counter() - started) * 1000, 1), "input_tokens": 0, "output_tokens": 0, "client": self.kind})
        return llm.strip_think(out)

    def shim(self, spec, system, user, temperature, json_mode, seed) -> str:
        return llm.chat(spec, system, user, temperature=temperature, json_mode=json_mode, seed=seed)

    def native(self, spec, system, user, temperature, json_mode, seed) -> str:
        raise NotImplementedError


class DirectRuntime(Runtime):
    kind = "direct"


class CrewRuntime(Runtime):
    kind = "crewai"

    def _crew(self, system: str, user: str, model) -> str:
        from crewai import Agent, Crew, Process, Task

        agent = Agent(
            role=f"support {self.role}",
            goal=f"perform the {self.role} step exactly as instructed",
            backstory=system,
            llm=model,
            allow_delegation=False,
            verbose=False,
        )
        task = Task(description=user, expected_output="the exact format requested above", agent=agent)
        out = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False).kickoff()
        return (getattr(out, "raw", None) or str(out)).strip()

    def native(self, spec, system, user, temperature, json_mode, seed):
        return self._crew(system, user, models.crewai_llm(spec, temperature))

    def shim(self, spec, system, user, temperature, json_mode, seed):
        from crewai import BaseLLM

        chat = bound_chat(llm.CALLS.get())

        class MockCrewLLM(BaseLLM):
            def call(self, messages, tools=None, callbacks=None, available_functions=None, from_task=None, from_agent=None, response_model=None, **kw):
                if isinstance(messages, str):
                    messages = [{"role": "user", "content": messages}]
                sys_text = "\n".join(m["content"] for m in messages if m.get("role") == "system")
                usr_text = "\n".join(m["content"] for m in messages if m.get("role") != "system")
                return chat(spec, sys_text, usr_text, temperature=temperature, json_mode=json_mode, seed=seed)

            def supports_function_calling(self) -> bool:
                return False

            def supports_stop_words(self) -> bool:
                return False

            def get_context_window_size(self) -> int:
                return 8192

        return self._crew(system, user, MockCrewLLM(model=spec, temperature=temperature))


class StrandsRuntime(Runtime):
    kind = "strands"

    def native(self, spec, system, user, temperature, json_mode, seed):
        from strands import Agent

        agent = Agent(model=models.strands_model(spec, temperature), system_prompt=system, tools=[], callback_handler=None)
        return str(agent(user)).strip()

    def shim(self, spec, system, user, temperature, json_mode, seed):
        from strands import Agent
        from strands.models import Model

        chat = bound_chat(llm.CALLS.get())

        class MockStrandsModel(Model):
            def __init__(self):
                self.config: Dict[str, Any] = {"model_id": spec}

            def update_config(self, **model_config):
                self.config.update(model_config)

            def get_config(self):
                return self.config

            async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
                raise NotImplementedError("structured output is not used by this platform")
                yield

            async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
                last = messages[-1]["content"]
                text_in = "".join(b.get("text", "") for b in last if isinstance(b, dict))
                out = chat(spec, system_prompt or "", text_in, temperature=temperature, json_mode=json_mode, seed=seed)
                yield {"messageStart": {"role": "assistant"}}
                yield {"contentBlockStart": {"start": {}}}
                yield {"contentBlockDelta": {"delta": {"text": out}}}
                yield {"contentBlockStop": {}}
                yield {"messageStop": {"stopReason": "end_turn"}}
                yield {"metadata": {"usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}, "metrics": {"latencyMs": 0}}}

        agent = Agent(model=MockStrandsModel(), system_prompt=system, tools=[], callback_handler=None)
        return str(agent(user)).strip()


class AdkRuntime(Runtime):
    kind = "adk"

    async def _run(self, model, system: str, user: str, temperature: float) -> str:
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        agent = LlmAgent(
            name=f"support_{self.role}",
            model=model,
            instruction=lambda ctx: system,
            generate_content_config=types.GenerateContentConfig(temperature=temperature, max_output_tokens=700),
        )
        sessions = InMemorySessionService()
        runner = Runner(app_name="northwind_support", agent=agent, session_service=sessions)
        session = await sessions.create_session(app_name="northwind_support", user_id="customer", session_id=uuid.uuid4().hex)
        text = ""
        async for event in runner.run_async(user_id="customer", session_id=session.id, new_message=types.Content(role="user", parts=[types.Part(text=user)])):
            if event.is_final_response() and event.content and event.content.parts:
                text += "".join(p.text or "" for p in event.content.parts)
        return text.strip()

    def native(self, spec, system, user, temperature, json_mode, seed):
        return asyncio.run(self._run(models.adk_model(spec), system, user, temperature))

    def shim(self, spec, system, user, temperature, json_mode, seed):
        return asyncio.run(self._run(mock_adk_llm(spec, temperature, json_mode, seed, bound_chat(llm.CALLS.get())), system, user, temperature))


def mock_adk_llm(spec, temperature, json_mode, seed, chat):
    from google.adk.models import BaseLlm, LlmResponse
    from google.genai import types

    class MockAdkLlm(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            parts = llm_request.contents[-1].parts if llm_request.contents else []
            text_in = "".join(p.text or "" for p in parts)
            sys_in = str(getattr(llm_request.config, "system_instruction", "") or "")
            out = await asyncio.get_running_loop().run_in_executor(
                None, lambda: chat(spec, sys_in, text_in, temperature=temperature, json_mode=json_mode, seed=seed)
            )
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=out)]))

    return MockAdkLlm(model=spec)


class PydanticAiRuntime(Runtime):
    kind = "pydantic_ai"

    def native(self, spec, system, user, temperature, json_mode, seed):
        from pydantic_ai import Agent

        agent = Agent(models.pydantic_ai_model(spec), system_prompt=system, model_settings={"temperature": temperature, "max_tokens": 700})
        return str(agent.run_sync(user).output).strip()

    def shim(self, spec, system, user, temperature, json_mode, seed):
        from pydantic_ai import Agent
        from pydantic_ai.messages import ModelResponse, TextPart
        from pydantic_ai.models.function import FunctionModel

        chat = bound_chat(llm.CALLS.get())

        def respond(messages, info):
            return ModelResponse(parts=[TextPart(chat(spec, system, user, temperature=temperature, json_mode=json_mode, seed=seed))])

        agent = Agent(FunctionModel(respond), system_prompt=system)
        return str(agent.run_sync(user).output).strip()


RUNTIMES = {"direct": DirectRuntime, "crewai": CrewRuntime, "strands": StrandsRuntime, "adk": AdkRuntime, "pydantic_ai": PydanticAiRuntime}


def make_runtime(kind: str, role: str) -> Runtime:
    if kind not in RUNTIMES:
        raise ValueError(f"unknown agent runtime '{kind}'; use one of {sorted(RUNTIMES)}")
    return RUNTIMES[kind](role)
