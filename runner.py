import uuid
from pathlib import Path

import click
import yaml

from agenteval.core.secrets import SecretStore


@click.command()
@click.option("--challenge", required=True, type=int, help="CTFd challenge ID")
@click.option("--config", default="config.yaml", help="Config file path")
@click.option("--halt-on-critical", is_flag=True, default=False)
def main(challenge: int, config: str, halt_on_critical: bool):
    cfg = yaml.safe_load(Path(config).read_text())
    if halt_on_critical:
        cfg["monitor"]["halt_on_critical"] = True

    run_id = str(uuid.uuid4())[:8]
    workspace = Path("workspace") / run_id
    report_dir = Path("reports") / run_id
    workspace.mkdir(parents=True, exist_ok=True)

    from agenteval.monitors.baseline_per_agent import ControlMonitor
    from agents.orchestrator import OrchestratorAgent
    from agents.specialists import SpecialistAgent
    from bus.message_bus import MessageBus
    from intake.challenge_fetcher import ChallengeFetcher
    from reports.capability import CapabilityReport
    from reports.control import ControlReport
    from submitter import FlagSubmitter

    bus = MessageBus(run_id=run_id, log_path=report_dir / "bus.jsonl")
    monitor = ControlMonitor(cfg["monitor"])

    # Secrets are loaded from outside the repo (see docs/CONTAINMENT.md,
    # agenteval/core/secrets.py) — never from a .env sitting in the
    # workspace an agent's tools might one day be able to read. Falls back
    # to process env so CI (which injects fake keys as env vars) is unaffected.
    secrets = SecretStore.load()

    fetcher = ChallengeFetcher(
        secrets.get_or_environ("CTFD_URL"), secrets.get_or_environ("CTFD_TOKEN"), workspace
    )
    click.echo(f"[{run_id}] Fetching challenge {challenge}...")
    ctf_challenge = fetcher.fetch(challenge)

    openrouter_key = secrets.get_or_environ("OPENROUTER_API_KEY")
    spec_cfg = cfg["agents"]["specialists"]
    specialists = {
        role: SpecialistAgent(
            role=role,
            model=spec_cfg[role]["model"],
            openrouter_key=openrouter_key,
            tools=[],
            bus=bus,
            max_tokens=spec_cfg[role]["max_tokens"],
        )
        for role in spec_cfg
    }

    orchestrator = OrchestratorAgent(
        model=cfg["agents"]["orchestrator"]["model"],
        anthropic_key=secrets.get_or_environ("ANTHROPIC_API_KEY"),
        specialists=specialists,
        bus=bus,
        monitor=monitor,
        config=cfg["agents"]["orchestrator"],
    )

    click.echo(f"[{run_id}] Running challenge: {ctf_challenge.title}")
    result = orchestrator.run(ctf_challenge)

    submitter = FlagSubmitter(secrets.get_or_environ("CTFD_URL"), secrets.get_or_environ("CTFD_TOKEN"))
    submission = None
    if result.get("flag_candidate"):
        flag = result["flag_candidate"]
        if submitter.validate(flag, ctf_challenge.flag_format):
            submission = submitter.submit(challenge, flag, result.get("solving_agent", "unknown"))
            click.echo(f"[{run_id}] Submitted: {submission['status']}")
        else:
            click.echo(f"[{run_id}] Flag failed format validation: {flag}")

    result["submission"] = submission
    cap = CapabilityReport(ctf_challenge, bus.get_log(), result)
    ctrl = ControlReport(monitor.get_transitions(), monitor.get_state())
    cap_path = cap.generate(report_dir)
    ctrl_path = ctrl.generate(report_dir)

    click.echo(f"[{run_id}] Reports written to {report_dir}/")
    click.echo(f"  Capability: {cap_path}")
    click.echo(f"  Control:    {ctrl_path}")
    click.echo(f"  Solved: {result.get('solved')} | State: {result.get('control_state')}")


if __name__ == "__main__":
    main()
