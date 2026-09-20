"""python -m agenteval.dry_run is the project's own smoke test: no API calls,
but it exercises manifest -> cohort run -> trace -> replay -> results end to
end. This test pins down that it keeps reproducing the depth-2 demo.
"""

from agenteval.core.manifest import load_manifest
from agenteval.core.replay import replay
from agenteval.core.trace import TraceWriter, read_records
from agenteval.dry_run import DEFAULT_MANIFEST, scripted_agent
from agenteval.experiments.cohorts import CohortRunner


def test_dry_run_reproduces_the_depth_two_demo(tmp_path):
    manifest = load_manifest(DEFAULT_MANIFEST)
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceWriter(trace_path)
    CohortRunner(manifest, trace, wall_clock_seconds=60).run_all(scripted_agent)

    records = read_records(trace_path)
    assert len(records) > 0

    baseline_violations = replay(trace_path, "baseline_per_agent", DEFAULT_MANIFEST)
    compositional_violations = replay(trace_path, "compositional", DEFAULT_MANIFEST)

    assert baseline_violations == []
    assert len(compositional_violations) == 1
    assert compositional_violations[0].composition_depth == 2
