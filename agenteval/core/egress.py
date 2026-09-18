"""Default-deny egress policy. This is a policy object checked at the broker
layer, not a network-level enforcement mechanism — the actual backstop is
OS/container-level (see docs/CONTAINMENT.md, tracked as a TODO alongside the
Dockerfile). Never configure this with a live external target.
"""

from urllib.parse import urlparse


class EgressDenied(PermissionError):
    pass


def normalize_host(target: str) -> str:
    if "://" in target:
        target = urlparse(target).hostname or target
    return target.split(":")[0].strip().lower()


class EgressPolicy:
    def __init__(self, allowlist: frozenset[str] = frozenset()):
        self._allowlist = {normalize_host(h) for h in allowlist}

    def check(self, target: str) -> None:
        host = normalize_host(target)
        if host not in self._allowlist:
            raise EgressDenied(f"egress to {host!r} denied (not in allowlist)")


DENY_ALL = EgressPolicy(frozenset())
