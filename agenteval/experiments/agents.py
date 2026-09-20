"""First real-agent milestone: one specialist, one real model call, wired
through everything the skeleton built so far instead of around it.

What "wired through" means concretely, since this is the part worth
learning from:

- The agent never sees `OPENROUTER_API_KEY`. It asks the broker for it
  (`broker.get_secret`), which only succeeds because the manifest grants
  this agent the `call_llm` capability on that exact secret name.
- The agent's own text/tool exchange is written to the trace as MESSAGE
  records, same shape as agenteval/dry_run.py's scripted agent uses — so
  this trace replays against both monitors exactly like a synthetic one.
- When the model asks to call a tool, that call goes through
  `broker.use()` (permission-checked, argument-hashed, trace-recorded)
  *before* the real tool in tools/crypto.py executes — this is the
  tool-wrapper/broker integration that was a named TODO after Task 3.
- Token spend is reported to `broker.spend_tokens`, so a real run is
  subject to the same budget enforcement a synthetic one is.

This is deliberately narrow: one specialist, one tool, no orchestrator, no
retry logic, no multi-turn planning. Real agent-loop concerns (retries,
malformed tool-call JSON, multi-tool plans) are the next increments, not
this one.
"""

import json
from pathlib import Path

from openai import OpenAI

from agenteval.core.broker import CapabilityBroker
from agenteval.core.manifest import AgentSpec
from agenteval.core.substrate import SubstrateResource
from agenteval.core.trace import MESSAGE, TOOL_CALL, TraceWriter
from tools.crypto import decrypt_caesar

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "agents" / "prompts"

_DECRYPT_CAESAR_TOOL = {
    "type": "function",
    "function": {
        "name": "decrypt_caesar",
        "description": "Decrypt a Caesar-shifted ciphertext. Pass shift=0 to try all 25 shifts.",
        "parameters": {
            "type": "object",
            "properties": {
                "ciphertext": {"type": "string"},
                "shift": {"type": "integer"},
            },
            "required": ["ciphertext", "shift"],
        },
    },
}


def _load_prompt(role: str) -> str:
    path = PROMPTS_DIR / f"{role}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"You are the {role} specialist. Complete the assigned task and report findings."


def make_openrouter_specialist(task: str, run_id: str = "single-agent-test"):
    """Returns an AgentFn (agenteval/experiments/cohorts.py) for one real,
    tool-using OpenRouter call. `task` is the natural-language task text —
    baked in via closure since AgentFn's signature has no room for it.
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
            messages=messages, tools=[_DECRYPT_CAESAR_TOOL],
        )
        usage = completion.usage
        broker.spend_tokens(agent.id, (usage.prompt_tokens or 0) + (usage.completion_tokens or 0))

        reply = completion.choices[0].message
        tool_calls = reply.tool_calls or []

        if tool_calls:
            messages.append(reply.model_dump(exclude_none=True))
            for call in tool_calls:
                tool_args = json.loads(call.function.arguments)
                broker.use(agent.id, "run_tool", "decrypt_caesar", tool_args)
                result = decrypt_caesar(tool_args["ciphertext"], tool_args["shift"])
                trace.append(TOOL_CALL, agent.id, {
                    "tool_name": "decrypt_caesar", "args": result.args,
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
