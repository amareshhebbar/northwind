import asyncio
import uuid
from typing import Any, AsyncGenerator, Callable, Dict

from supportkit import pipeline as P


def run_adk_workflow(svc: P.ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    return asyncio.run(_run(svc, st))


async def _run(svc: P.ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    from google.adk.agents import BaseAgent, LoopAgent, SequentialAgent
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events import Event, EventActions
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    class StepAgent(BaseAgent):
        fn: Any = None
        only_when_answering: bool = True

        async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
            state = dict(ctx.session.state.get("support", {}))
            if not self.only_when_answering or state.get("route") == "answer":
                await asyncio.to_thread(self.fn, svc, state)
            yield Event(author=self.name, invocation_id=ctx.invocation_id, actions=EventActions(state_delta={"support": state}))

    class VerifyDecision(BaseAgent):
        async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
            state = dict(ctx.session.state.get("support", {}))
            decision = P.verify_decision(state) if state.get("route") == "answer" else "done"
            escalate = True
            if decision == "retry":
                await asyncio.to_thread(P.step_regenerate, svc, state)
                escalate = False
            elif decision == "fail":
                await asyncio.to_thread(P.step_fail, svc, state)
            yield Event(author=self.name, invocation_id=ctx.invocation_id, actions=EventActions(state_delta={"support": state}, escalate=escalate))

    retries = int(st["v"].get("verify_retries", 1))
    pipeline = SequentialAgent(
        name="support_pipeline",
        sub_agents=[
            StepAgent(name="route", fn=P.step_route, only_when_answering=False),
            StepAgent(name="retrieve", fn=P.step_retrieve),
            StepAgent(name="generate", fn=P.step_generate),
            StepAgent(name="vote", fn=P.step_vote),
            LoopAgent(
                name="verify_loop",
                max_iterations=retries + 2,
                sub_agents=[StepAgent(name="verify", fn=P.step_verify), VerifyDecision(name="verify_decision")],
            ),
            StepAgent(name="gate", fn=P.step_gate, only_when_answering=False),
            StepAgent(name="finalize", fn=P.finalize, only_when_answering=False),
        ],
    )
    sessions = InMemorySessionService()
    runner = Runner(app_name="northwind_workflow", agent=pipeline, session_service=sessions)
    session = await sessions.create_session(app_name="northwind_workflow", user_id="customer", session_id=uuid.uuid4().hex, state={"support": st})
    async for _ in runner.run_async(user_id="customer", session_id=session.id, new_message=types.Content(role="user", parts=[types.Part(text=st["question"])])):
        pass
    final = await sessions.get_session(app_name="northwind_workflow", user_id="customer", session_id=session.id)
    st.update(final.state.get("support", {}))
    return st
