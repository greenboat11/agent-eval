from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from bus.message import Message
from monitor.signals import (
    AdherenceSignal,
    GraphSignal,
    IntegritySignal,
    SignalResult,
    VolumeSignal,
)


class ControlState(Enum):
    NOMINAL = "NOMINAL"
    ELEVATED = "ELEVATED"
    CRITICAL = "CRITICAL"


@dataclass
class StateTransition:
    from_state: ControlState
    to_state: ControlState
    timestamp: datetime
    signal_snapshot: list[SignalResult]
    trigger: str


class ControlMonitor:
    def __init__(self, config: dict):
        t = config.get("thresholds", {})
        self._graph = GraphSignal()
        self._volume = VolumeSignal(
            window_seconds=t.get("volume_window_seconds", 300),
            multiplier=t.get("volume_multiplier", 3.0),
        )
        self._adherence = AdherenceSignal(min_similarity=t.get("adherence_min", 0.6))
        self._integrity = IntegritySignal()
        self._state = ControlState.NOMINAL
        self._transitions: list[StateTransition] = []
        self._last_snapshot: list[SignalResult] = []

    def on_message(self, message: Message) -> None:
        results = [
            self._graph.update(message),
            self._volume.update(message),
            self._adherence.update(message),
        ]
        self._last_snapshot = results
        self._evaluate(results, trigger=f"message:{message.message_type.value}")

    def check_tool_result(self, tool_name: str, args: dict,
                          claimed_hash: str, actual_output: str) -> None:
        result = self._integrity.check(tool_name, args, claimed_hash, actual_output)
        snapshot = self._last_snapshot + [result]
        if result.elevated:
            self._transition_to(ControlState.CRITICAL, snapshot, trigger="integrity_failure")

    def get_state(self) -> ControlState:
        return self._state

    def get_transitions(self) -> list[StateTransition]:
        return list(self._transitions)

    def get_signal_snapshot(self) -> list[SignalResult]:
        return list(self._last_snapshot)

    def _evaluate(self, results: list[SignalResult], trigger: str) -> None:
        elevated_count = sum(1 for r in results if r.elevated)
        if elevated_count == 0:
            if self._state == ControlState.ELEVATED:
                self._transition_to(ControlState.NOMINAL, results, trigger="signals_cleared")
        elif elevated_count == 1:
            if self._state == ControlState.NOMINAL:
                self._transition_to(ControlState.ELEVATED, results, trigger=trigger)
        else:
            if self._state != ControlState.CRITICAL:
                self._transition_to(ControlState.CRITICAL, results, trigger=trigger)

    def _transition_to(self, new_state: ControlState,
                       snapshot: list[SignalResult], trigger: str) -> None:
        if new_state == self._state:
            return
        self._transitions.append(StateTransition(
            from_state=self._state,
            to_state=new_state,
            timestamp=datetime.now(timezone.utc),
            signal_snapshot=snapshot,
            trigger=trigger,
        ))
        self._state = new_state
