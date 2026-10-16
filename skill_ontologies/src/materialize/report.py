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
        ("Container skills", ", ".join(f["container_skills"]) or "none"),
        ("Skills without ontology", ", ".join(n for n in f["container_skills"] if n not in f.get("modeled_skills", [])) or "none"),
        ("MCP servers (third-party)", ", ".join(config.get("mcp_servers") or {}) or "none"),
        ("MCP servers without ontology", ", ".join(n for n in config.get("mcp_servers") or {} if n not in f.get("modeled_mcp", {})) or "none"),
        ("Gateway identity", agent["identifier"] if agent else "none"),
        ("Granted credentials", ", ".join(f"{s['name']} ({s['hostPattern']})" for s in f["secrets"]) or "none"),
        ("Gateway policy", evidence),
        ("Cedar policies in scope", f"permit={permits}; forbid={len(rules) - permits}"),
        ("Claude tool lists", f"TOOL_ALLOWLIST={len(f['claude_tools']['allowlist'])}; SDK_DISALLOWED_TOOLS={len(f['claude_tools']['disallowed'])}"),
        ("Instances / triples", f"{len(set(snap.graph.subjects(RDF.type, None)))} / {len(snap.graph)}"),
    ], (26, 90))


COLUMNS = ("Resource", "Location", "Effects", "Via", "Status", "Gate")
WIDTHS = (32, 44, 18, 52, 11, 44)


REMOTE_COLUMNS = ("Endpoint", "What can happen there", "Route", "Status", "Gate")
REMOTE_WIDTHS = (60, 66, 44, 11, 40)


def parse_via(cell: str) -> tuple[list[str], list[str]]:
    """(labels, routes) of a via cell: label lines ("<tool or operation>:") each followed by
    an indented route, or "<label>: <route>" on one line."""
    labels, routes, body = [], [], []

    def flush() -> None:
        if body:
            routes.append("\n".join(body))
            body.clear()

    for line in cell.splitlines():
        if line.startswith(" "):
            body.append(line[2:])
            continue
        flush()
        if line.endswith(":"):
            labels.append(line[:-1])
        elif ": " in line:
            head, tail = line.split(": ", 1)
            labels.append(head)
            body.append(tail)
        else:
            labels.append(line)
    flush()
    return labels, routes


def union_gates(gates: list[str]) -> str:
    """Facts (one per line, deduplicated) followed by the union of the controls."""
    facts, controls = [], set()
    for g in gates:
        in_controls = False
        for line in g.splitlines():
            text = line.strip()
            if text in ("-", "") or (text.startswith("[") and text.endswith("]")):
                continue
            if text == "controls:":
                in_controls = True
            elif in_controls and line.startswith("  ") and ":" not in text:
                controls.add(text)
            else:
                in_controls = False
                if text not in facts:
                    facts.append(text)
    lines = facts + (["controls:"] + [f"  {c}" for c in sorted(controls)] if controls else [])
    return "\n".join(lines) or "-"


def endpoint_key(location: str) -> tuple[str, str]:
    """(row key, qualifier): the Cedar policy entry when the location names one (any host
    above it becomes the qualifier), else the whole location."""
    lines = location.splitlines()
    cedar = [l for l in lines if l.startswith("cedar: ")]
    if cedar:
        return cedar[0], ", ".join(l for l in lines if not l.startswith("cedar: "))
    return location, ""


def merge_routes(routes: list[str]) -> list[str]:
    """Routes sharing everything after their first step: the first steps listed together
    over one copy of the shared tail."""
    tails: dict[str, list[str]] = {}
    for r in routes:
        head, _, tail = r.partition("\n")
        tails.setdefault(tail, [])
        if head not in tails[tail]:
            tails[tail].append(head)
    return [", ".join(heads) + (f"\n{tail}" if tail else "") for tail, heads in tails.items()]


def by_endpoint(rows: list[tuple], policy_text: dict[str, str] | None = None) -> list[tuple]:
    """One row per endpoint (the Cedar policy entry a gateway path passes, else the
    location: a destination, "*", "-"): every resource reached there with its effects,
    the host when one is known, and the tools or operations doing it; each distinct
    route once; the statuses; and the union of the gates. A Cedar endpoint shows the
    policy entry's code verbatim under its name."""
    groups: dict[str, list[tuple]] = {}
    for row in rows:
        groups.setdefault(endpoint_key(row[1])[0], []).append(row)
    out = []
    for where, items in groups.items():
        statuses = list(dict.fromkeys(st for r in items for st in r[4].splitlines()))
        what: dict[tuple[str, str], set[str]] = {}
        effects: dict[tuple[str, str], set[str]] = {}
        routes: list[str] = []
        for res, loc, eff, via, status, _gate in items:
            labels, paths = parse_via(via)
            host = endpoint_key(loc)[1]
            key = (res.strip(" └") + (f" @ {host}" if host else ""), status.replace("\n", ", "))
            what.setdefault(key, set()).update(labels)
            effects.setdefault(key, set()).update(e.strip() for e in eff.split(",") if e.strip())
            routes += [p for p in paths if p not in routes]
        lines = []
        for (res, status), labels in sorted(what.items()):
            tag = f"  [{status}]" if len(statuses) > 1 else ""
            lines.append(f"{', '.join(sorted(effects[(res, status)]))} · {res}{tag}")
            lines.append(f"  via {', '.join(sorted(labels))}")
        name = where[len("cedar: "):] if where.startswith("cedar: ") else None
        code = (policy_text or {}).get(name or "")
        endpoint = f"{where}\n" + "\n".join("  " + l for l in code.strip().splitlines()) if code else where
        out.append((endpoint, "\n".join(lines), "\n".join(merge_routes(routes)) or "-", "\n".join(statuses), union_gates([r[5] for r in items])))
    return sorted(out, key=lambda r: (not r[0].startswith("cedar: "), r[0]))


def print_modifications(snap: Snapshot, inside: list[tuple], outside: list[tuple], remote: list[tuple]) -> None:
    print_table("Inside the container: read or changed", COLUMNS, inside, WIDTHS)
    print_table("On the host, outside the container: read or changed", COLUMNS, outside, WIDTHS)
    policy = snap.facts["gateway_policy"] or {}
    texts = {p["name"]: p["text"] for p in policy.get("policies", [])}
    print_table("Off this machine (remote): what can happen at each endpoint", REMOTE_COLUMNS, by_endpoint(remote, texts), REMOTE_WIDTHS)


def print_findings(snap: Snapshot) -> None:
    if snap.findings:
        print("\nModel/runtime differences:")
        for item in snap.findings:
            print(f"  - {item}")


def print_downstream(rows: list[tuple]) -> None:
    print_table("Downstream in remote environments: what the remote effects may set off, and how",
                ("Resource", "Influence", "Path (shortest per effect)", "Started by", "Status"), rows, (30, 22, 90, 50, 11))


def print_report(snap: Snapshot, inside: list[tuple], outside: list[tuple], remote: list[tuple], downstream: list[tuple] = ()) -> None:
    """Session header, the three effect tables (native and skill-operation rows), and model/runtime differences.

    Everything else (mounts, requirements, tools, capabilities, routes, Cedar
    policies) is recorded in the snapshot graph, not printed.
    """
    print_session(snap)
    print_modifications(snap, inside, outside, remote)
    print_downstream(list(downstream))
    print_findings(snap)
