import hashlib
import subprocess
import time
from dataclasses import dataclass


@dataclass
class ToolResult:
    tool_name: str
    args: dict
    output: str
    success: bool
    execution_hash: str
    duration_ms: int


class SandboxedExecutor:
    def __init__(self, timeout_seconds: int = 30, max_output_bytes: int = 65536):
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def run(self, command: list[str], args: dict, tool_name: str,
            env: dict | None = None) -> ToolResult:
        start = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=env,
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
