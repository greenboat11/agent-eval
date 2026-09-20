"""Cascade seeding: an artifact injected at one agent propagates through the
manifest's declared topology, and analyze_cascade recovers adoption
fraction, half-life, and the topology-aware downstream-adopters metric —
see agenteval/experiments/cascade.py for exact definitions.
"""

from agenteval.core.broker import CapabilityBroker
from agenteval.core.manifest import (
    AgentSpec,
    CapabilityGrant,
    Generation,
    PopulationManifest,
    SubstrateResourceSpec,
)
from agenteval.core.substrate import build_substrate
from agenteval.core.trace import TraceWriter, read_records
from agenteval.experiments.cascade import analyze_cascade, seed_cascade


def _chain_manifest():
    # seeder -> a -> b -> c, a straight-line topology so downstream counts
    # are easy to hand-verify.
    return PopulationManifest(
        generations=[Generation(id="gen-0", agents=[
            AgentSpec(id="seeder", model="x", token_budget=10, topology=["a"],
                      capabilities=[CapabilityGrant("write_reg", "reg")]),
            AgentSpec(id="a", model="x", token_budget=10, topology=["b"],
                      capabilities=[CapabilityGrant("read_reg", "reg")]),
            AgentSpec(id="b", model="x", token_budget=10, topology=["c"],
                      capabilities=[CapabilityGrant("read_reg", "reg")]),
            AgentSpec(id="c", model="x", token_budget=10, topology=[],
                      capabilities=[CapabilityGrant("read_reg", "reg")]),
        ])],
        substrate=[SubstrateResourceSpec(id="reg", kind="scratch_registry", zone=1)],
        invariants=[],
    )


def test_cascade_metrics_on_a_chain(tmp_path):
    manifest = _chain_manifest()
    trace_path = tmp_path / "run.jsonl"
    trace = TraceWriter(trace_path)
    broker = CapabilityBroker(manifest, trace)
    substrate = build_substrate(manifest.substrate)

    seed_cascade(substrate["reg"], broker, trace, "seeder", "write_reg", "payload-1", "value")

    # a, then b, then c each adopt in order.
    substrate["reg"].read("a", broker, trace, "read_reg", "payload-1")
    substrate["reg"].read("b", broker, trace, "read_reg", "payload-1")
    substrate["reg"].read("c", broker, trace, "read_reg", "payload-1")

    records = read_records(trace_path)
    metrics = analyze_cascade(records, manifest, artifact_id="payload-1", seed_agent_id="seeder")

    assert [e.agent_id for e in metrics.adopters] == ["a", "b", "c"]
    assert metrics.adoption_fraction == 1.0  # all 3 non-seeder agents adopted
    assert metrics.half_life_seconds is not None and metrics.half_life_seconds >= 0

    # topology is a straight chain: a's only neighbor is b, who adopted
    # after a (downstream=1); b's only neighbor is c, who adopted after b
    # (downstream=1); c has no neighbors (downstream=0). Mean = 2/3.
    assert abs(metrics.mean_downstream_adopters_per_adopter - (2 / 3)) < 1e-9


def test_cascade_with_no_adopters(tmp_path):
    manifest = _chain_manifest()
    trace_path = tmp_path / "run.jsonl"
    trace = TraceWriter(trace_path)
    broker = CapabilityBroker(manifest, trace)
    substrate = build_substrate(manifest.substrate)

    seed_cascade(substrate["reg"], broker, trace, "seeder", "write_reg", "lonely-payload", "value")

    records = read_records(trace_path)
    metrics = analyze_cascade(records, manifest, artifact_id="lonely-payload", seed_agent_id="seeder")

    assert metrics.adopters == []
    assert metrics.adoption_fraction == 0.0
    assert metrics.half_life_seconds is None
    assert metrics.mean_downstream_adopters_per_adopter == 0.0
