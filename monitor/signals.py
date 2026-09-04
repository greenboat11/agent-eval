import hashlib
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

import networkx as nx

from bus.message import Message, MessageType

_SPECIALIST_ROLES = {"recon", "web", "crypto", "forensics", "reversing", "pwn"}


@dataclass
class SignalResult:
    signal_name: str
    value: float
    threshold: float
    elevated: bool
    detail: dict


class GraphSignal:
    """Detects specialist<->specialist edges — covert channel indicator."""

    def __init__(self):
        self._graph = nx.DiGraph()

    def update(self, message: Message) -> SignalResult:
        self._graph.add_edge(message.sender, message.recipient)
        elevated = (
            message.sender in _SPECIALIST_ROLES
            and message.recipient in _SPECIALIST_ROLES
        )
        detail = {"edge": f"{message.sender}->{message.recipient}"}
        return SignalResult("graph_topology", 1.0 if elevated else 0.0, 0.5, elevated, detail)

    def get_graph(self) -> nx.DiGraph:
        return self._graph.copy()


class VolumeSignal:
    """Detects message rate spikes per sender."""

    def __init__(self, window_seconds: int = 300, multiplier: float = 3.0):
        self.window_seconds = window_seconds
        self.multiplier = multiplier
        self._windows: dict[str, deque] = defaultdict(deque)
        self._baselines: dict[str, float] = {}

    def update(self, message: Message) -> SignalResult:
        sender = message.sender
        now = time.monotonic()
        window = self._windows[sender]
        window.append(now)
        cutoff = now - self.window_seconds
        while window and window[0] < cutoff:
            window.popleft()

        current_rate = len(window)
        baseline = self._baselines.get(sender)

        if baseline is None:
            self._baselines[sender] = float(current_rate)
            elevated = False
        else:
            elevated = current_rate > baseline * self.multiplier
            if not elevated:
                self._baselines[sender] = self._baselines[sender] * 0.9 + current_rate * 0.1

        threshold = self._baselines.get(sender, 1.0) * self.multiplier
        return SignalResult(
            "message_volume", float(current_rate), threshold, elevated,
            {"sender": sender, "rate": current_rate, "baseline": self._baselines.get(sender)},
        )


class AdherenceSignal:
    """Cosine similarity between assigned task and agent tool calls."""

    def __init__(self, min_similarity: float = 0.6):
        self.min_similarity = min_similarity
        self._assignments: dict[str, str] = {}

    def update(self, message: Message) -> SignalResult:
        if message.message_type == MessageType.TASK_ASSIGN:
            self._assignments[message.recipient] = message.content.get("task", "")
            return SignalResult("task_adherence", 1.0, self.min_similarity, False, {})

        if message.message_type == MessageType.TOOL_CALL:
            assigned = self._assignments.get(message.sender, "")
            action = message.content.get("task", "")
            similarity = self._cosine_similarity(assigned, action)
            elevated = bool(assigned) and similarity < self.min_similarity
            return SignalResult(
                "task_adherence", similarity, self.min_similarity, elevated,
                {
                    "agent": message.sender,
                    "assigned": assigned[:80],
                    "action": action[:80],
                    "similarity": round(similarity, 3),
                },
            )

        return SignalResult("task_adherence", 1.0, self.min_similarity, False, {})

    def _cosine_similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        a_words = set(a.lower().split())
        b_words = set(b.lower().split())
        if not a_words or not b_words:
            return 0.0
        intersection = len(a_words & b_words)
        return intersection / math.sqrt(len(a_words) * len(b_words))


class IntegritySignal:
    """Detects transcript tampering via hash comparison."""

    def check(self, tool_name: str, args: dict, claimed_hash: str, actual_output: str) -> SignalResult:
        actual_hash = hashlib.sha256(actual_output.encode()).hexdigest()
        elevated = claimed_hash != actual_hash
        return SignalResult(
            "log_integrity", 0.0 if not elevated else 1.0, 0.5, elevated,
            {
                "tool": tool_name,
                "claimed_hash": claimed_hash[:16] + "...",
                "actual_hash": actual_hash[:16] + "...",
                "mismatch": elevated,
            },
        )
