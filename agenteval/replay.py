"""CLI: python -m agenteval.replay --trace PATH --monitor NAME [--manifest PATH]

This is the only sanctioned way a monitor is ever run against a trace. See
agenteval/core/replay.py for the reusable function this wraps.
"""

import argparse
import dataclasses
import json
import sys

from agenteval.core.replay import replay
from agenteval.monitors import available_monitors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, help="path to a hash-chained trace JSONL file")
    parser.add_argument("--monitor", required=True, choices=available_monitors())
    parser.add_argument("--manifest", default=None, help="population manifest, for invariants")
    args = parser.parse_args()

    violations = replay(args.trace, args.monitor, args.manifest)
    json.dump([dataclasses.asdict(v) for v in violations], sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
