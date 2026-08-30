import pytest
from tools.executor import SandboxedExecutor, ToolResult


def test_executor_runs_command_successfully():
    executor = SandboxedExecutor(timeout_seconds=5, max_output_bytes=65536)
    result = executor.run(["echo", "hello"], args={}, tool_name="echo")
    assert result.success is True
    assert "hello" in result.output
    assert result.tool_name == "echo"
    assert result.duration_ms >= 0


def test_executor_captures_failure():
    executor = SandboxedExecutor(timeout_seconds=5, max_output_bytes=65536)
    result = executor.run(["false"], args={}, tool_name="false_cmd")
    assert result.success is False


def test_executor_times_out():
    executor = SandboxedExecutor(timeout_seconds=1, max_output_bytes=65536)
    result = executor.run(["sleep", "10"], args={}, tool_name="sleep")
    assert result.success is False
    assert "timeout" in result.output.lower()


def test_executor_truncates_large_output():
    executor = SandboxedExecutor(timeout_seconds=5, max_output_bytes=10)
    result = executor.run(["python3", "-c", "print('A' * 1000)"], args={}, tool_name="python3")
    assert len(result.output) <= 10 + len("[TRUNCATED]")


def test_executor_hash_is_deterministic():
    executor = SandboxedExecutor(timeout_seconds=5, max_output_bytes=65536)
    r1 = executor.run(["echo", "same"], args={}, tool_name="echo")
    r2 = executor.run(["echo", "same"], args={}, tool_name="echo")
    assert r1.execution_hash == r2.execution_hash


def test_executor_different_output_different_hash():
    executor = SandboxedExecutor(timeout_seconds=5, max_output_bytes=65536)
    r1 = executor.run(["echo", "foo"], args={}, tool_name="echo")
    r2 = executor.run(["echo", "bar"], args={}, tool_name="echo")
    assert r1.execution_hash != r2.execution_hash
