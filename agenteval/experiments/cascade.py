"""Cascade seeding: inject an artifact at one agent, then measure how (and
whether) it propagates through the declared population topology.

Definitions used below (stated explicitly because "half-life" and
"downstream adopters" don't have one universal meaning):

- An **adopter** is any agent other than the seeder that reads the seeded
  artifact_id from substrate at least once. Its adoption time is the
  timestamp of its *first* such read.
- **Adoption fraction** = number of adopters / (population size - 1), i.e.
  out of everyone who could have adopted.
- **Half-life** here means: elapsed time from the seed write to the moment
  cumulative adopters first reach half of the *eventual* adopter count.
  This is a discrete-event estimate, not a fitted exponential decay
  constant — do not conflate it with a half-life in the radioactive-decay
  sense.
- **Mean downstream adopters per adopter** uses the manifest's declared
  topology (AgentSpec.topology): for each adopter, count how many of its
  topology neighbors are *also* adopters who adopted later, then average
  that count across all adopters. This is a branching-factor proxy over the
  declared graph, not an inferred causal attribution — the trace has no
  record of *why* a neighbor adopted, only that it did, and later.
"""

from dataclasses import dataclass, field

from agenteval.core.broker import CapabilityBroker
from agenteval.core.manifest import PopulationManifest
from agenteval.core.substrate import SubstrateResource
from agenteval.core.trace import (
    SUBSTRATE_READ,
    SUBSTRATE_WRITE,
    TraceRecord,
    TraceWriter,
)


def seed_cascade(
    substrate: SubstrateResource, broker: CapabilityBroker, trace: TraceWriter,
    agent_id: str, capability: str, artifact_id: str, value: object,
    generation_id: str | None = None,
) -> None:
    """Injects `value` as `artifact_id` at `agent_id`, at "time T" = now.
    A thin, named wrapper around SubstrateResource.write so a cascade's seed
    event is easy to find in code and in a trace by intent, not just by
    being the first write of that artifact_id.
    """
    substrate.write(agent_id, broker, trace, capability, artifact_id, value, generation_id)


@dataclass
class AdoptionEvent:
    agent_id: str
    adopted_at: str  # ISO timestamp of first read


@dataclass
class CascadeMetrics:
    artifact_id: str
    seed_agent_id: str
    seed_time: str
    adopters: list[AdoptionEvent] = field(default_factory=list)
    adoption_fraction: float = 0.0
    half_life_seconds: float | None = None
    mean_downstream_adopters_per_adopter: float = 0.0


def _iso_delta_seconds(a: str, b: str) -> float:
    from datetime import datetime
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()


def analyze_cascade(
    records: list[TraceRecord], manifest: PopulationManifest,
    artifact_id: str, seed_agent_id: str,
) -> CascadeMetrics:
    seed_time = None
    for r in records:
        if (r.record_type == SUBSTRATE_WRITE and r.agent_id == seed_agent_id
                and r.payload.get("artifact_id") == artifact_id):
            seed_time = r.timestamp
            break
    if seed_time is None:
        raise ValueError(f"no seed write found for artifact_id={artifact_id!r} by {seed_agent_id!r}")

    # Tracked by trace `seq`, not by comparing timestamp strings: two reads
    # can land on the same wall-clock tick depending on clock resolution,
    # but seq is a strict, gap-free causal order straight from the trace.
    first_adoption: dict[str, tuple[int, str]] = {}
    for r in records:
        is_read_of_artifact = (
            r.record_type == SUBSTRATE_READ and r.payload.get("artifact_id") == artifact_id
            and r.agent_id != seed_agent_id and r.agent_id is not None
        )
        if is_read_of_artifact and (r.agent_id not in first_adoption or r.seq < first_adoption[r.agent_id][0]):
            first_adoption[r.agent_id] = (r.seq, r.timestamp)

    adopters = sorted(
        (AdoptionEvent(agent_id=a, adopted_at=t) for a, (seq, t) in first_adoption.items()),
        key=lambda e: first_adoption[e.agent_id][0],
    )

    population = manifest.agent_ids() - {seed_agent_id}
    adoption_fraction = len(adopters) / len(population) if population else 0.0

    half_life_seconds = None
    if adopters:
        target = -(-len(adopters) // 2)  # ceil(n/2)
        half_life_seconds = _iso_delta_seconds(seed_time, adopters[target - 1].adopted_at)

    topology = {agent_id: set(manifest.agent(agent_id).topology) for agent_id in population}
    adoption_seq = {a: seq for a, (seq, _) in first_adoption.items()}
    downstream_counts = []
    for e in adopters:
        neighbors = topology.get(e.agent_id, set())
        downstream = sum(
            1 for n in neighbors
            if n in adoption_seq and adoption_seq[n] > adoption_seq[e.agent_id]
        )
        downstream_counts.append(downstream)
    mean_downstream = sum(downstream_counts) / len(downstream_counts) if downstream_counts else 0.0

    return CascadeMetrics(
        artifact_id=artifact_id,
        seed_agent_id=seed_agent_id,
        seed_time=seed_time,
        adopters=adopters,
        adoption_fraction=adoption_fraction,
        half_life_seconds=half_life_seconds,
        mean_downstream_adopters_per_adopter=mean_downstream,
    )
