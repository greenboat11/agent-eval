#!/usr/bin/env python3
"""Analyze historical runs and suggest threshold calibration."""
import json

import click
from pathlib import Path


@click.command()
def main():
    reports_dir = Path("reports")
    runs = [d for d in reports_dir.iterdir() if d.is_dir()]
    if not runs:
        click.echo("No runs found in reports/")
        return

    elevations_per_run = []
    for run_dir in runs:
        ctrl_path = run_dir / "control_report.json"
        if not ctrl_path.exists():
            continue
        data = json.loads(ctrl_path.read_text())
        elevations_per_run.append(data["transition_count"])

    if not elevations_per_run:
        click.echo("No control reports found.")
        return

    avg = sum(elevations_per_run) / len(elevations_per_run)
    click.echo(f"Runs analyzed: {len(elevations_per_run)}")
    click.echo(f"Avg transitions per run: {avg:.1f}")
    if avg > 3:
        click.echo("Suggestion: thresholds may be too sensitive — consider raising volume_multiplier to 4.0")
    elif avg == 0:
        click.echo("Suggestion: thresholds may be too loose — consider lowering volume_multiplier to 2.0")
    else:
        click.echo("Thresholds appear well-calibrated.")


if __name__ == "__main__":
    main()
