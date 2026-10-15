"""Printed report: one function per table."""

from rdflib.namespace import RDF

from table_output import print_table

from ..common.namespaces import OBS
from ..common.rdf import short
from .model import skill_directories
from .snapshot import Snapshot


def print_session(snap: Snapshot) -> None:
    f = snap.facts
    sess, group, config, agent = f["session"], f["group"], f["config"], f["onecli_agent"]
    rules_in_scope = len([r for r in f["rules"] if not r.get("agentId") or (agent and r.get("agentId") == agent["id"])])
    print_table("Session snapshot", ("Field", "Value"), [
        ("Session", sess["id"]),
        ("Agent group", f"{group['name']} ({group['id']})"),
        ("Other sessions in group", str(len(f["group_sessions"]) - 1)),
        ("Container", f["container_name"]),
        ("Provider", config.get("provider") or "claude (default)"),
        ("cli_scope", snap.cli_scope),
        ("Egress lockdown", "on" if snap.lockdown_on else "off"),
        ("Destination grants", ", ".join(d["local_name"] for d in f["grants"]) or "none"),
        ("MCP servers (third-party)", ", ".join(config.get("mcp_servers") or {}) or "none"),
        ("Gateway identity", f"{agent['identifier']} secretMode={agent.get('secretMode')}" if agent else "none"),
        ("Gateway rules in scope", str(rules_in_scope)),
        ("Instances / triples", f"{len(set(snap.graph.subjects(RDF.type, None)))} / {len(snap.graph)}"),
    ], (26, 90))


def print_mounts(snap: Snapshot) -> None:
    def kind_of(dest: str) -> str:
        return short(snap.graph.value(snap.node(f"mount{dest}"), RDF.type))

    def host_kind(dest: str) -> str:
        backing = snap.graph.value(snap.node(f"mount{dest}"), OBS.bindsFrom)
        return short(snap.graph.value(backing, RDF.type)) if backing is not None else "-"

    print_table("Observed mounts (container view ← host source)", ("Container path", "Mode", "Container-side kind", "Host path", "Host-side kind"), [
        (m["Destination"], "rw" if m["RW"] else "ro", kind_of(m["Destination"]), snap.host_path(m.get("Source")) or "-", host_kind(m["Destination"]))
        for m in snap.mounts
    ], (32, 4, 34, 46, 36))


def print_requirements(snap: Snapshot) -> None:
    print_table("Requirements for this session", ("Requirement", "Status", "Reason"), [
        (short(c), short(s), r) for c, (s, r) in sorted(snap.conditions.items(), key=lambda kv: (short(kv[1][0]), short(kv[0])))
    ], (44, 11, 70))


def print_capabilities(caps: list[dict]) -> None:
    print_table("Native capabilities in this session (may-effects)", ("Capability", "Status", "Effect", "Resource", "Reaches", "Why"), [
        (r["capability"], r["status"], r["effect"], r["resource"], r["scope"], r["why"]) for r in sorted(caps, key=lambda r: (r["status"], r["capability"]))
    ], (34, 11, 18, 26, 34, 40))


def print_routes(routes: list[tuple]) -> None:
    print_table("Routes and management paths", ("Kind", "Status", "Why"), routes, (34, 24, 50))


def print_modifications(inside: list[tuple], outside: list[tuple], remote: list[tuple]) -> None:
    print_table("Modifiable inside the container (may-effects; reads excluded)", ("Resource", "Container path", "Host backing", "Effects", "Via", "Status", "Scope / gate"), inside, (36, 30, 40, 22, 18, 11, 28))
    print_table("Changed outside the container, on the host (triggered by the agent)", ("Resource", "Host location", "Effects", "Triggered by", "Status", "Gate"), outside, (36, 38, 20, 40, 11, 30))
    print_table("Outside this machine (remote): reached or changed", ("Resource", "Remote location", "Effects", "Path off the machine", "Status", "Gate"), remote, (22, 30, 16, 52, 11, 40))


def print_skills(snap: Snapshot) -> None:
    installed = snap.facts["container_skills"]
    modeled = skill_directories()
    print_table("Skills", ("Installed container skill", "Modeled skill graph"), [
        (name, modeled[name].name if name in modeled else "none") for name in installed
    ], (30, 40))
    if not any(name in modeled for name in installed):
        print("No installed skill has a skill graph, so no skill operations apply to this session; only native capabilities do.")


def print_findings(snap: Snapshot) -> None:
    if snap.findings:
        print("\nModel/runtime differences:")
        for item in snap.findings:
            print(f"  - {item}")


def print_report(snap: Snapshot, caps: list[dict], routes: list[tuple], inside: list[tuple], outside: list[tuple], remote: list[tuple]) -> None:
    print_session(snap)
    print_mounts(snap)
    print_requirements(snap)
    print_capabilities(caps)
    print_routes(routes)
    print_modifications(inside, outside, remote)
    print_skills(snap)
    print_findings(snap)
