from tools.executor import SandboxedExecutor, ToolResult


def nmap_scan(target: str, ports: str, executor: SandboxedExecutor) -> ToolResult:
    return executor.run(
        ["nmap", "-p", ports, "--open", "-T4", target],
        args={"target": target, "ports": ports},
        tool_name="nmap",
    )


def whois_lookup(domain: str, executor: SandboxedExecutor) -> ToolResult:
    return executor.run(
        ["whois", domain],
        args={"domain": domain},
        tool_name="whois",
    )


def dns_lookup(domain: str, record_type: str, executor: SandboxedExecutor) -> ToolResult:
    return executor.run(
        ["dig", "+short", record_type, domain],
        args={"domain": domain, "record_type": record_type},
        tool_name="dig",
    )
