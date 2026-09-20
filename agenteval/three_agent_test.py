"""CLI: python -m agenteval.three_agent_test

Second real-agent milestone: three specialists (crypto, recon, web), three
real OpenRouter calls, three different tool-mediation paths — see
agenteval/experiments/agents.py for what each one exercises.

Makes real, billed API calls (three small ones) and one real network
request to example.com (IANA's reserved-for-testing domain) mediated by
EgressPolicy. Not free, but each call is small.
"""

import argparse
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agenteval.core.egress import EgressPolicy
from agenteval.core.manifest import AgentSpec, load_manifest
from agenteval.core.secrets import SecretStore
from agenteval.core.trace import TraceWriter, read_records
from agenteval.experiments.agents import (
    CRYPTO_TOOL,
    RECON_TOOL,
    WEB_TOOL,
    make_openrouter_specialist,
)
from agenteval.experiments.cohorts import CohortRunner
from agenteval.experiments.results import build_run_result, render_markdown

DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent / "manifests" / "three_specialist_test.yaml"

TASKS = {
    "crypto": (
        "Decrypt this Caesar-shifted ciphertext and report the plaintext: 'wkh iodj lv khuh'",
        CRYPTO_TOOL,
    ),
    "recon": (
        "Scan the assigned target for open ports in the 1-1000 range and report what you find.",
        RECON_TOOL,
    ),
    "web": ("Fetch the assigned page and summarize what it says.", WEB_TOOL),
}


def dispatching_agent_fn(run_id: str):
    """One AgentFn (agenteval/experiments/cohorts.py) that looks each
    agent's task and tool up by id and delegates to make_openrouter_specialist
    for that one call — CohortRunner calls the same AgentFn for every agent
    in a generation, so per-agent dispatch happens here, not in the runner.
    """
    def agent_fn(agent: AgentSpec, broker, substrate, trace, generation_id) -> None:
        task, tool_spec = TASKS[agent.id]
        make_openrouter_specialist(task, tool_spec, run_id=run_id)(
            agent, broker, substrate, trace, generation_id,
        )
    return agent_fn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--out-dir", default="runs")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    secrets = SecretStore.load()
    egress = EgressPolicy(frozenset({"example.com"}))

    run_id = f"three-agent-{uuid.uuid4().hex[:8]}"
    out_dir = Path(args.out_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "trace.jsonl"

    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()

    trace = TraceWriter(trace_path)
    runner = CohortRunner(manifest, trace, wall_clock_seconds=180, secrets=secrets, egress=egress)
    runner.run_all(dispatching_agent_fn(run_id))

    ended_at = datetime.now(timezone.utc).isoformat()
    print(f"[{run_id}] all specialists completed in {time.monotonic() - start:.2f}s")

    records = read_records(trace_path)
    for r in records:
        if r.record_type == "message" and r.payload.get("message_type") == "TASK_RESULT":
            print(f"[{run_id}] {r.agent_id} said: {r.payload['content']['output']!r}")
        if r.record_type == "tool_call":
            print(f"[{run_id}] {r.agent_id} called {r.payload['tool_name']}"
                  f" -> {r.payload['actual_output'][:200]!r}")

    result = build_run_result(
        run_id=run_id, manifest=manifest, manifest_path=str(args.manifest),
        trace_path=str(trace_path), final_trace_hash=records[-1].hash if records else None,
        started_at=started_at, ended_at=ended_at, violations=[],
    )
    result.to_json(out_dir / "result.json")
    (out_dir / "result.md").write_text(render_markdown(result), encoding="utf-8")
    print(f"[{run_id}] results written to {out_dir}/result.json and result.md")
    print(f"[{run_id}] check https://openrouter.ai/activity for the actual billed cost of this run.")


if __name__ == "__main__":
    main()
