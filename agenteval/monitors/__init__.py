"""Monitor plugin interface. The harness never calls a monitor directly —
only agenteval.core.replay does, by name, against a stored trace.
"""

from collections.abc import Callable
from typing import Protocol

from agenteval.core.invariants import Violation
from agenteval.core.manifest import InvariantSpec
from agenteval.core.trace import TraceRecord


class Monitor(Protocol):
    name: str

    def evaluate(self, records: list[TraceRecord], invariants: list[InvariantSpec]) -> list[Violation]:
        """Returns the violations this monitor detects in the given trace.
        Two monitors run against the same trace are expected to disagree —
        that disagreement is the experiment's result, not a bug.
        """
        ...


_REGISTRY: dict[str, Callable[[], Monitor]] = {}


def register(name: str):
    def decorator(factory: Callable[[], Monitor]):
        _REGISTRY[name] = factory
        return factory
    return decorator


def get_monitor(name: str) -> Monitor:
    if name not in _REGISTRY:
        raise KeyError(f"unknown monitor {name!r}; available: {sorted(_REGISTRY)}")
    return _REGISTRY[name]()


def available_monitors() -> list[str]:
    return sorted(_REGISTRY)


# Importing this package registers the built-in monitors. Each submodule
# calls register(...) at import time as a side effect.
from agenteval.monitors import baseline_per_agent, compositional  # noqa: F401
