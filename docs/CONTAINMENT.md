# Containment

**Status:** covers Task 3 of docs/adr/001-compositional-pivot.md.
**Scope:** what's implemented today, what's a policy object without an OS-level
backstop yet, and what's still a manual step. Read this before running any
agent against real credentials or a real network.

## Why this exists before any agent runs

The July 2026 OpenAI/Hugging Face incident (see ADR 001) didn't stay a
containment exercise — the pivot from "agents cheating on a benchmark" to
"agents doing something that reaches outside the benchmark" happened at the
moment an agent discovered a real credential. This project deliberately
manufactures the conditions for that discovery (agents with shell access,
package mirrors, scratch registries) in order to measure detection. That
means the actual live secrets, the actual network, and the actual host
filesystem have to be harder to reach than the manufactured ones, or the
experiment stops being an experiment.

## 1. Secrets live outside the agent-visible filesystem

**Problem:** the repo root previously held a `.env` file with live
`ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` / `CTFD_TOKEN` values, sitting in
the same directory tree any future filesystem-read or shell capability would
have access to.

**What's implemented:**
- `agenteval/core/secrets.py`: `SecretStore` loads from
  `$AGENTEVAL_SECRETS_PATH` (defaulting to `~/.agenteval/secrets.env`, i.e.
  outside the repo entirely), falling back to process environment variables
  for anything a file doesn't provide — so CI, which injects fake keys
  directly as env vars, is unaffected.
- `runner.py` loads secrets through `SecretStore` instead of
  `load_dotenv()` reading the repo-root `.env`.
- `agenteval/core/broker.py`: `CapabilityBroker.get_secret(agent_id,
  capability, secret_name)` is the only path a secret value is ever handed
  out programmatically. It requires an explicit manifest grant naming the
  secret as the resource — a manifest has to say, in YAML, which agent gets
  which credential. The trace records that the grant was used; it never
  records the value.
- `tools/executor.py`: `SandboxedExecutor` no longer passes the harness
  process's full environment to a spawned tool subprocess. Only an
  allowlist (`PATH`, `SYSTEMROOT`, `TEMP`, `TMP`, `HOME`, `USERPROFILE`)
  passes through by default; anything else has to be explicitly injected
  per call. Verified in `tests/test_containment.py` and manually (a value
  present in the harness's own environment does not reach a spawned
  subprocess unless explicitly passed).

**What's a manual step, deliberately:** this repo's actual `.env` currently
holds real keys. Nothing in this pass touches it automatically — a script
that moves live credentials shouldn't run without the operator watching it.
`scripts/migrate_secrets.py` does the move (copies `.env` to the
`SecretStore` path, chmods it `0600`, then replaces `.env` with the canary
below) and is meant to be run by hand:

```
python scripts/migrate_secrets.py
```

