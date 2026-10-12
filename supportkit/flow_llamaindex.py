import asyncio
from typing import Any, Dict

from supportkit import pipeline as P


def run_llamaindex_workflow(svc: P.ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    from llama_index.core.workflow import Event, StartEvent, StopEvent, Workflow, step

    class Routed(Event):
        pass

    class Retrieved(Event):
        pass

    class Generated(Event):
        pass

    class Voted(Event):
        pass

    class Regenerated(Event):
        pass

    class ToGate(Event):
        pass

    class SupportWorkflow(Workflow):
        @step
        async def route(self, ev: StartEvent) -> Routed | ToGate:
            await asyncio.to_thread(P.step_route, svc, st)
            return Routed() if st["route"] == "answer" else ToGate()

        @step
        async def retrieve(self, ev: Routed) -> Retrieved:
            await asyncio.to_thread(P.step_retrieve, svc, st)
            return Retrieved()

        @step
        async def generate(self, ev: Retrieved) -> Generated:
            await asyncio.to_thread(P.step_generate, svc, st)
            return Generated()

        @step
        async def vote(self, ev: Generated) -> Voted:
            await asyncio.to_thread(P.step_vote, svc, st)
            return Voted()

        @step
        async def verify(self, ev: Voted | Regenerated) -> Regenerated | ToGate:
            await asyncio.to_thread(P.step_verify, svc, st)
            decision = P.verify_decision(st)
            if decision == "retry":
                await asyncio.to_thread(P.step_regenerate, svc, st)
                return Regenerated()
            if decision == "fail":
                await asyncio.to_thread(P.step_fail, svc, st)
            return ToGate()

        @step
        async def gate(self, ev: ToGate) -> StopEvent:
            await asyncio.to_thread(P.step_gate, svc, st)
            await asyncio.to_thread(P.finalize, svc, st)
            return StopEvent(result=st["result"])

    async def go():
        return await SupportWorkflow(timeout=900, verbose=False).run()

    asyncio.run(go())
    return st
