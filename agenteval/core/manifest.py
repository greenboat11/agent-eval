"""Population manifest: the only place a run's roster is declared.

No agent roster is ever hardcoded in Python — everything about who exists,
what they can touch, and how they're connected comes from this YAML file.
See manifests/example_population.yaml for a worked example.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class CapabilityGrant:
    capability: str
    resource: str | None = None  # None = capability not scoped to one resource


@dataclass
class AgentSpec:
    id: str
    model: str
    capabilities: list[CapabilityGrant]
    token_budget: int
    topology: list[str] = field(default_factory=list)  # ids of agents this one may message


@dataclass
class Generation:
    id: str
    agents: list[AgentSpec]


@dataclass
class SubstrateResourceSpec:
    id: str
    kind: str  # e.g. "package_mirror", "scratch_registry", "shared_mount", "dns_resolver"
    zone: int
    params: dict = field(default_factory=dict)


@dataclass
class InvariantSpec:
    name: str
    kind: str  # e.g. "forbidden_capability_pair", "forbidden_zone_crossing"
    params: dict = field(default_factory=dict)


@dataclass
class PopulationManifest:
    generations: list[Generation]
    substrate: list[SubstrateResourceSpec]
    invariants: list[InvariantSpec]

    def agent_ids(self) -> set[str]:
        return {a.id for g in self.generations for a in g.agents}

    def agent(self, agent_id: str) -> AgentSpec:
        for g in self.generations:
            for a in g.agents:
                if a.id == agent_id:
                    return a
        raise KeyError(f"no such agent in manifest: {agent_id}")


class ManifestError(ValueError):
    pass


def _require(d: dict, key: str, context: str) -> object:
    if key not in d:
        raise ManifestError(f"missing required field '{key}' in {context}")
    return d[key]


def _load_agent(d: dict, context: str) -> AgentSpec:
    caps = [
        CapabilityGrant(capability=c["capability"], resource=c.get("resource"))
        for c in d.get("capabilities", [])
    ]
    return AgentSpec(
        id=_require(d, "id", context),
        model=_require(d, "model", context),
        capabilities=caps,
        token_budget=_require(d, "token_budget", context),
        topology=d.get("topology", []),
    )


def load_manifest(path: Path) -> PopulationManifest:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())

    generations = [
        Generation(
            id=_require(g, "id", "generation"),
            agents=[_load_agent(a, f"generation {g.get('id')}") for a in g.get("agents", [])],
        )
        for g in raw.get("generations", [])
    ]
    substrate = [
        SubstrateResourceSpec(
            id=_require(s, "id", "substrate resource"),
            kind=_require(s, "kind", "substrate resource"),
            zone=_require(s, "zone", "substrate resource"),
            params=s.get("params", {}),
        )
        for s in raw.get("substrate", [])
    ]
    invariants = [
        InvariantSpec(
            name=_require(i, "name", "invariant"),
            kind=_require(i, "kind", "invariant"),
            params=i.get("params", {}),
        )
        for i in raw.get("invariants", [])
    ]

    manifest = PopulationManifest(generations=generations, substrate=substrate, invariants=invariants)

    all_ids = manifest.agent_ids()
    for g in manifest.generations:
        for a in g.agents:
            unknown = set(a.topology) - all_ids
            if unknown:
                raise ManifestError(f"agent {a.id} has topology edge(s) to unknown agent(s): {unknown}")

    return manifest
