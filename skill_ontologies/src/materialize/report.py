"""Printed report: one function per table."""

from rdflib.namespace import RDF

from table_output import print_table

from .gateway_policy import applicable_rules, effective_mode
from .snapshot import Snapshot


def print_session(snap: Snapshot) -> None:
    f = snap.facts
    sess, group, config, agent = f["session"], f["group"], f["config"], f["onecli_agent"]
    policy = f["gateway_policy"]
    rules = applicable_rules(policy, agent["id"] if agent else None)
    permits = sum(p["scope"]["effect"] == "permit" for p in rules)
    _, evidence = effective_mode(policy)
    print_table("Session snapshot", ("Field", "Value"), [
        ("Session", sess["id"]),
        ("Agent group", f"{group['name']} ({group['id']})"),
        ("Other sessions in group", str(len(f["group_sessions"]) - 1)),
        ("Container", f["container_name"]),
        ("Provider", config.get("provider") or "claude"),
        ("cli_scope", snap.cli_scope),
        ("Egress lockdown", "on" if snap.lockdown_on else "off"),
        ("Destination grants", ", ".join(d["local_name"] for d in f["grants"]) or "none"),
        ("MCP servers (third-party)", ", ".join(config.get("mcp_servers") or {}) or "none"),
        ("Gateway identity", agent["identifier"] if agent else "none"),
        ("Granted credentials", ", ".join(f"{s['name']} ({s['hostPattern']})" for s in f["secrets"]) or "none"),
        ("Gateway policy", evidence),
        ("Cedar policies in scope", f"permit={permits}; forbid={len(rules) - permits}"),
        ("Claude tool lists", f"TOOL_ALLOWLIST={len(f['claude_tools']['allowlist'])}; SDK_DISALLOWED_TOOLS={len(f['claude_tools']['disallowed'])}"),
        ("Instances / triples", f"{len(set(snap.graph.subjects(RDF.type, None)))} / {len(snap.graph)}"),
    ], (26, 90))


COLUMNS = ("Resource", "Location", "Effects", "Via", "Status", "Gate")
WIDTHS = (32, 44, 18, 52, 11, 44)


def print_modifications(inside: list[tuple], outside: list[tuple], remote: list[tuple]) -> None:
    print_table("Inside the container: read or changed", COLUMNS, inside, WIDTHS)
    print_table("On the host, outside the container: read or changed", COLUMNS, outside, WIDTHS)
    print_table("Off this machine (remote): reached or changed", COLUMNS, remote, WIDTHS)


def print_findings(snap: Snapshot) -> None:
    if snap.findings:
        print("\nModel/runtime differences:")
        for item in snap.findings:
            print(f"  - {item}")


def print_report(snap: Snapshot, inside: list[tuple], outside: list[tuple], remote: list[tuple]) -> None:
    """Session header, the three effect tables (native and skill-operation rows), and model/runtime differences.

    Everything else (mounts, requirements, tools, capabilities, routes, Cedar
    policies) is recorded in the snapshot graph, not printed.
    """
    print_session(snap)
    print_modifications(inside, outside, remote)
    print_findings(snap)
