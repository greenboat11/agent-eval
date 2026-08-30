import hashlib
import json
import time

from bs4 import BeautifulSoup

from tools.executor import SandboxedExecutor, ToolResult


def http_get(url: str, headers: dict, executor: SandboxedExecutor) -> ToolResult:
    header_args = []
    for k, v in headers.items():
        header_args += ["-H", f"{k}: {v}"]
    return executor.run(
        ["curl", "-si", "--max-time", "15", *header_args, url],
        args={"url": url, "headers": headers},
        tool_name="curl_get",
    )


def http_post(url: str, data: dict, headers: dict, executor: SandboxedExecutor) -> ToolResult:
    header_args = []
    for k, v in headers.items():
        header_args += ["-H", f"{k}: {v}"]
    return executor.run(
        ["curl", "-si", "-X", "POST", "-d", json.dumps(data),
         "-H", "Content-Type: application/json", *header_args, url],
        args={"url": url, "data": data},
        tool_name="curl_post",
    )


def parse_html(html: str, selector: str) -> ToolResult:
    start = time.monotonic()
    try:
        soup = BeautifulSoup(html, "html.parser")
        elements = soup.select(selector)
        if not elements:
            output = f"[NO MATCH for selector '{selector}']"
            success = False
        else:
            output = "\n".join(el.get_text(strip=True) for el in elements)
            success = True
    except Exception as exc:
        output = f"[ERROR: {exc}]"
        success = False

    duration_ms = int((time.monotonic() - start) * 1000)
    return ToolResult(
        tool_name="parse_html",
        args={"selector": selector},
        output=output,
        success=success,
        execution_hash=hashlib.sha256(output.encode()).hexdigest(),
        duration_ms=duration_ms,
    )
