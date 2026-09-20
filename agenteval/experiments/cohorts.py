"""Generational cohorts: the manifest's generations run in order, sharing one
substrate instance across the whole population run. A later cohort boots
cold — it gets no Python-level state from the cohort before it, no shared
memory, no handoff object — and can only find what a prior cohort left by
actually reading substrate, the same way any other cross-agent discovery
happens in this project. See docs/adr/001-compositional-pivot.md.

Deliberate budget skew is just per-agent token_budget values in the
manifest differing within one generation — RunBudget enforces whatever the
manifest declares, independently per agent, with no assumption that a
generation's agents share a budget.
"""

from collections.abc import Callable
from dataclasses import dataclass

from agenteval.core.broker import CapabilityBroker
from agenteval.core.budget import RunBudget
from agenteval.core.egress import EgressPolicy
from agenteval.core.manifest import AgentSpec, Generation, PopulationManifest
from agenteval.core.secrets import SecretStore
from agenteval.core.substrate import SubstrateResource, build_substrate
from agenteval.core.trace import AGENT_LIFECYCLE, TraceWriter

# An agent_fn is deliberately not an LLM-driven agent implementation here —
# per the Task 4 constraint, the full roster isn't built yet. It's the seam
# a real orchestrator/specialist loop plugs into later: given its own spec,
# the shared broker, the shared substrate, the trace, and which generation
# it's running in, it does whatever it does.
AgentFn = Callable[[AgentSpec, CapabilityBroker, dict[str, SubstrateResource], TraceWriter, str], None]


@dataclass
class CohortRunResult:
    generation_id: str
    agent_ids: list[str]
    budget: RunBudget


class CohortRunner:
    """Owns the one substrate instance and one trace that every generation in
    a population run shares. Constructed once per run; call run_all() (or
    run_generation() per-generation for finer control, e.g. in tests).
    """

    def __init__(
        self,
        manifest: PopulationManifest,
        trace: TraceWriter,
        wall_clock_seconds: float = 3600,
        secrets: SecretStore | None = None,
        egress: EgressPolicy | None = None,
        canary_token: str | None = None,
    ):
        self.manifest = manifest
        self.trace = trace
        self.wall_clock_seconds = wall_clock_seconds
        self.secrets = secrets
        self.egress = egress
        self.canary_token = canary_token
        # Built once, shared by every generation — this is what lets cohort
        # K+1 find cohort K's artifacts.
        self.substrate: dict[str, SubstrateResource] = build_substrate(manifest.substrate)

    def run_generation(self, generation: Generation, agent_fn: AgentFn) -> CohortRunResult:
        budget = RunBudget(
            wall_clock_seconds=self.wall_clock_seconds,
            token_budgets={a.id: a.token_budget for a in generation.agents},
        )
        broker = CapabilityBroker(
            self.manifest, self.trace,
            secrets=self.secrets, egress=self.egress, budget=budget,
            canary_token=self.canary_token,
        )

        self.trace.append(AGENT_LIFECYCLE, None, {
            "event": "generation_start", "generation_id": generation.id,
            "agent_ids": [a.id for a in generation.agents],
        })
        for agent in generation.agents:
            self.trace.append(AGENT_LIFECYCLE, agent.id, {
                "event": "agent_start", "generation_id": generation.id,
            })
            agent_fn(agent, broker, self.substrate, self.trace, generation.id)
            self.trace.append(AGENT_LIFECYCLE, agent.id, {
                "event": "agent_end", "generation_id": generation.id,
            })
        self.trace.append(AGENT_LIFECYCLE, None, {
            "event": "generation_end", "generation_id": generation.id,
        })

        return CohortRunResult(
            generation_id=generation.id,
            agent_ids=[a.id for a in generation.agents],
            budget=budget,
        )

    def run_all(self, agent_fn: AgentFn) -> list[CohortRunResult]:
        return [self.run_generation(gen, agent_fn) for gen in self.manifest.generations]
