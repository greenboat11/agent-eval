#!/usr/bin/env python3
"""Push all challenges from ctfd/challenges/ to a running CTFd instance."""
import os
from pathlib import Path

import click
import requests
import yaml
from dotenv import load_dotenv

load_dotenv()


@click.command()
@click.option("--ctfd-url", envvar="CTFD_URL", default="http://localhost:8000")
@click.option("--ctfd-token", envvar="CTFD_TOKEN", required=True)
@click.option("--challenges-dir", default="ctfd/challenges", type=click.Path())
def main(ctfd_url, ctfd_token, challenges_dir):
    url = ctfd_url.rstrip("/")
    headers = {
        "Authorization": f"Token {ctfd_token}",
        "Content-Type": "application/json",
    }

    challenges_path = Path(challenges_dir)
    challenge_dirs = [d for d in challenges_path.iterdir() if d.is_dir()]
    if not challenge_dirs:
        click.echo(f"No challenges found in {challenges_dir}")
        return

    for challenge_dir in sorted(challenge_dirs):
        spec_path = challenge_dir / "challenge.yml"
        if not spec_path.exists():
            click.echo(f"  Skipping {challenge_dir.name} — no challenge.yml")
            continue

        spec = yaml.safe_load(spec_path.read_text())

        resp = requests.post(f"{url}/api/v1/challenges", headers=headers, json={
            "name": spec["name"],
            "description": spec["description"],
            "category": spec["category"],
            "value": spec["value"],
            "type": spec.get("type", "standard"),
            "state": "visible",
        })
        if resp.status_code != 200:
            click.echo(f"  FAILED {spec['name']}: HTTP {resp.status_code} — {resp.text[:200]}")
            continue

        challenge_id = resp.json()["data"]["id"]

        for flag in spec.get("flags", []):
            requests.post(f"{url}/api/v1/flags", headers=headers, json={
                "challenge_id": challenge_id,
                "content": flag,
                "type": "static",
            }).raise_for_status()

        click.echo(f"  Created #{challenge_id}: {spec['name']} ({spec['category']}, {spec['value']} pts)")

    click.echo("Done.")


if __name__ == "__main__":
    main()
