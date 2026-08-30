import hashlib
import time

from tools.executor import SandboxedExecutor, ToolResult

_BLOCKED_PATTERNS = ["import os", "import sys", "import subprocess", "__import__", "open("]


def _make_blocked_result(code: str) -> ToolResult:
    output = "[BLOCKED: dangerous import or syscall detected in code]"
    return ToolResult(
        tool_name="execute_python",
        args={"code": code[:200]},
        output=output,
        success=False,
        execution_hash=hashlib.sha256(output.encode()).hexdigest(),
        duration_ms=0,
    )


def execute_python(code: str, executor: SandboxedExecutor) -> ToolResult:
    for pattern in _BLOCKED_PATTERNS:
        if pattern in code:
            return _make_blocked_result(code)
    return executor.run(
        ["python3", "-c", code],
        args={"code": code[:200]},
        tool_name="python3",
    )


def shellcraft_generate(arch: str, os_: str, shellcode_type: str,
                        executor: SandboxedExecutor) -> ToolResult:
    code = (
        f"from pwn import shellcraft, asm, context; "
        f"context.arch='{arch}'; context.os='{os_}'; "
        f"print(asm(shellcraft.{shellcode_type}()).hex())"
    )
    return executor.run(
        ["python3", "-c", code],
        args={"arch": arch, "os": os_, "type": shellcode_type},
        tool_name="shellcraft",
    )
