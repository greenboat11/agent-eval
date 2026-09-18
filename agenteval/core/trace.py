"""Append-only, hash-chained trace of everything that happens in a run.

The trace is the sole record replay operates on (see agenteval/replay.py).
Agents only ever get a TraceHandle (write-only, bound to one agent_id) — the
read/verify side (TraceReader) is for the harness and monitors, never for an
agent process to reach.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

GENESIS_HASH = "0" * 64

# Record types. See docs/adr/001-compositional-pivot.md for what each models.
AGENT_LIFECYCLE = "agent_lifecycle"
GRANT_USE = "grant_use"
SUBSTRATE_READ = "substrate_read"
SUBSTRATE_WRITE = "substrate_write"
MESSAGE = "message"
TOOL_CALL = "tool_call"

RECORD_TYPES = frozenset({
    AGENT_LIFECYCLE, GRANT_USE, SUBSTRATE_READ, SUBSTRATE_WRITE, MESSAGE, TOOL_CALL,
})


@dataclass
class TraceRecord:
    seq: int
    timestamp: str
    record_type: str
    agent_id: str | None
    payload: dict
    prev_hash: str
    hash: str = field(init=False, default="")

    def _content(self) -> dict:
        return {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "record_type": self.record_type,
            "agent_id": self.agent_id,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
        }

    def compute_hash(self) -> str:
        canonical = json.dumps(self._content(), sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def to_dict(self) -> dict:
        d = self._content()
        d["hash"] = self.hash
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TraceRecord":
        rec = cls(
            seq=d["seq"],
            timestamp=d["timestamp"],
            record_type=d["record_type"],
            agent_id=d.get("agent_id"),
            payload=d["payload"],
            prev_hash=d["prev_hash"],
        )
        rec.hash = d["hash"]
        return rec


def _argument_hash(args: dict) -> str:
    return hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()


class TraceWriter:
    """Owns the append-only file. Not given to agents directly — see TraceHandle."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = 0
        self._last_hash = GENESIS_HASH
        if self.path.exists() and self.path.stat().st_size > 0:
            existing = read_records(self.path)
            if existing:
                self._seq = existing[-1].seq + 1
                self._last_hash = existing[-1].hash

    def append(self, record_type: str, agent_id: str | None, payload: dict) -> TraceRecord:
        if record_type not in RECORD_TYPES:
            raise ValueError(f"unknown record_type: {record_type}")
        record = TraceRecord(
            seq=self._seq,
            timestamp=datetime.now(timezone.utc).isoformat(),
            record_type=record_type,
            agent_id=agent_id,
            payload=payload,
            prev_hash=self._last_hash,
        )
        record.hash = record.compute_hash()
        with self.path.open("a") as f:
            f.write(json.dumps(record.to_dict()) + "\n")
        self._seq += 1
        self._last_hash = record.hash
        return record

    def handle_for(self, agent_id: str) -> "TraceHandle":
        return TraceHandle(self, agent_id)


class TraceHandle:
    """Write-only view of a TraceWriter, bound to a single agent. No read methods."""

    def __init__(self, writer: TraceWriter, agent_id: str):
        self._writer = writer
        self.agent_id = agent_id

    def record(self, record_type: str, payload: dict) -> None:
        self._writer.append(record_type, self.agent_id, payload)


def read_records(path: Path) -> list[TraceRecord]:
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(TraceRecord.from_dict(json.loads(line)))
    return records


def verify_chain(records: list[TraceRecord]) -> bool:
    """Recomputes the hash chain; False means the trace was tampered with or reordered."""
    prev_hash = GENESIS_HASH
    for record in records:
        if record.prev_hash != prev_hash:
            return False
        if record.compute_hash() != record.hash:
            return False
        prev_hash = record.hash
    return True
