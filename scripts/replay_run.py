#!/usr/bin/env python3
"""Replay a past run from its bus log. Usage: make replay RUN=<run_id>"""
import json

import click
from pathlib import Path


@click.command()
@click.option("--run", required=True, help="Run ID to replay")
def main(run):
    log_path = Path("reports") / run / "bus.jsonl"
    if not log_path.exists():
        click.echo(f"No bus log found at {log_path}")
        raise SystemExit(1)

    messages = [json.loads(line) for line in log_path.read_text().strip().split("\n") if line]
    click.echo(f"Replaying {len(messages)} messages from run {run}\n")
    for msg in messages:
        ts = msg["timestamp"][:19]
        click.echo(f"[{ts}] {msg['sender']:12s} -> {msg['recipient']:12s}  {msg['message_type']}")
        if msg.get("content", {}).get("flag_candidate"):
            click.echo(f"           FLAG_CANDIDATE: {msg['content']['flag_candidate']}")


if __name__ == "__main__":
    main()
