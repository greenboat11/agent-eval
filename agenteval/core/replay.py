"""Replay logic: load a trace, run one named monitor against it. The harness
never calls a monitor directly — this function (and the CLI in
agenteval/replay.py) is the only path a monitor is ever invoked through.
"""

from pathlib import Path

from agenteval.core.invariants import Violation
from agenteval.core.manifest import PopulationManifest, load_manifest
from agenteval.core.trace import read_records, verify_chain
from agenteval.monitors import get_monitor


class TraceIntegrityError(RuntimeError):
    pass


def replay(trace_path: Path, monitor_name: str, manifest_path: Path | None = None) -> list[Violation]:
    records = read_records(trace_path)
    if not verify_chain(records):
        raise TraceIntegrityError(f"hash chain verification failed for {trace_path}")

    invariants = []
    if manifest_path is not None:
        manifest: PopulationManifest = load_manifest(manifest_path)
        invariants = manifest.invariants

    monitor = get_monitor(monitor_name)
    return monitor.evaluate(records, invariants)
