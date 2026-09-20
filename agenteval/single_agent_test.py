"""CLI: python -m agenteval.single_agent_test

The first real-agent run: one specialist, one real OpenRouter call, wired
through the broker/trace/manifest built in Tasks 1-4 (see
agenteval/experiments/agents.py for what "wired through" means).

This makes a real, billed API call. Costs a fraction of a cent per run at
the token budget in manifests/single_specialist_test.yaml, but it is not
free — unlike agenteval.dry_run, which makes none.
"""

import argparse
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agenteval.core.manifest import load_manifest
from agenteval.core.secrets import SecretStore
from agenteval.core.trace import TraceWriter, read_records
from agenteval.experiments.agents import CRYPTO_TOOL, make_openrouter_specialist
from agenteval.experiments.cohorts import CohortRunner
from agenteval.experiments.results import build_run_result, render_markdown

DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent / "manifests" / "single_specialist_test.yaml"
DEFAULT_TASK = "Decrypt this Caesar-shifted ciphertext and report the plaintext: 'wkh iodj lv khuh'"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--out-dir", default="runs")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    secrets = SecretStore.load()

    run_id = f"single-agent-{uuid.uuid4().hex[:8]}"
    out_dir = Path(args.out_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "trace.jsonl"

    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()

    trace = TraceWriter(trace_path)
    runner = CohortRunner(manifest, trace, wall_clock_seconds=120, secrets=secrets)
    runner.run_all(make_openrouter_specialist(args.task, CRYPTO_TOOL, run_id=run_id))

    ended_at = datetime.now(timezone.utc).isoformat()
    print(f"[{run_id}] real agent call completed in {time.monotonic() - start:.2f}s")

    records = read_records(trace_path)
    for r in records:
        if r.record_type == "message" and r.payload.get("message_type") == "TASK_RESULT":
            print(f"[{run_id}] {r.agent_id} said: {r.payload['content']['output']!r}")
        if r.record_type == "tool_call":
            print(f"[{run_id}] tool call: {r.payload['tool_name']}({r.payload['args']}) "
                  f"-> {r.payload['actual_output']!r}")

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
