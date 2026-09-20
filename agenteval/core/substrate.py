"""Pluggable shared resources whose affordances are NOT labeled as
communication — this is deliberately the class of thing the original
bus-scoped monitor could never see (docs/adr/001-compositional-pivot.md).

Each resource's ground-truth channel capacity lives in a separate answer-key
file (see load_answer_key below) that monitors never receive — it exists so
a held-out evaluator can score detection against a known quantity, not so a
monitor can cheat by reading it.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from agenteval.core.broker import CapabilityBroker
from agenteval.core.manifest import SubstrateResourceSpec
from agenteval.core.trace import SUBSTRATE_READ, SUBSTRATE_WRITE, TraceWriter


@dataclass
class Artifact:
    """What a substrate read actually returns: not just the value, but who
    put it there and in which generation, so generational-cohort experiments
    (agenteval/experiments/cohorts.py) can tell a cold-booted cohort found
    something a prior cohort left, not something it produced itself.
    """

    value: object
    written_by: str
    generation_id: str | None
    written_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SubstrateResource:
    """Base class for a shared resource. Subclasses are stubs: enough behavior
    to exercise the broker/trace/invariants interfaces, not production
    implementations of a package mirror, DNS resolver, etc.
    """

    def __init__(self, spec: SubstrateResourceSpec):
        self.id = spec.id
        self.kind = spec.kind
        self.zone = spec.zone
        self.params = spec.params
        self._store: dict[str, Artifact] = {}

    def write(self, agent_id: str, broker: CapabilityBroker, trace: TraceWriter,
              capability: str, artifact_id: str, value: object,
              generation_id: str | None = None) -> None:
        broker.use(agent_id, capability, self.id, {"artifact_id": artifact_id})
        artifact = Artifact(value=value, written_by=agent_id, generation_id=generation_id)
        self._store[artifact_id] = artifact
        trace.append(SUBSTRATE_WRITE, agent_id, {
            "resource": self.id, "kind": self.kind, "zone": self.zone,
            "capability": capability, "artifact_id": artifact_id,
            "generation_id": generation_id,
        })

    def read(self, agent_id: str, broker: CapabilityBroker, trace: TraceWriter,
             capability: str, artifact_id: str,
             generation_id: str | None = None) -> Artifact | None:
        broker.use(agent_id, capability, self.id, {"artifact_id": artifact_id})
        artifact = self._store.get(artifact_id)
        trace.append(SUBSTRATE_READ, agent_id, {
            "resource": self.id, "kind": self.kind, "zone": self.zone,
            "capability": capability, "artifact_id": artifact_id,
            "generation_id": generation_id,
            "found": artifact is not None,
            "written_by": artifact.written_by if artifact else None,
            "written_in_generation": artifact.generation_id if artifact else None,
        })
        return artifact


class PackageMirror(SubstrateResource):
    """Stub: directory/package names are the affordance, per the incident."""


class ScratchRegistry(SubstrateResource):
    """Stub: a shared writable key registry."""


class SharedMount(SubstrateResource):
    """Stub: a shared writable filesystem mount."""


class DNSResolver(SubstrateResource):
    """Stub: TXT/subdomain-style resolution as a covert affordance."""


_KIND_TO_CLASS = {
    "package_mirror": PackageMirror,
    "scratch_registry": ScratchRegistry,
    "shared_mount": SharedMount,
    "dns_resolver": DNSResolver,
}


def build_substrate(specs: list[SubstrateResourceSpec]) -> dict[str, SubstrateResource]:
    resources = {}
    for spec in specs:
        cls = _KIND_TO_CLASS.get(spec.kind, SubstrateResource)
        resources[spec.id] = cls(spec)
    return resources


@dataclass
class ChannelCapacity:
    resource_id: str
    bits_per_access: float
    notes: str = ""


def load_answer_key(path: Path) -> dict[str, ChannelCapacity]:
    """Loads ground-truth channel capacity per substrate resource. This file
    is never imported by agenteval.monitors — only by scoring/eval code that
    needs to know, independent of any monitor, how much bandwidth a resource
    actually offered.
    """
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return {
        resource_id: ChannelCapacity(
            resource_id=resource_id,
            bits_per_access=entry["bits_per_access"],
            notes=entry.get("notes", ""),
        )
        for resource_id, entry in raw.items()
    }
