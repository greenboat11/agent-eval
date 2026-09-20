"""Structured results: JSON is the source of truth, markdown is rendered
from it, and pinned model versions come from the manifest.
"""

import json
from pathlib import Path

from agenteval.core.broker import CapabilityBroker
from agenteval.core.invariants import check_invariants
from agenteval.core.manifest import load_manifest
from agenteval.core.substrate import build_substrate
from agenteval.core.trace import TraceWriter, read_records, verify_chain
from agenteval.experiments.cascade import analyze_cascade, seed_cascade
from agenteval.experiments.results import build_run_result, render_markdown

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "manifests" / "example_population.yaml"


def test_run_result_round_trips_through_json(tmp_path):
    manifest = load_manifest(MANIFEST_PATH)
    trace_path = tmp_path / "run.jsonl"
    trace = TraceWriter(trace_path)
    broker = CapabilityBroker(manifest, trace)
    substrate = build_substrate(manifest.substrate)

    substrate["pkg-mirror"].write("specialist-a", broker, trace, "write_pkg_mirror", "payload-1", "x")
    substrate["pkg-mirror"].read("specialist-b", broker, trace, "exec_from_mirror", "payload-1")

    records = read_records(trace_path)
    assert verify_chain(records)
    violations = check_invariants(records, manifest.invariants)

    seed_cascade(substrate["scratch-registry"], broker, trace, "specialist-c",
                 "read_scratch", "seed-1", "value")
    records = read_records(trace_path)
    cascade = analyze_cascade(records, manifest, artifact_id="seed-1", seed_agent_id="specialist-c")

    result = build_run_result(
        run_id="test-run-1", manifest=manifest, manifest_path=str(MANIFEST_PATH),
        trace_path=str(trace_path), final_trace_hash=records[-1].hash,
        started_at="2026-01-01T00:00:00+00:00", ended_at="2026-01-01T00:01:00+00:00",
        violations=violations, seed=42, cascade_metrics=cascade,
    )

    out_path = tmp_path / "result.json"
    result.to_json(out_path)
    reloaded = json.loads(out_path.read_text(encoding="utf-8"))

    assert reloaded["run_id"] == "test-run-1"
    assert reloaded["seed"] == 42
    assert reloaded["model_versions"]["orchestrator"] == "claude-haiku-4-5-20251001"
    assert reloaded["cost_usd"] == {}  # no real model calls happened
    assert len(reloaded["violations"]) == 1
    assert reloaded["violations"][0]["composition_depth"] == 2
    assert reloaded["cascade_metrics"]["artifact_id"] == "seed-1"


def test_render_markdown_includes_all_sections(tmp_path):
    manifest = load_manifest(MANIFEST_PATH)
    trace_path = tmp_path / "run.jsonl"

    result = build_run_result(
        run_id="test-run-2", manifest=manifest, manifest_path=str(MANIFEST_PATH),
        trace_path=str(trace_path), final_trace_hash=None,
        started_at="2026-01-01T00:00:00+00:00", ended_at="2026-01-01T00:01:00+00:00",
        violations=[],
    )
    md = render_markdown(result)

    assert "# Run test-run-2" in md
    assert "## Model versions" in md
    assert "## Cost" in md
    assert "_No cost data recorded" in md
    assert "## Invariant violations" in md
    assert "_None detected._" in md
    assert "## Cascade metrics" in md
    assert "_No cascade seeded in this run._" in md
