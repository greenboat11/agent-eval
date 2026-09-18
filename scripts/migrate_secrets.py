"""One-time, operator-run migration: move real secrets out of the repo-root
.env into the out-of-workspace location agenteval.core.secrets.SecretStore
reads from, then replace .env with a canary (see docs/CONTAINMENT.md).

Not run automatically by anything in this repo — the operator runs it once,
by hand, after reviewing what it does:

    python scripts/migrate_secrets.py

It refuses to run if the destination secrets file already exists, so it
can't silently clobber a previous migration.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agenteval.core.secrets import (
    DEFAULT_SECRETS_PATH,
    SECRETS_PATH_ENV_VAR,
    write_canary_env,
)

REPO_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def main() -> None:
    import os

    dest = Path(os.environ.get(SECRETS_PATH_ENV_VAR, DEFAULT_SECRETS_PATH))

    if not REPO_ENV_PATH.exists():
        print(f"no {REPO_ENV_PATH} found — nothing to migrate.")
        return

    if dest.exists():
        print(f"refusing to overwrite existing secrets file at {dest}")
        print("delete it first if you really mean to re-migrate.")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(REPO_ENV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    dest.chmod(0o600)
    print(f"copied {REPO_ENV_PATH} -> {dest}")

    token = write_canary_env(REPO_ENV_PATH)
    print(f"replaced {REPO_ENV_PATH} with a canary (token: {token[:8]}...)")
    print(f"set {SECRETS_PATH_ENV_VAR}={dest} if you don't want to rely on the default path.")


if __name__ == "__main__":
    main()
