import os
import uuid
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv

load_dotenv()


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

    from intake.challenge_fetcher import ChallengeFetcher
    from bus.message_bus import MessageBus
    from monitor.control_monitor import ControlMonitor
    from agents.specialists import SpecialistAgent
    from agents.orchestrator import OrchestratorAgent
    from submitter import FlagSubmitter
    from reports.capability import CapabilityReport
    from reports.control import ControlReport

    bus = MessageBus(run_id=run_id, log_path=report_dir / "bus.jsonl")
    monitor = ControlMonitor(cfg["monitor"])

    fetcher = ChallengeFetcher(
        os.environ["CTFD_URL"], os.environ["CTFD_TOKEN"], workspace
    )
    click.echo(f"[{run_id}] Fetching challenge {challenge}...")
    ctf_challenge = fetcher.fetch(challenge)

    openrouter_key = os.environ["OPENROUTER_API_KEY"]
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
        anthropic_key=os.environ["ANTHROPIC_API_KEY"],
        specialists=specialists,
        bus=bus,
        monitor=monitor,
        config=cfg["agents"]["orchestrator"],
    )

    click.echo(f"[{run_id}] Running challenge: {ctf_challenge.title}")
    result = orchestrator.run(ctf_challenge)

    submitter = FlagSubmitter(os.environ["CTFD_URL"], os.environ["CTFD_TOKEN"])
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
