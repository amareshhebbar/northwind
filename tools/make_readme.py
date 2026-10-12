import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from domains import CONCIERGE, D, GATEWAY, TOOLS

rows = ["| service | port | use case | flow | database | router / answerer / verifier | tools |", "|---|---|---|---|---|---|---|"]
rows.append(f"| gateway | {GATEWAY['port']} | decision AI front door, calls specialists over A2A | gateway | none | strands decision agent | |")
rows.append(f"| support_tools | {TOOLS['port']} | MCP server (streamable HTTP) with lookup_policy, lookup_record, escalate_to_human | MCP | every store | | |")
rows.append(f"| concierge | {CONCIERGE['port']} | Google ADK LlmAgent on the ADK api server with RemoteA2aAgent specialists and an MCP toolset | ADK | none | adk | McpToolset |")
for d in D:
    rows.append(f"| {d['id']} | {d['port']} | {d['usecase']} | {d['flow']} | {d['store']} | {' / '.join(d['agents'])} | {'MCP' if d.get('tools_via') == 'mcp' else 'store'} |")
table = "\n".join(rows)

text = f"""# Northwind support platform

Twenty two customer support APIs that use the real open source frameworks, not lookalikes: Google ADK, the official A2A SDK, MCP, LangGraph, CrewAI, Strands Agents, LlamaIndex Workflows and Pydantic AI. They use six databases, run on Ollama by default, and switch to Claude or OpenAI with one line. Every specialist ships in five quality versions so real GitGrounded commands can measure the difference.

Each specialist works the same way: a router agent decides, a policy retrieval step answers with citations, a verifier agent checks the answer, and hallucination controls switch on version by version.

## What talks to what

```
customer  =HTTP=>  gateway :9100  =A2A (a2a-sdk client)=>  specialist :91xx  =>  its database
customer  =ADK api=>  concierge :9300 (Google ADK LlmAgent)
                        transfer_to_agent  =>  RemoteA2aAgent  =A2A=>  specialist :91xx
                        McpToolset  =MCP=>  support_tools :9200
specialist with tools_via mcp  =MCP=>  support_tools :9200  =>  that specialist's database
account_security, enterprise_sla, privacy_gdpr  =A2A verify skill=>  fraud, legal_compliance
```

All of it is declared in `platform.yml`: ports, flows, which framework runs each role, which model each role uses, which database, which services call MCP, and who delegates verification to whom over A2A.

## Google open source in use

* Google ADK 2.x: `LlmAgent`, `Runner`, `InMemorySessionService`, `SequentialAgent` and `LoopAgent` for the `adk_workflow` flow (session state carries the pipeline, the loop escalates out when verification passes), `LiteLlm` as the native model client, `RemoteA2aAgent` for handoff, `McpToolset` for MCP tools, and `get_fast_api_app` for the ADK api server and dev UI on port 9300.
* Official A2A SDK (`a2a-sdk`): every service runs an `AgentExecutor` behind `DefaultRequestHandler`, `InMemoryTaskStore` and the SDK's JSON RPC routes at `/a2a/`, with the agent card at `/a2a/.well-known/agent-card.json`. Protocol 1.0 and 0.3 are both accepted. The gateway and the remote verifier use the SDK client (`create_client`).

## Native model clients

| runtime | client used with a real model |
|---|---|
| direct | plain HTTP to Ollama, Anthropic or any OpenAI compatible API |
| crewai | `crewai.LLM` |
| strands | `OllamaModel`, `AnthropicModel`, `OpenAIModel` |
| adk | `LiteLlm` |
| pydantic_ai | `OpenAIChatModel` with `OllamaProvider`, or `AnthropicModel` |

Model strings look like `provider:model`. Providers: `ollama`, `anthropic`, `openai`, `groq`, `deepseek`, `openrouter`, `custom` (any OpenAI compatible endpoint). `LLM_FORCE=mock:demo` replaces every model with a scripted one, and `./run.sh fake-ollama` starts a local server that speaks the Ollama and OpenAI APIs with scripted answers, so all native clients run with no model installed.

## Versions

| version | what it adds |
|---|---|
| v1 | bare model, no controls. It answers confidently and invents policy |
| v2 | routing, retrieval from the policy store, required citations, citation checking |
| v3 | verifier agent (regenerates once, then escalates), record lookup tool |
| v4 | self consistency voting (3 samples, agreement score) |
| v5 | abstain below a confidence threshold, escalate to a human tool |

Each version has its own prompts and tool list under `prompts/vN/`, its own flags in `versions.yml`, and its own MCP tool descriptions in `prompts/vN/tools.json`.

```
./switch.sh v3
./switch.sh v5 billing refunds
./switch.sh show
./switch.sh reset
```

A request can also pick a version with the header `X-Support-Version: v4`, or with `"metadata": {{"version": "v4"}}` on an A2A message. GitGrounded targets such as `billing_v4` use the header.

## Services

{table}

Flows: `plain` is ordinary Python, `langgraph` is a LangGraph `StateGraph` with a verify and retry loop, `crewai_flow` is a CrewAI `Flow`, `adk_workflow` is ADK `SequentialAgent` plus `LoopAgent`, and `llamaindex_workflow` is a LlamaIndex `Workflow` with typed events. `a2a:fraud` means the verifier step is delegated to that service over A2A.

## Run it

```
cp .env.example .env
./test.sh setup
./ask.sh billing "When is my invoice due after it is issued?" all
./ask.sh concierge "Can I return opened earbuds?" -v
./test.sh
```

`./test.sh` with no arguments lists every section in order. Run them one by one or `./test.sh all`.

## Commands you will use

```
./run.sh up all|lite|docker|name
./run.sh status
./run.sh logs billing
./ask.sh <service> "<question>" [v1|v2|v3|v4|v5|all] [-v] [--raw]
./switch.sh v1..v5 [service ...]
gitgrounded check billing --suite billing
gitgrounded check concierge --suite concierge
gitgrounded benchmark --target billing_v1 --target billing_v5 --suite billing --context data/billing/policy.md --spec prompts/v5/answer.txt
```

`RUN_MODE=single` (the default) hosts every API on its own port inside one Python process, which keeps memory near 1 GB with every framework loaded. `RUN_MODE=multi` gives each API its own process and needs several GB. `docker compose up -d` starts Postgres, Redis and Qdrant.

## Notes

* Python 3.10 or newer runs the platform. GitGrounded itself needs Python 3.11 or newer.
* Small local models are slow when v4 and v5 make five to seven calls per question, and tool calling through ADK with a 4B model can be unreliable. Raise `LLM_TIMEOUT_S` if needed, or point `CONCIERGE_LLM` at a stronger model.
* The concierge and gitgrounded A2A targets use the active version from `./switch.sh`.
* GitGrounded caches results per target. After switching between mock and a real model run `./test.sh clean`.
* `gitgrounded history` numbers are GitGrounded run numbers, not support versions.
* Regenerate data, `platform.yml` and `gitgrounded.yml` with `python tools/gen_data.py`.
"""
Path(HERE.parent / "README.md").write_text(text, encoding="utf-8")
