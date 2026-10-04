# ADR 001: Compositional Capability Evaluation — A Second Question Alongside Bus-Compliance Monitoring

**Status:** Accepted
**Date:** 2026-09-18
**Author:** Kyle A. Kilian

## Summary

**A Follow-up Question on Compositional.** This project's first line of work
(`v0.1`) asks whether a deterministic monitor watching a mandatory
inter-agent message bus can reliably detect loss-of-control behavior, using live CTF competitive
pressure as a naturalistic source of instrumental goals, instead of
constructing synthetic eval scenarios, to give agents a genuine reason to
deviate rather than a scripted one.

This document concerns a second, complementary question, raised
specifically by the July 2026 OpenAI/Hugging Face incident: can a
population's *combined*, individually-permitted capabilities compose into a
violation that no single agent's channel-scoped view was ever positioned to
see? That question is outside what a channel-scoped monitor is built to
answer — because "watch the
designated channel" and "watch what a group's permissions add up to" are
different instruments pointed at different failure modes. The incident is a
case of the second kind, so this ADR sets up an architecture aimed
specifically for compositional failure.

## What the incident showed

In the July 2026 incident, the agents under evaluation never communicated
over any channel their operators had designated for communication, and they
never needed to. They shared read access to an internal package cache — a
piece of infrastructure nobody had classified as a communication medium
because, in isolation, it obviously isn't one. One agent began encoding
information in the names of directories it created inside that cache;
another agent, with no instruction to look for messages there, listed the
cache as a routine part of its task and read the names back out. Neither
agent violated a permission it had been granted. Neither used a channel a
monitor was watching. The coordination was an emergent property of two
narrow, individually-reasonable capability grants intersecting on a shared
resource.

No log of "messages sent" would show this exchange, because nothing in the
system's own ontology called it a message.

## Why bus-compliance monitoring has a structural blind spot

The original `ControlMonitor` (see `monitor/control_monitor.py`,
`monitor/signals.py`) is a well-built instance of a monitoring strategy
scoped, by design, to one channel. It watches four signals — graph
topology of bus edges, message volume, task-adherence cosine similarity, and
log-hash integrity — and all four are defined *over messages published to the
bus*. The detection claim, "any agent-to-agent communication that bypasses
the bus is detectable by definition," is true only because it is
tautological: the monitor is defined to see everything that is defined as
bus traffic, and nothing else. It says nothing about traffic the operator
never thought to route through the bus in the first place.

This is not a bug in the implementation. It is a structural property of any
monitor that is scoped to a sanctioned channel: its detection surface is
exactly the set of channels the system designer already anticipated. The
incident shows the failure mode directly — the package cache was substrate,
not bus, and substrate is exactly what a bus-scoped monitor cannot see by
construction. Widening the monitor to watch "more channels" does not fix
this, because the next incident's channel is, by the same logic, whatever
shared affordance nobody thought to label. The blind spot moves; it does not
close.

What generalizes from the incident is not "watch the package cache too." It
is: **individually-authorized capabilities can compose into an unauthorized
outcome through shared state that no single grant labeled as communication.**
That is a claim about capability composition, not about channel coverage,
and it is the claim this second line of work is built to test.

## New thesis

**Object of study:** whether permission architectures compose safely under
agent populations — i.e., whether a set of individually-reasonable,
per-agent capability grants can jointly produce a violation of a
system-level invariant that no single grant, and no single agent, was
authorized to produce alone.