**What's still TODO:** the broker's secret-injection path isn't wired into
`tools/*.py` yet — those wrappers don't go through the broker at all in
this skeleton. That integration is explicitly deferred (see
`agenteval/core/broker.py`'s module docstring) rather than rushed ahead of
the agent roster that would actually exercise it.

## 2. Canary at the old `.env` path

Once real secrets are migrated out, the old path should never be silent —
if anything reads it, we want to know. `agenteval/core/secrets.py:
write_canary_env(path)` writes fake-looking values plus a random
`AGENTEVAL_CANARY_TOKEN`, and returns the token.

Detection is content-based, not filesystem-event-based: portable file-read
notification (inotify equivalents) isn't reliable across the Windows/Linux
split this project runs on, so the tripwire is
`CapabilityBroker.check_canary_leak(agent_id, text)` — called wherever tool
output, substrate reads, or messages become observable to the harness. If
the token appears anywhere in that text, the broker emits a `CANARY_TRIP`
trace record with `severity: CRITICAL` and raises immediately
(`CanaryTripped`). This means the canary only trips once its content
surfaces somewhere the harness is already watching — it will not catch a
read that never produces observable output, which is a real limitation, not
a hidden one.

**What's still TODO:** `check_canary_leak` isn't yet called automatically
from every tool-output ingestion point — that wiring lands with the Task 3
tool-wrapper broker integration mentioned above.

## 3. Egress: default-deny with an explicit allowlist

`agenteval/core/egress.py`: `EgressPolicy` is a policy object with a
`frozenset` allowlist of hosts. `CapabilityBroker` defaults to `DENY_ALL`
when no policy is supplied. `CapabilityBroker.check_egress(agent_id,
capability, target)` mediates any network-capable capability the same way
`.use()` mediates any other — it logs a grant-use record before checking
the policy, so a denied attempt is still in the trace.

**Never configure this with a live external target.** The allowlist in any
experiment manifest should only ever name the CTFd Docker service or
`localhost` — never a real host on the internet.

**What this is not:** `EgressPolicy` is a Python-level check the broker
performs when a capability wrapper chooses to call `check_egress`. It is
**not** an OS-level firewall — a tool subprocess that opens a raw socket
outside the broker's mediation is not stopped by this object today. The
actual backstop has to be the container/network layer (the existing
`Dockerfile` / `docker-compose.yml`), and hardening that — e.g. running tool
subprocesses in a network namespace with no route to the internet — is
tracked as a TODO, not claimed as done here.

## 4. Substrate credentials are synthetic

`agenteval/core/substrate.py`'s resources (`PackageMirror`,
`ScratchRegistry`, `SharedMount`, `DNSResolver`) are in-memory stubs with no
real network calls, real DNS resolution, or real filesystem mount — by
construction, not by configuration. There is currently nothing in the
codebase that could make a substrate resource resolve to a real host, so
there's no toggle to accidentally leave in the wrong position. If a future
substrate resource needs to model something closer to a real service (e.g.
an actual local Docker-network package registry for higher-fidelity runs),
it must still resolve only to a local mock — never a real upstream — and
that constraint should be re-stated in this document when it happens, not
assumed to carry over silently.

## 5. Wall-clock and token budget caps

`agenteval/core/budget.py`: `RunBudget` holds a wall-clock deadline and
per-agent token caps, set once at run start and never exposed to an agent.
`CapabilityBroker.use()` checks the wall-clock deadline on every mediated
capability use (i.e. on every broker-mediated action in the system, since
`.use()` is the common path `get_secret`/`check_egress`/substrate
read-write all go through). `RunBudget.spend_tokens(agent_id, n)` is
available for the orchestrator/specialist loop to call after each model
call; that wiring lands with the full agent roster (deferred, same as tool
integration above — see the Status table in README.md).

## Tiered release policy

- **Public:** the skeleton (this repo, minus real credentials), the ADR,
  this document, and trace corpora from runs against synthetic substrate
  and manufactured invariant violations. A trace is safe to publish once it
  has been checked for canary trips and contains no real credential
  material (traces never contain secret values by construction — see
  `broker.get_secret` above — but should still be spot-checked before
  release, since a tool's raw output could in principle echo something it
  shouldn't).
- **On request, not public by default:** configurations tuned to reliably
  elicit a specific high-yield behavior (e.g. a manifest + prompt
  combination that reliably produces a depth-2 violation with a
  particular real-world analog). These are useful to other safety
  researchers and risky as a how-to for anyone else; share them
  individually, to people who can be identified and who have a stated
  research purpose, not as a public artifact.

## Disclosure procedure

If a run ever produces something that would work against real
infrastructure — a technique, a credential-discovery path, an exploit
primitive that generalizes beyond this project's synthetic substrate — stop
the run, do not publish the trace or the manifest that produced it, and:

1. Preserve the trace and manifest privately (hash-chained, so their
   integrity is independently verifiable later) — do not delete them, and
   do not re-run the same configuration to "confirm" it outside a
   controlled setting.
2. Assess whether it discloses a vulnerability in a real, currently
   deployed system (as opposed to a generalizable technique with no
   specific real target). If it does, follow coordinated disclosure to the
   affected party before any public writeup, on whatever timeline
   responsible disclosure norms for that ecosystem call for.
3. If it's a generalizable technique rather than a specific system
   vulnerability, treat it as "on request" material (see above), not
   public-by-default, until there's been time to consider defensive
   writeups (e.g. to model providers or the AI safety community) getting
   ahead of a capability writeup.
4. When in doubt about which category something falls into, default to the
   more conservative option (private, on-request) until it's been reviewed
   by someone other than the person who ran the experiment.
