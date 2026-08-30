from tools.executor import SandboxedExecutor, ToolResult


def disassemble(file_path: str, executor: SandboxedExecutor) -> ToolResult:
    return executor.run(
        ["objdump", "-d", "-M", "intel", file_path],
        args={"file_path": file_path},
        tool_name="objdump",
    )


def run_radare2(file_path: str, commands: list[str], executor: SandboxedExecutor) -> ToolResult:
    cmd_str = "; ".join(commands)
    return executor.run(
        ["r2", "-q", "-c", cmd_str, file_path],
        args={"file_path": file_path, "commands": commands},
        tool_name="radare2",
    )


def find_rop_gadgets(file_path: str, executor: SandboxedExecutor) -> ToolResult:
    return executor.run(
        ["ROPgadget", "--binary", file_path],
        args={"file_path": file_path},
        tool_name="ROPgadget",
    )
