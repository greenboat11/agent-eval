"""Mediates every capability use. Every access path in the system is meant to
go through this — tools/ wrapper integration is TODO, tracked as part of the
Task 3 containment work (docs/CONTAINMENT.md), not implemented in this
skeleton pass.
"""

import hashlib
import json
from dataclasses import dataclass

from agenteval.core.manifest import PopulationManifest
from agenteval.core.trace import GRANT_USE, TraceWriter


class PermissionDenied(PermissionError):
    pass


@dataclass(frozen=True)
class Grant:
    capability: str
    resource: str | None


def _argument_hash(args: dict) -> str:
    return hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()


class CapabilityBroker:
    def __init__(self, manifest: PopulationManifest, trace: TraceWriter):
        self._trace = trace
        self._grants: dict[str, set[Grant]] = {
            agent.id: {Grant(c.capability, c.resource) for c in agent.capabilities}
            for gen in manifest.generations
            for agent in gen.agents
        }

    def grants_for(self, agent_id: str) -> set[Grant]:
        return set(self._grants.get(agent_id, set()))

    def is_granted(self, agent_id: str, capability: str, resource: str | None = None) -> bool:
        grants = self._grants.get(agent_id, set())
        return (
            Grant(capability, resource) in grants
            or Grant(capability, None) in grants  # unscoped grant covers any resource
        )

    def use(self, agent_id: str, capability: str, resource: str | None, args: dict) -> None:
        """Mediates one capability use. Raises PermissionDenied if not granted,
        otherwise emits a grant-use trace record before the caller proceeds.
        """
        if not self.is_granted(agent_id, capability, resource):
            raise PermissionDenied(
                f"agent {agent_id!r} is not granted capability {capability!r}"
                + (f" on resource {resource!r}" if resource else "")
            )
        self._trace.append(GRANT_USE, agent_id, {
            "capability": capability,
            "resource": resource,
            "argument_hash": _argument_hash(args),
        })
