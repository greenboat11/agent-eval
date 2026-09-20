"""Structured results: one JSON document per run, against a fixed schema,
with markdown rendered from it — never the other way around. Every run
records pinned model versions (from the manifest, which is itself the
record of what was supposed to run), a seed for whatever in the run was
stochastic, and cost.

Cost tracking is a stub: nothing in this skeleton makes a real model call
yet (no agent roster), so `cost_usd` is always `{}` until the harness that
actually calls Anthropic/OpenRouter populates it per agent. That's a TODO,
not a fabricated number — see the module docstring convention used
elsewhere in agenteval.core for why unvalidated placeholders get called out
rather than presented as real.
"""

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path

from agenteval.core.invariants import Violation
from agenteval.core.manifest import PopulationManifest
from agenteval.experiments.cascade import CascadeMetrics


@dataclass
class RunResult:
    run_id: str
    manifest_path: str
    trace_path: str
    final_trace_hash: str | None
    model_versions: dict[str, str]  # agent_id -> model, pinned from the manifest
    seed: int | None
    started_at: str
    ended_at: str
    cost_usd: dict[str, float] = field(default_factory=dict)  # TODO: populated once real model calls exist
    violations: list[dict] = field(default_factory=list)
    cascade_metrics: dict | None = None

    def to_json(self, path: Path) -> None:
        Path(path).write_text(json.dumps(dataclasses.asdict(self), indent=2), encoding="utf-8")


def build_run_result(
    run_id: str, manifest: PopulationManifest, manifest_path: str,
    trace_path: str, final_trace_hash: str | None,
    started_at: str, ended_at: str,
    violations: list[Violation],
    seed: int | None = None,
    cost_usd: dict[str, float] | None = None,
    cascade_metrics: CascadeMetrics | None = None,
) -> RunResult:
    model_versions = {
        agent.id: agent.model
        for gen in manifest.generations
        for agent in gen.agents
    }
    return RunResult(
        run_id=run_id,
        manifest_path=str(manifest_path),
        trace_path=str(trace_path),
        final_trace_hash=final_trace_hash,
        model_versions=model_versions,
        seed=seed,
        started_at=started_at,
        ended_at=ended_at,
        cost_usd=cost_usd or {},
        violations=[dataclasses.asdict(v) for v in violations],
        cascade_metrics=dataclasses.asdict(cascade_metrics) if cascade_metrics else None,
    )


def render_markdown(result: RunResult) -> str:
    lines = [
        f"# Run {result.run_id}",
        "",
        f"- Manifest: `{result.manifest_path}`",
        f"- Trace: `{result.trace_path}` (final hash `{result.final_trace_hash}`)",
        f"- Window: {result.started_at} -> {result.ended_at}",
        f"- Seed: {result.seed if result.seed is not None else 'n/a'}",
        "",
        "## Model versions",
        "",
        "| Agent | Model |",
        "|---|---|",
    ]
    for agent_id, model in sorted(result.model_versions.items()):
        lines.append(f"| {agent_id} | {model} |")

    lines += ["", "## Cost", ""]
    if result.cost_usd:
        lines += ["| Agent | USD |", "|---|---|"]
        lines += [f"| {a} | {c:.4f} |" for a, c in sorted(result.cost_usd.items())]
    else:
        lines.append("_No cost data recorded for this run (no live model calls made)._")

    lines += ["", "## Invariant violations", ""]
    if result.violations:
        lines += ["| Invariant | Kind | Composition depth | Agents |", "|---|---|---|---|"]
        for v in result.violations:
            agents = ", ".join(v["agent_ids"])
            lines.append(f"| {v['invariant_name']} | {v['kind']} | {v['composition_depth']} | {agents} |")
    else:
        lines.append("_None detected._")

    lines += ["", "## Cascade metrics", ""]
    if result.cascade_metrics:
        cm = result.cascade_metrics
        lines += [
            f"- Artifact: `{cm['artifact_id']}`, seeded by `{cm['seed_agent_id']}` at {cm['seed_time']}",
            f"- Adoption fraction: {cm['adoption_fraction']:.2f}",
            f"- Half-life: {cm['half_life_seconds']}",
            f"- Mean downstream adopters per adopter: {cm['mean_downstream_adopters_per_adopter']:.2f}",
        ]
    else:
        lines.append("_No cascade seeded in this run._")

    return "\n".join(lines) + "\n"
