"""Settle the model's requirements for this session.

Each ar:Requirement becomes satisfied, unsatisfied, or unknown with a reason.
Requirements that depend on a concrete path or a per-request decision stay
unknown and are never assumed satisfied; so does any requirement without an
evaluator here.
"""

from rdflib import URIRef
from rdflib.namespace import RDF

from ..common.namespaces import AR, OBS
from ..common.rdf import short
from .constants import OBSERVED, SATISFIED, UNKNOWN, UNSATISFIED
from .gateway_policy import reachability
from .provider_tools import tool_status, tools_implementing
from .snapshot import Snapshot


def evaluate(snap: Snapshot) -> dict[str, tuple[URIRef, str]]:
    """Requirement local name -> (status, reason)."""
    f, config = snap.facts, snap.facts["config"]
    mounts = {m["Destination"]: bool(m["RW"]) for m in f["inspect"]["Mounts"]}
    provider = (config.get("provider") or f["session"].get("agent_provider") or "claude").lower()
    claude = provider == "claude"
    extras = [d for d in mounts if d.startswith("/workspace/extra/")]
    origin = bool(f["session"].get("messaging_group_id"))

    def mounted(path: str, what: str) -> tuple[URIRef, str]:
        return (SATISFIED if path in mounts else UNSATISFIED), f"{what} mount " + ("present" if path in mounts else "absent")

    claude_state = claude and "/home/node/.claude" in mounts
    any_rw_extra = any(mounts[d] for d in extras)
    onecli_files = any("onecli" in d for d in mounts)
    return {
        "cond_default_claude_provider": (SATISFIED if claude_state else UNSATISFIED, f"provider={provider}; /home/node/.claude {'mounted' if '/home/node/.claude' in mounts else 'not mounted'}"),
        "cond_builtin_messaging_tool_available": (SATISFIED, "built-in nanoclaw MCP server is always registered"),
        "cond_shared_skills_exist": mounted("/app/skills", "/app/skills"),
        "cond_container_config_exists": mounted("/workspace/agent/container.json", "container.json"),
        "cond_standing_instructions_composed": mounted("/workspace/agent/CLAUDE.md", "CLAUDE.md"),
        "cond_additional_mount_admitted": (SATISFIED if extras else UNSATISFIED, f"{len(extras)} /workspace/extra mounts observed"),
        "cond_additional_mount_readwrite": (SATISFIED if any_rw_extra else UNSATISFIED, "a read-write extra mount is present" if any_rw_extra else "no read-write extra mount"),
        "cond_onecli_files_contributed": (SATISFIED if onecli_files else UNSATISFIED, "OneCLI CA mounts " + ("present" if onecli_files else "absent")),
        "cond_network_client_available": (SATISFIED, f"curl at {f['curl']}") if f["curl"] else (UNKNOWN, "no curl found; other clients may exist"),
        "cond_destination_projected_and_authorized": (SATISFIED if f["grants"] or origin else UNSATISFIED, f"{len(f['grants'])} destination grant(s); origin chat {'present' if origin else 'absent'}"),
        "cond_network_route_permitted": network_route_requirement(snap),
        "cond_container_file_readable": (UNKNOWN, "depends on the concrete path"),
        "cond_container_file_writable": (UNKNOWN, "depends on the concrete path; see mount modes"),
        "cond_ncl_available": (UNSATISFIED if snap.cli_scope == "disabled" else SATISFIED, f"cli_scope={snap.cli_scope}"),
        "cond_cli_scope_global": (SATISFIED if snap.cli_scope == "global" else UNSATISFIED, f"cli_scope={snap.cli_scope}"),
    }


def network_route_requirement(snap: Snapshot) -> tuple[URIRef, str]:
    """Unsatisfied only when lockdown forces the gateway and its effective policy allows nothing."""
    agent = snap.facts["onecli_agent"]
    where, why, reachable = reachability(snap.facts["gateway_policy"], agent["id"] if agent else None, snap.facts["secrets"])
    route = "lockdown on: only gateway-proxied requests can leave" if snap.lockdown_on else "lockdown off: direct and proxied routes exist"
    if snap.lockdown_on and not reachable:
        return UNSATISFIED, f"{route}; gateway reachable hosts: {where} ({why})"
    return UNKNOWN, f"{route}; gateway reachable hosts: {where}; per-request and remote decisions are not observable"


def provider(snap: Snapshot) -> str:
    return (snap.facts["config"].get("provider") or snap.facts["session"].get("agent_provider") or "claude").lower()


def evaluate_tool_requirements(snap: Snapshot) -> dict[URIRef, tuple[URIRef, str]]:
    """Requirements decided by which provider tools are enabled (from the model)."""
    lists, out = snap.facts["claude_tools"], {}
    if provider(snap) != "claude":
        for cond in set(snap.model.subjects(AR.requiresProviderTool, None)) | set(snap.model.subjects(AR.satisfiedByEndpointKind, None)):
            out[cond] = (UNKNOWN, f"provider {provider(snap)} not modeled")
        return out
    for cond, name in snap.model.subject_objects(AR.requiresProviderTool):
        enabled, reason = tool_status(lists, str(name))
        out[cond] = (SATISFIED if enabled else UNSATISFIED, f"{name}: {reason}")
    for cond, endpoint in snap.model.subject_objects(AR.satisfiedByEndpointKind):
        tools = tools_implementing(snap.model, endpoint)
        enabled = [name for _, name in tools if tool_status(lists, name)[0]]
        if enabled:
            out[cond] = (SATISFIED, "enabled: " + ", ".join(enabled))
        else:
            out[cond] = (UNSATISFIED, "no enabled tool implements it" + (f" ({', '.join(n for _, n in tools)} disabled)" if tools else ""))
    return out


def resolve_conditions(snap: Snapshot) -> None:
    for name, result in evaluate(snap).items():
        snap.conditions[AR[name]] = result
    snap.conditions.update(evaluate_tool_requirements(snap))
    for cond in sorted(set(snap.model.subjects(RDF.type, AR.Requirement))):
        if cond not in snap.conditions:
            snap.conditions[cond] = (UNKNOWN, "no evaluator for this requirement")
    for cond, (status, reason) in snap.conditions.items():
        snap.add(snap.node(f"eval_{short(cond)}"), OBS.ConditionEvaluation, OBSERVED, short(cond), evaluates=cond, status=status, reason=reason)
