"""Task 3 containment: secrets, egress, budget caps, and the canary — see
docs/CONTAINMENT.md.
"""

import time

import pytest

from agenteval.core.broker import CanaryTripped, CapabilityBroker, PermissionDenied
from agenteval.core.budget import BudgetExceeded, RunBudget
from agenteval.core.egress import DENY_ALL, EgressDenied, EgressPolicy, normalize_host
from agenteval.core.manifest import (
    AgentSpec,
    CapabilityGrant,
    Generation,
    PopulationManifest,
)
from agenteval.core.secrets import (
    SecretNotFound,
    SecretStore,
    contains_canary,
    write_canary_env,
)
from agenteval.core.trace import CANARY_TRIP, TraceWriter


def _manifest():
    return PopulationManifest(
        generations=[Generation(id="gen-0", agents=[
            AgentSpec(
                id="orchestrator", model="x", token_budget=10,
                capabilities=[
                    CapabilityGrant("read_secret", "CTFD_TOKEN"),
                    CapabilityGrant("fetch_url"),
                ],
            ),
        ])],
        substrate=[], invariants=[],
    )


# --- SecretStore --------------------------------------------------------

def test_secret_store_loads_from_file(tmp_path):
    path = tmp_path / "secrets.env"
    path.write_text("CTFD_TOKEN=abc123\n# comment\nOPENROUTER_API_KEY=xyz\n")
    store = SecretStore.load(path)
    assert store.get("CTFD_TOKEN") == "abc123"
    assert store.get("OPENROUTER_API_KEY") == "xyz"


def test_secret_store_missing_raises():
    store = SecretStore({})
    with pytest.raises(SecretNotFound):
        store.get("NOPE")


def test_secret_store_falls_back_to_environ(monkeypatch):
    store = SecretStore({})
    monkeypatch.setenv("SOME_CI_SECRET", "from-environ")
    assert store.get_or_environ("SOME_CI_SECRET") == "from-environ"


# --- Canary --------------------------------------------------------------

def test_canary_written_and_detected(tmp_path):
    path = tmp_path / ".env"
    token = write_canary_env(path)
    content = path.read_text()
    assert contains_canary(content, token)
    assert not contains_canary("nothing to see here", token)


# --- Egress ----------------------------------------------------------------

def test_egress_default_deny_all():
    with pytest.raises(EgressDenied):
        DENY_ALL.check("example.com")


def test_egress_allowlist_permits_listed_host():
    policy = EgressPolicy(frozenset({"localhost"}))
    policy.check("localhost")  # no raise
    policy.check("http://localhost:8000/api")  # scheme/port stripped
    with pytest.raises(EgressDenied):
        policy.check("evil.example.com")


def test_normalize_host_strips_scheme_and_port():
    assert normalize_host("https://Example.com:443/path") == "example.com"


# --- Budget ------------------------------------------------------------

def test_budget_wall_clock_exceeded():
    budget = RunBudget(wall_clock_seconds=0.01, token_budgets={})
    time.sleep(0.02)
    with pytest.raises(BudgetExceeded):
        budget.check_wall_clock()


def test_budget_token_cap_enforced():
    budget = RunBudget(wall_clock_seconds=3600, token_budgets={"specialist-a": 100})
    budget.spend_tokens("specialist-a", 60)
    assert budget.remaining_tokens("specialist-a") == 40
    with pytest.raises(BudgetExceeded):
        budget.spend_tokens("specialist-a", 60)


def test_budget_ignores_agents_with_no_declared_cap():
    budget = RunBudget(wall_clock_seconds=3600, token_budgets={})
    budget.spend_tokens("untracked-agent", 10_000_000)  # no raise


# --- Broker integration --------------------------------------------------

def test_broker_get_secret_requires_grant(tmp_path):
    trace = TraceWriter(tmp_path / "run.jsonl")
    secrets = SecretStore({"CTFD_TOKEN": "real-token"})
    broker = CapabilityBroker(_manifest(), trace, secrets=secrets)

    assert broker.get_secret("orchestrator", "read_secret", "CTFD_TOKEN") == "real-token"

    with pytest.raises(PermissionDenied):
        broker.get_secret("orchestrator", "read_secret", "ANTHROPIC_API_KEY")  # not granted


def test_broker_get_secret_without_store_configured(tmp_path):
    trace = TraceWriter(tmp_path / "run.jsonl")
    broker = CapabilityBroker(_manifest(), trace)
    with pytest.raises(PermissionDenied):
        broker.get_secret("orchestrator", "read_secret", "CTFD_TOKEN")


def test_broker_egress_default_deny(tmp_path):
    trace = TraceWriter(tmp_path / "run.jsonl")
    broker = CapabilityBroker(_manifest(), trace)  # no egress policy passed -> deny-all
    with pytest.raises(EgressDenied):
        broker.check_egress("orchestrator", "fetch_url", "example.com")


def test_broker_egress_allowlisted(tmp_path):
    trace = TraceWriter(tmp_path / "run.jsonl")
    broker = CapabilityBroker(_manifest(), trace, egress=EgressPolicy(frozenset({"localhost"})))
    broker.check_egress("orchestrator", "fetch_url", "localhost")  # no raise


def test_broker_canary_trip_logs_critical_record(tmp_path):
    trace_path = tmp_path / "run.jsonl"
    trace = TraceWriter(trace_path)
    broker = CapabilityBroker(_manifest(), trace, canary_token="the-canary-token")

    with pytest.raises(CanaryTripped):
        broker.check_canary_leak("orchestrator", "output containing the-canary-token here")

    from agenteval.core.trace import read_records
    records = read_records(trace_path)
    assert any(r.record_type == CANARY_TRIP and r.payload["severity"] == "CRITICAL" for r in records)


def test_broker_canary_no_trip_on_clean_output(tmp_path):
    trace = TraceWriter(tmp_path / "run.jsonl")
    broker = CapabilityBroker(_manifest(), trace, canary_token="the-canary-token")
    broker.check_canary_leak("orchestrator", "perfectly normal tool output")  # no raise
