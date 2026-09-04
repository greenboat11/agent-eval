#!/usr/bin/env python3
"""Add a challenge to CTFd via API. Usage: python scripts/create_challenge.py"""
import os

import click
import requests
from dotenv import load_dotenv

load_dotenv()


@click.command()
@click.option("--name", required=True)
@click.option("--description", required=True)
@click.option("--category", required=True,
              type=click.Choice(["recon", "web", "crypto", "forensics", "reversing", "pwn"]))
@click.option("--points", required=True, type=int)
@click.option("--flag", required=True, help="The correct flag, e.g. CTF{answer}")
def main(name, description, category, points, flag):
    url = os.environ["CTFD_URL"].rstrip("/")
    headers = {
        "Authorization": f"Token {os.environ['CTFD_TOKEN']}",
        "Content-Type": "application/json",
    }

    resp = requests.post(f"{url}/api/v1/challenges", headers=headers, json={
        "name": name, "description": description, "category": category,
        "value": points, "type": "standard", "state": "visible",
    })
    resp.raise_for_status()
    challenge_id = resp.json()["data"]["id"]

    requests.post(f"{url}/api/v1/flags", headers=headers, json={
        "challenge_id": challenge_id, "content": flag, "type": "static",
    }).raise_for_status()

    click.echo(f"Created challenge #{challenge_id}: {name}")


if __name__ == "__main__":
    main()
