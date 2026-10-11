from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TypedDict

from supportkit import llm
from supportkit import pipeline as P


def run_plain(svc: P.ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    P.step_route(svc, st)
    if st["route"] == "answer":
        P.step_retrieve(svc, st)
        P.step_generate(svc, st)
        P.step_vote(svc, st)
        P.step_verify(svc, st)
        while True:
            decision = P.verify_decision(st)
            if decision == "retry":
                P.step_regenerate(svc, st)
                P.step_verify(svc, st)
                continue
            if decision == "fail":
                P.step_fail(svc, st)
            break
    P.step_gate(svc, st)
    return P.finalize(svc, st)


def run_langgraph(svc: P.ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    from langgraph.graph import END, START, StateGraph

    State = TypedDict("State", {k: Any for k in P.STATE_KEYS}, total=False)

    def node(fn):
        def run(state):
            local = dict(state)
            fn(svc, local)
            return local

        return run

    g = StateGraph(State)
    g.add_node("route", node(P.step_route))
    g.add_node("retrieve", node(P.step_retrieve))
    g.add_node("generate", node(P.step_generate))
    g.add_node("vote", node(P.step_vote))
    g.add_node("verify", node(P.step_verify))
    g.add_node("regenerate", node(P.step_regenerate))
    g.add_node("fail", node(P.step_fail))
    g.add_node("gate", node(P.step_gate))
    g.add_node("finalize", node(P.finalize))
    g.add_edge(START, "route")
    g.add_conditional_edges("route", lambda s: "retrieve" if s["route"] == "answer" else "gate", {"retrieve": "retrieve", "gate": "gate"})
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "vote")
    g.add_edge("vote", "verify")
    g.add_conditional_edges("verify", P.verify_decision, {"done": "gate", "retry": "regenerate", "fail": "fail"})
    g.add_edge("regenerate", "verify")
    g.add_edge("fail", "gate")
    g.add_edge("gate", "finalize")
    g.add_edge("finalize", END)
    out = g.compile().invoke(st)
    st.update(out)
    return st


def run_crewai_flow(svc: P.ServiceRuntime, st: Dict[str, Any]) -> Dict[str, Any]:
    from crewai.flow.flow import Flow, listen, or_, router, start

    class SupportFlow(Flow):
        @start()
        def route(self):
            P.step_route(svc, st)
            return st["route"]

        @router(route)
        def after_route(self):
            return "answer_path" if st["route"] == "answer" else "gate_path"

        @listen("answer_path")
        def answer(self):
            P.step_retrieve(svc, st)
            P.step_generate(svc, st)
            P.step_vote(svc, st)
            P.step_verify(svc, st)
            while True:
                decision = P.verify_decision(st)
                if decision == "retry":
                    P.step_regenerate(svc, st)
                    P.step_verify(svc, st)
                    continue
                if decision == "fail":
                    P.step_fail(svc, st)
                break
            return "answered"

        @listen(or_(answer, "gate_path"))
        def gate(self):
            P.step_gate(svc, st)
            P.finalize(svc, st)
            return "done"

    try:
        flow = SupportFlow(suppress_flow_events=True)
    except TypeError:
        flow = SupportFlow()
    flow.kickoff()
    return st


def run_adk_workflow(svc, st):
    from supportkit.flow_adk import run_adk_workflow as run

    return run(svc, st)


def run_llamaindex_workflow(svc, st):
    from supportkit.flow_llamaindex import run_llamaindex_workflow as run

    return run(svc, st)


FLOWS = {
    "plain": run_plain,
    "langgraph": run_langgraph,
    "crewai_flow": run_crewai_flow,
    "adk_workflow": run_adk_workflow,
    "llamaindex_workflow": run_llamaindex_workflow,
}


def execute(svc: P.ServiceRuntime, question: str, version: str) -> Dict[str, Any]:
    vcfg = svc.platform.version(version)
    st = P.new_state(question, vcfg)
    calls = llm.begin_calls()
    started = time.perf_counter()
    flow = svc.cfg.get("flow", "plain")
    if flow not in FLOWS:
        raise ValueError(f"unknown flow '{flow}'")
    with svc.sem:
        FLOWS[flow](svc, st)
    return P.build_result(svc, st, started, calls)
