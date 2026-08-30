import binascii
import hashlib
import time
from collections import Counter

from tools.executor import SandboxedExecutor, ToolResult


def _make_result(tool_name: str, args: dict, output: str, success: bool, start: float) -> ToolResult:
    duration_ms = int((time.monotonic() - start) * 1000)
    return ToolResult(
        tool_name=tool_name,
        args=args,
        output=output,
        success=success,
        execution_hash=hashlib.sha256(output.encode()).hexdigest(),
        duration_ms=duration_ms,
    )


def decrypt_caesar(ciphertext: str, shift: int) -> ToolResult:
    start = time.monotonic()
    shifts = [shift] if shift != 0 else list(range(1, 26))
    results = []
    for s in shifts:
        decoded = ""
        for ch in ciphertext:
            if ch.isalpha():
                base = ord('A') if ch.isupper() else ord('a')
                decoded += chr((ord(ch) - base - s) % 26 + base)
            else:
                decoded += ch
        results.append(f"shift={s}: {decoded}")
    output = "\n".join(results)
    return _make_result("caesar", {"ciphertext": ciphertext, "shift": shift}, output, True, start)


def decrypt_xor(hex_ciphertext: str, hex_key: str) -> ToolResult:
    start = time.monotonic()
    try:
        cipher = binascii.unhexlify(hex_ciphertext)
        key = binascii.unhexlify(hex_key)
        plain = bytes(a ^ key[i % len(key)] for i, a in enumerate(cipher))
        output = plain.decode(errors="replace")
        return _make_result("xor", {"hex_ciphertext": hex_ciphertext, "hex_key": hex_key}, output, True, start)
    except Exception as exc:
        return _make_result("xor", {}, f"[ERROR: {exc}]", False, start)


def frequency_analysis(text: str) -> ToolResult:
    start = time.monotonic()
    letters = [ch.lower() for ch in text if ch.isalpha()]
    counts = Counter(letters)
    sorted_chars = sorted(counts.items(), key=lambda x: -x[1])
    output = "\n".join(f"{ch}: {count}" for ch, count in sorted_chars)
    return _make_result("freq_analysis", {"text": text[:100]}, output, True, start)


def hash_crack(hash_str: str, wordlist_path: str, executor: SandboxedExecutor) -> ToolResult:
    return executor.run(
        ["hashcat", "--force", "-a", "0", hash_str, wordlist_path],
        args={"hash": hash_str, "wordlist": wordlist_path},
        tool_name="hashcat",
    )
