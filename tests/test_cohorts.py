"""Generational cohorts: substrate persists across generations, a cohort
boots cold, and per-agent budget skew within a cohort is real enforcement,
not just a declared number.
"""

import pytest

from agenteval.core.budget import BudgetExceeded
from agenteval.core.manifest import (
    AgentSpec,
    CapabilityGrant,
    Generation,
    PopulationManifest,
    SubstrateResourceSpec,
)
from agenteval.core.trace import TraceWriter
from agenteval.experiments.cohorts import CohortRunner


def _two_generation_manifest():
    return PopulationManifest(
        generations=[
            Generation(id="gen-0", agents=[
                AgentSpec(id="seeder", model="x", token_budget=100,
                          capabilities=[CapabilityGrant("write_mount", "mount")]),
            ]),
            Generation(id="gen-1", agents=[
                AgentSpec(id="scout-rich", model="x", token_budget=1000,
                          capabilities=[CapabilityGrant("read_mount", "mount")]),
                AgentSpec(id="scout-poor", model="x", token_budget=5,
                          capabilities=[CapabilityGrant("read_mount", "mount")]),
            ]),
        ],
        substrate=[SubstrateResourceSpec(id="mount", kind="shared_mount", zone=3)],
        invariants=[],
    )


def test_cohort_k_plus_one_finds_cohort_k_artifact(tmp_path):
    manifest = _two_generation_manifest()
    trace = TraceWriter(tmp_path / "run.jsonl")
    runner = CohortRunner(manifest, trace, wall_clock_seconds=3600)

    found = {}

    def agent_fn(agent, broker, substrate, trace, generation_id):
        if agent.id == "seeder":
            substrate["mount"].write(
                agent.id, broker, trace, "write_mount",
                artifact_id="left-behind", value="cohort-0-payload",
                generation_id=generation_id,
            )
        elif agent.id in ("scout-rich", "scout-poor"):
            artifact = substrate["mount"].read(
                agent.id, broker, trace, "read_mount",
                artifact_id="left-behind", generation_id=generation_id,
            )
            found[agent.id] = artifact

    runner.run_all(agent_fn)

    # gen-1 booted cold (no Python state passed between generations other
    # than the shared substrate) and still found what gen-0 left.
    assert found["scout-rich"].value == "cohort-0-payload"
    assert found["scout-rich"].written_by == "seeder"
    assert found["scout-rich"].generation_id == "gen-0"
    assert found["scout-poor"].value == "cohort-0-payload"


def test_budget_skew_enforced_independently_per_agent(tmp_path):
    manifest = _two_generation_manifest()
    trace = TraceWriter(tmp_path / "run.jsonl")
    runner = CohortRunner(manifest, trace, wall_clock_seconds=3600)

    def agent_fn(agent, broker, substrate, trace, generation_id):
        if agent.id == "scout-rich":
            broker.spend_tokens(agent.id, 900)  # well under its 1000 cap
        elif agent.id == "scout-poor":
            with pytest.raises(BudgetExceeded):
                broker.spend_tokens(agent.id, 900)  # far over its 5-token cap

    runner.run_generation(manifest.generations[0], lambda *a: None)
    runner.run_generation(manifest.generations[1], agent_fn)
