import pytest
from unittest.mock import MagicMock
from tools.executor import SandboxedExecutor, ToolResult
from tools.recon import nmap_scan, whois_lookup, dns_lookup
from tools.web import http_get, http_post, parse_html
from tools.crypto import decrypt_caesar, decrypt_xor, frequency_analysis
from tools.forensics import run_strings, identify_file
from tools.reversing import disassemble, run_radare2, find_rop_gadgets
from tools.pwn import execute_python, shellcraft_generate


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


def test_nmap_scan_calls_executor(mocker):
    mock_executor = MagicMock()
    mock_executor.run.return_value = ToolResult(
        tool_name="nmap", args={}, output="open 80/tcp", success=True,
        execution_hash="abc123", duration_ms=100
    )
    result = nmap_scan("localhost", "80", mock_executor)
    mock_executor.run.assert_called_once()
    called_cmd = mock_executor.run.call_args[0][0]
    assert "nmap" in called_cmd
    assert "localhost" in called_cmd


def test_http_get_calls_executor(mocker):
    mock_executor = MagicMock()
    mock_executor.run.return_value = ToolResult(
        tool_name="curl", args={}, output="HTTP/1.1 200 OK\n<html>", success=True,
        execution_hash="def456", duration_ms=50
    )
    result = http_get("http://localhost/flag", {}, mock_executor)
    mock_executor.run.assert_called_once()
    called_cmd = mock_executor.run.call_args[0][0]
    assert "curl" in called_cmd or "http://localhost/flag" in " ".join(called_cmd)


def test_parse_html_extracts_tag():
    html = "<html><body><p class='flag'>CTF{test}</p></body></html>"
    result = parse_html(html, "p.flag")
    assert result.success is True
    assert "CTF{test}" in result.output


def test_parse_html_missing_selector():
    html = "<html><body></body></html>"
    result = parse_html(html, "p.flag")
    assert result.success is False


def test_decrypt_caesar_shift3():
    result = decrypt_caesar("Khoor", 3)
    assert result.success is True
    assert "Hello" in result.output


def test_decrypt_caesar_all_shifts_when_shift_zero():
    result = decrypt_caesar("Khoor", 0)
    assert result.success is True
    assert "Hello" in result.output


def test_decrypt_xor_basic():
    import binascii
    plaintext = b"flag"
    key = b"\x00"
    cipher_hex = binascii.hexlify(bytes(a ^ b for a, b in zip(plaintext, key * len(plaintext)))).decode()
    key_hex = binascii.hexlify(key).decode()
    result = decrypt_xor(cipher_hex, key_hex)
    assert result.success is True
    assert "flag" in result.output


def test_frequency_analysis_returns_sorted():
    result = frequency_analysis("aaabbc")
    assert result.success is True
    assert result.output.index("a") < result.output.index("b")


def test_run_strings_calls_executor(mocker):
    mock_executor = MagicMock()
    mock_executor.run.return_value = ToolResult(
        tool_name="strings", args={}, output="CTF{secret}", success=True,
        execution_hash="xyz", duration_ms=20
    )
    result = run_strings("/tmp/binary", 4, mock_executor)
    mock_executor.run.assert_called_once()
    assert "strings" in mock_executor.run.call_args[0][0]


def test_identify_file_calls_executor(mocker):
    mock_executor = MagicMock()
    mock_executor.run.return_value = ToolResult(
        tool_name="file", args={}, output="PNG image", success=True,
        execution_hash="abc", duration_ms=5
    )
    result = identify_file("/tmp/image.png", mock_executor)
    mock_executor.run.assert_called_once()


def test_disassemble_calls_executor(mocker):
    mock_executor = MagicMock()
    mock_executor.run.return_value = ToolResult(
        tool_name="objdump", args={}, output="push rbp", success=True,
        execution_hash="aaa", duration_ms=30
    )
    result = disassemble("/tmp/binary", mock_executor)
    mock_executor.run.assert_called_once()
    assert "objdump" in mock_executor.run.call_args[0][0]


def test_execute_python_runs_safe_code():
    mock_executor = MagicMock()
    mock_executor.run.return_value = ToolResult(
        tool_name="python3", args={}, output="42", success=True,
        execution_hash="bbb", duration_ms=100
    )
    result = execute_python("print(6*7)", mock_executor)
    mock_executor.run.assert_called_once()
    cmd = mock_executor.run.call_args[0][0]
    assert "python3" in cmd


def test_execute_python_blocks_import_os(mocker):
    mock_executor = MagicMock()
    result = execute_python("import os; os.system('rm -rf /')", mock_executor)
    mock_executor.run.assert_not_called()
    assert result.success is False
    assert "blocked" in result.output.lower()
