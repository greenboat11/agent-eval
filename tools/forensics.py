from tools.executor import SandboxedExecutor, ToolResult


def run_strings(file_path: str, min_length: int, executor: SandboxedExecutor) -> ToolResult:
    return executor.run(
        ["strings", "-n", str(min_length), file_path],
        args={"file_path": file_path, "min_length": min_length},
        tool_name="strings",
    )


def run_binwalk(file_path: str, executor: SandboxedExecutor) -> ToolResult:
    return executor.run(
        ["binwalk", file_path],
        args={"file_path": file_path},
        tool_name="binwalk",
    )


def run_exiftool(file_path: str, executor: SandboxedExecutor) -> ToolResult:
    return executor.run(
        ["exiftool", file_path],
        args={"file_path": file_path},
        tool_name="exiftool",
    )


def identify_file(file_path: str, executor: SandboxedExecutor) -> ToolResult:
    return executor.run(
        ["file", file_path],
        args={"file_path": file_path},
        tool_name="file",
    )
