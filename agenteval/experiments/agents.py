"""Real-agent wiring, generalized past the single crypto milestone.

What "wired through" means concretely, since this is the part worth
learning from:

- An agent never sees a raw secret. It asks the broker for one
  (`broker.get_secret`), which only succeeds because the manifest grants
  this agent the `call_llm` capability on that exact secret name.
- Every tool call goes through the broker *before* the real tool in
  tools/*.py executes: `broker.use()` for a local/synthetic action,
  `broker.check_egress()` (which itself calls `.use()`) for anything that
  reaches a real network target. This is the tool-wrapper/broker
  integration that was a named TODO after Task 3.
- A tool's operator-fixed parameters (a scan target, a fetch URL) are never
  exposed to the model as callable arguments, even when the underlying
  Python function accepts them. The model decides *whether* to call a
  tool; it does not get to choose parameters nothing about its task
  requires it to control. That's a deliberate scoping decision, not an
  oversight — a capability grant should scope the safe parameter space,
  not just which function name can be invoked.
- Everything is recorded as MESSAGE/TOOL_CALL trace records in the same
  shape agenteval/dry_run.py's scripted agent uses, so a real trace
  replays against both monitors exactly like a synthetic one.

Three tools are wired: decrypt_caesar (crypto, pure Python, no network),
nmap_scan against 127.0.0.1 only (recon, local self-scan, no egress
needed), and http_get against example.com only (web — IANA's
reserved-for-testing domain, the one real network call, mediated by
EgressPolicy). This is deliberately narrow: no retry logic, no multi-tool
plans, one tool per specialist. Real agent-loop concerns (retries,
malformed tool-call JSON, chaining multiple tools) are the next
increments, not this one.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from agenteval.core.broker import CapabilityBroker
from agenteval.core.manifest import AgentSpec
from agenteval.core.substrate import SubstrateResource
from agenteval.core.trace import MESSAGE, TOOL_CALL, TraceWriter
from tools.crypto import decrypt_caesar
from tools.executor import SandboxedExecutor, ToolResult
from tools.recon import nmap_scan
from tools.web import http_get

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "agents" / "prompts"


def _load_prompt(role: str) -> str:
    path = PROMPTS_DIR / f"{role}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"You are the {role} specialist. Complete the assigned task and report findings."


@dataclass
class ToolSpec:
    name: str
    description: str
    properties: dict  # JSON-schema "properties" for model-controlled args only
    required: list[str]
    capability: str
    execute: Callable[..., ToolResult]  # called with the model's parsed args
    resource: str | None = None  # for broker.use(); ignored if egress_target is set
    egress_target: str | None = None  # if set, mediated via broker.check_egress instead


def _openai_tool_def(spec: ToolSpec) -> dict:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": {
                "type": "object", "properties": spec.properties, "required": spec.required,
            },
        },
    }


def _mediate(broker: CapabilityBroker, agent_id: str, spec: ToolSpec, tool_args: dict) -> None:
    if spec.egress_target is not None:
        broker.check_egress(agent_id, spec.capability, spec.egress_target)
    else:
        broker.use(agent_id, spec.capability, spec.resource, tool_args)


def make_openrouter_specialist(task: str, tool_spec: ToolSpec, run_id: str = "single-agent-test"):
    """Returns an AgentFn (agenteval/experiments/cohorts.py) for one real,
    tool-using OpenRouter call against the given ToolSpec. `task` and
    `tool_spec` are baked in via closure since AgentFn's signature has no
    room for them.
    """

    def agent_fn(agent: AgentSpec, broker: CapabilityBroker,
                 substrate: dict[str, SubstrateResource], trace: TraceWriter,
                 generation_id: str) -> None:
        api_key = broker.get_secret(agent.id, "call_llm", "OPENROUTER_API_KEY")
        client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

        messages = [
            {"role": "system", "content": _load_prompt(agent.id)},
            {"role": "user", "content": f"Task: {task}"},
        ]
        trace.append(MESSAGE, agent.id, {
            "sender": "orchestrator", "recipient": agent.id,
            "message_type": "TASK_ASSIGN", "content": {"task": task}, "run_id": run_id,
        })

        completion = client.chat.completions.create(
            model=agent.model, max_tokens=agent.token_budget,
            messages=messages, tools=[_openai_tool_def(tool_spec)],
        )
        usage = completion.usage
        broker.spend_tokens(agent.id, (usage.prompt_tokens or 0) + (usage.completion_tokens or 0))

        reply = completion.choices[0].message
        tool_calls = reply.tool_calls or []

        if tool_calls:
            messages.append(reply.model_dump(exclude_none=True))
            for call in tool_calls:
                tool_args = json.loads(call.function.arguments or "{}")
                _mediate(broker, agent.id, tool_spec, tool_args)
                result = tool_spec.execute(**tool_args)
                trace.append(TOOL_CALL, agent.id, {
                    "tool_name": tool_spec.name, "args": result.args,
                    "claimed_hash": result.execution_hash, "actual_output": result.output,
                })
                messages.append({
                    "role": "tool", "tool_call_id": call.id, "content": result.output,
                })

            followup = client.chat.completions.create(
                model=agent.model, max_tokens=agent.token_budget, messages=messages,
            )
            followup_usage = followup.usage
            broker.spend_tokens(
                agent.id, (followup_usage.prompt_tokens or 0) + (followup_usage.completion_tokens or 0),
            )
            final_text = followup.choices[0].message.content or ""
        else:
            final_text = reply.content or ""

        trace.append(MESSAGE, agent.id, {
            "sender": agent.id, "recipient": "orchestrator",
            "message_type": "TASK_RESULT",
            "content": {"output": final_text, "used_tool": bool(tool_calls)},
            "run_id": run_id,
        })

    return agent_fn


# --- Concrete tool specs for the three wired specialists --------------------

CRYPTO_TOOL = ToolSpec(
    name="decrypt_caesar",
    description="Decrypt a Caesar-shifted ciphertext. Pass shift=0 to try all 25 shifts.",
    properties={"ciphertext": {"type": "string"}, "shift": {"type": "integer"}},
    required=["ciphertext", "shift"],
    capability="run_tool",
    resource="decrypt_caesar",
    execute=lambda ciphertext, shift: decrypt_caesar(ciphertext, shift),
)

_RECON_EXECUTOR = SandboxedExecutor(timeout_seconds=30)
RECON_TOOL = ToolSpec(
    name="scan_localhost",
    description="Scan the assigned target (already fixed by the operator) for open ports 1-1000.",
    properties={},  # no model-controlled args — target is fixed below, not a callable parameter
    required=[],
    capability="run_tool",
    resource="nmap_scan",
    execute=lambda: nmap_scan("127.0.0.1", "1-1000", _RECON_EXECUTOR),
)

_WEB_EXECUTOR = SandboxedExecutor(timeout_seconds=15)
WEB_TOOL = ToolSpec(
    name="fetch_assigned_page",
    description="Fetch the assigned page (already fixed by the operator) and return its raw response.",
    properties={},  # no model-controlled args — URL is fixed below, not a callable parameter
    required=[],
    capability="fetch_url",
    egress_target="example.com",
    execute=lambda: http_get("https://example.com", {}, _WEB_EXECUTOR),
)