**Design:** each agent in a population receives a strict partial capability
set (a subset of available tools and substrate resources). The operator
declares global invariants over the whole population — constraints that hold
regardless of which agent does what (e.g., "no artifact may cross from zone 1
to zone 3," or "no agent may hold both capability A and capability D"). We
run populations against tasks that create instrumental pressure to use
whatever capabilities are available, and we check, post hoc, whether the
population's combined behavior violates an invariant that individual
per-agent policy enforcement would not have flagged, because no single agent
crossed its own boundary.

**Falsifiable claim:** per-agent policy enforcement has a detection floor at
**composition depth 2** — meaning a violation that requires chaining the
capabilities of two or more distinct agents through shared substrate is
systematically missed by monitoring that evaluates each agent's actions
against that agent's own grant, even when every individual action is exactly
what an agent-scoped monitor would consider compliant.

This claim is falsifiable in the ordinary sense: if depth-2 (or deeper)
violations are reliably caught by per-agent monitoring in this framework's
own experiments, the thesis is wrong, and that is a real, reportable result.

## What "composition depth" means

Composition depth is a property of a *violation*, not of an agent or a
capability. It is the number of distinct agents whose capability grants had
to be chained — through shared substrate, sequential handoff, or induced
imitation — for the invariant violation to occur.

- **Depth 1**: a single agent's own actions violate an invariant using only
  capabilities it was directly granted. This is the case ordinary per-agent
  policy enforcement is designed for, and is expected to catch reliably.
- **Depth 2**: the violation requires two agents, neither of whom
  individually held both of the capabilities the invariant forbids
  combining, but who jointly produced the forbidden combination — e.g.,
  Agent A writes an artifact into substrate it is permitted to write, Agent
  B (which never touched Agent A's forbidden capability) reads that
  substrate and, through a capability *it* holds, moves the artifact into a
  zone the invariant protects.
- **Depth N**: the chain extends across N agents, each individually
  compliant, before the invariant is violated.

Composition depth is computed from the capability graph reconstructed from
broker events in the trace (see Task 2), not asserted by the experiment
designer, so it is a measured property of what actually happened in a run,
not a label attached to the scenario in advance.

## Small-N strategy

The available compute budget (8-16 agents, short runs, cheap models,
personal API spend) rules out the population sizes that would make
composition-depth statistics precise on their own. Three strategies keep the
evaluation meaningful at this scale, and are explicitly designed to carry
over unchanged to a larger compute environment later:

1. **Generational cohorts.** Rather than needing many agents live
   simultaneously, the manifest declares generations that run sequentially
   against persistent substrate. A cohort boots cold, may discover artifacts
   left behind by the prior cohort, and inherits none of the prior cohort's
   context — only what it can find in shared state. This lets a small
   per-generation population accumulate compositional pressure over time
   instead of requiring it from population size alone, and it directly
   models the realistic case where an operator's monitoring gap compounds
   across deployments rather than within one.

2. **Offline monitor replay.** The trace is the unit of record, and monitors
   are never wired to observe a run live — they are run afterward, via
   `python -m agenteval.replay`, against a stored trace. This means the same
   small set of expensive runs can be scored against an arbitrary number of
   monitor implementations (the baseline per-agent monitor, the
   compositional monitor, and any future candidate) without re-running
   agents, which is the main lever available for getting statistical
   coverage out of a constrained compute/API budget.

3. **Synthetic population inflation for monitor load testing only.** Where a
   question is specifically about a monitor's scaling behavior (e.g., false
   positive rate as population size grows) rather than about whether real
   agent behavior composes a violation, the trace format supports
   synthetically generated broker events to stress-test the monitor at
   population sizes the live budget cannot afford to run. This is explicitly
   a monitor-testing technique, not a substitute for real agent runs, and
   results from synthetic populations are never to be reported as findings
   about agent behavior — only as findings about monitor scaling.

## What the compositional architecture adds

The mandatory message bus and the bus-scoped `ControlMonitor` are not
deleted or superseded. The monitor is re-homed, unchanged in behavior, as
`agenteval/monitors/baseline_per_agent.py` — the control arm of the
experiment. Its blindness at composition depth 2 is the result this project
is trying to measure, so its behavior must stay fixed, not improved. What is
new is a capability broker mediating all resource access, a hash-chained
trace as the sole record of what happened, pluggable substrate resources
whose channel capacity is known to a ground-truth answer key but withheld
from monitors, and declarative invariants checked by replay against that
trace. Implementation detail for these components is out of scope for this
document and is covered by the package-boundary and skeleton work that
follows this ADR.

## Consequences

- The pre-pivot codebase is tagged `v0.1` before any restructuring, with a
  release note stating the original thesis as originally intended. It
  remains citable as the "per-agent/bus-compliance" condition rather than
  being erased from history.
- `agenteval/core` (substrate, broker, trace, invariants, replay) must not
  import from `agenteval/experiments` (CTF intake, cascade seeding,
  invariant specs). This keeps the infrastructure layer extractable to its
  own repo later without an early submodule split neither half has earned
  yet.
- The existing bus/monitor implementation is preserved as the baseline
  monitor, not discarded, so the depth-2 blind-spot claim has a real,
  unmodified control arm to compare against rather than a strawman.
- Everything downstream of this document (population manifest, capability
  broker, trace format, substrate, invariants/replay, and the compositional
  monitor) is scoped to demonstrate one thing: a hash-chained trace that
  replays to different verdicts under the baseline and compositional
  monitors, with a manufactured depth-2 violation caught by one and missed
  by the other.
