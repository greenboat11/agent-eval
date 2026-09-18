import hashlib
import os
import subprocess
import time
from dataclasses import dataclass

# Subprocess env is never inherited wholesale from the harness process — see
# docs/CONTAINMENT.md. If secrets are ever loaded into the harness's own
# environment, a tool subprocess must not receive them for free just because
# it's a child process. Only these names pass through by default; anything a
# specific tool call actually needs (e.g. a broker-injected credential) must
# be passed explicitly via the `env` argument to .run().
DEFAULT_ENV_ALLOWLIST = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE")


@dataclass
class ToolResult:
    tool_name: str
    args: dict
    output: str
    success: bool
    execution_hash: str
    duration_ms: int


class SandboxedExecutor:
    def __init__(self, timeout_seconds: int = 30, max_output_bytes: int = 65536,
                 env_allowlist: tuple[str, ...] = DEFAULT_ENV_ALLOWLIST):
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.env_allowlist = env_allowlist

    def _build_env(self, explicit_env: dict | None) -> dict:
        base = {k: os.environ[k] for k in self.env_allowlist if k in os.environ}
        if explicit_env:
            base.update(explicit_env)
        return base

    def run(self, command: list[str], args: dict, tool_name: str,
            env: dict | None = None) -> ToolResult:
        start = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=self._build_env(env),
            )
            raw_output = proc.stdout + proc.stderr
            success = proc.returncode == 0
        except subprocess.TimeoutExpired:
            raw_output = f"[TIMEOUT after {self.timeout_seconds}s]"
            success = False
        except Exception as exc:
            raw_output = f"[ERROR: {exc}]"
            success = False

        duration_ms = int((time.monotonic() - start) * 1000)
        output = self._truncate(raw_output)
        execution_hash = hashlib.sha256(output.encode()).hexdigest()

        return ToolResult(
            tool_name=tool_name,
            args=args,
            output=output,
            success=success,
            execution_hash=execution_hash,
            duration_ms=duration_ms,
        )

    def _truncate(self, text: str) -> str:
        encoded = text.encode()
        if len(encoded) <= self.max_output_bytes:
            return text
        return encoded[: self.max_output_bytes].decode(errors="replace") + "[TRUNCATED]"
