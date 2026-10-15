"""What this session can cause the host to read or change, outside its container.

Rows: (resource, host location, effects, triggered by, status, gate). Host-side
steps are found by walking routesToKind from container-side tool endpoints;
host-side reads come from capabilities whose resource is located on the host
(their results return into the container); host-mediated management actions are
listed from NanoClaw's guard rules.
"""

from rdflib import URIRef
from rdflib.namespace import RDF

from ...common.namespaces import AR
from ...common.rdf import short
from ..constants import LOCAL_CHANNELS
from ..provider_tools import tool_status
from ..snapshot import Snapshot
from .common import merge, reported_capabilities, tool_label


def container_entry_points(snap: Snapshot) -> list[URIRef]:
    """Agent-callable endpoints running in the container, filtered by cli_scope."""
    m, scope = snap.model, snap.cli_scope
    lists = snap.facts["claude_tools"]
    entries = [
        k for k in m.subjects(RDF.type, AR.ToolEndpointKind)
        if snap.side_of(k) == AR.NanoClawAgentContainer
        and (m.value(k, AR.providerToolName) is None or tool_status(lists, str(m.value(k, AR.providerToolName)))[0])
    ]
    ncl_kinds = {
        k for k in entries
        if k == AR.NanoClawContainerNclCLI or AR.NanoClawContainerNclCLI in m.transitive_objects(k, AR.specializesInvocationKind)
    }
    if scope == "disabled":
        return [k for k in entries if k not in ncl_kinds]
    if scope != "global":
        return [k for k in entries if k != AR.NanoClawContainerGlobalAdminCLI]
    return entries


def reachable_host_steps(snap: Snapshot) -> dict[URIRef, set[URIRef]]:
    """Host-side invocation kind -> container entry points that reach it.

    Host delivery is a hub every outbound row passes through, so the walk does
    not continue past it; specific host steps have direct routes in the model.
    """
    m = snap.model
    reached: dict[URIRef, set[URIRef]] = {}
    for entry in container_entry_points(snap):
        todo, seen = [entry], set()
        while todo:
            k = todo.pop()
            if k in seen:
                continue
            seen.add(k)
            if k != entry and snap.side_of(k) == AR.NanoClawHostProcess and (k, RDF.type, AR.InvocationSurfaceKind) in m:
                reached.setdefault(k, set()).add(entry)
            if k == AR.NanoClawHostDeliveryInvocation:
                continue
            todo.extend(t for t in m.objects(k, AR.routesToKind) if (t, RDF.type, AR.InvocationSurfaceKind) in m)
            todo.extend(m.objects(k, AR.specializesInvocationKind))  # inherit routes of broader kinds
    return reached


def step_effects(snap: Snapshot) -> dict[URIRef, tuple[str, str, str, str]]:
    """Host step -> (resource, effects, concrete host location, status) in this session."""
    f, scope = snap.facts, snap.cli_scope
    folder = f["group"].get("folder") or "{folder}"
    agent_grants = [d["local_name"] for d in f["grants"] if d["target_type"] == "agent"]
    ws = next((x for x in f["inspect"]["Mounts"] if x["Destination"] == "/workspace"), {})
    session_dir = snap.host_path(ws.get("Source")) or "data/v2-sessions/<group>/<session>"
    ncl_status = "Available" if scope != "disabled" else "Unavailable"
    a2a_status = "Available" if agent_grants else "Unavailable"
    return {
        AR.NanoClawHostDeliveryInvocation: ("NanoClawDeliveryRecord", "Create", f"{session_dir}/inbound.db (delivered)", "Available"),
        AR.NanoClawAgentRouteInvocation: ("NanoClawInboundMessage (another agent's session)", "Create", ", ".join(agent_grants) or "no agent destination grants", a2a_status),
        AR.NanoClawHostAttachmentStaging: ("NanoClawInboxArtifact (another agent's session)", "Create", "data/v2-sessions/<target group>/<session>/inbox/", a2a_status),
        AR.NanoClawHostTaskLogAppend: ("NanoClawTaskRunLog", "Update", f"groups/{folder}/tasks/<series>.md", ncl_status),
        AR.NanoClawHostImageBuild: ("NanoClawAgentImage", "Install, Update", "per-group image (Docker image store)", "Available"),
        AR.NanoClawHostConfigMaterialization: ("NanoClawHostContainerConfigFile, NanoClawHostComposedInstructionsFile", "Update", f"groups/{folder}/container.json, groups/{folder}/CLAUDE.md", ncl_status),
        AR.NanoClawHostCommandDispatch: ("NanoClawCentralDatabase", "Create, Read, Update, Delete", "data/v2.db", ncl_status),
        AR.NanoClawHostGuardInvocation: ("NanoClawCentralDatabase", "Create, Update, Delete", "data/v2.db", ncl_status),
    }


def route_rows(snap: Snapshot, reached: dict[URIRef, set[URIRef]]) -> list[tuple]:
    m = snap.model
    effects = step_effects(snap)
    names = {AR.NanoClawContainerShellExecution: "shell"}
    rows = []
    for step, sources in sorted(reached.items(), key=lambda kv: short(kv[0])):
        if step not in effects:
            continue
        resource, eff, where, status = effects[step]
        leaves = {e for e in sources if not any(e in m.objects(o, AR.specializesInvocationKind) for o in sources)}
        via = ", ".join(sorted(names.get(e, tool_label(e)) for e in leaves))
        if step == AR.NanoClawHostDeliveryInvocation:
            via = "every outbound row (all built-in tools, ncl, direct writes)"
        controls = sorted(short(c) for c in m.objects(step, AR.protectedByKind))
        rows.append((resource, where, eff, f"{short(step).replace('NanoClaw', '')} ← {via}", status, ", ".join(controls) or "-"))
    return rows


def host_read_rows(snap: Snapshot) -> list[tuple]:
    """Capabilities on host-located resources (e.g. ncl reads), whose results return to the agent."""
    m = snap.model
    gid = snap.facts["group"]["id"]
    locations = {
        AR.NanoClawCentralDatabase: "data/v2.db (own group: config, sessions, destinations, members)",
        AR.NanoClawSessionTranscript: f"data/v2-sessions/{gid}/<any session>/inbound.db + outbound.db",
        AR.NanoClawScheduledTask: "data/v2.db + task session inbound.db",
        AR.NanoClawMessagingRouteConfiguration: "data/v2.db (messaging groups, wirings, policies, user DMs)",
        AR.NanoClawRoleMembershipState: "data/v2.db (users, roles)",
        AR.NanoClawDroppedMessage: "data/v2.db (dropped_messages)",
        AR.NanoClawApprovalRequest: "data/v2.db (pending_approvals)",
    }
    hits = reported_capabilities(snap, lambda c: snap.side_of(m.value(c, AR.nativeResourceKind)) == AR.NanoClawHostProcess)
    rows = []
    for cap, status, effects in sorted(hits, key=lambda h: short(h[0])):
        resource = m.value(cap, AR.nativeResourceKind)
        eff, via, st = merge(snap, [(cap, status, effects)])
        rows.append((short(resource), locations.get(resource, "host"), eff, via, st, "no approval; result returned into the container"))
    return rows


def local_delivery_rows(snap: Snapshot, reached: dict[URIRef, set[URIRef]]) -> list[tuple]:
    """Deliveries to local channels (CLI, Emacs) stay on this machine."""
    if AR.NanoClawChannelAdapterDelivery not in reached:
        return []
    return [
        ("MessagingMessage (local channel)", f"{d.get('channel_type')}: {d.get('display_name') or d['local_name']} (local client)", "Create, Transmit", "ChannelAdapterDelivery ← built-in messaging tools", "Available", "destination grant; origin chat always allowed")
        for d in snap.facts["grants"]
        if d["target_type"] == "channel" and d.get("channel_type") in LOCAL_CHANNELS
    ]


def management_rows(snap: Snapshot) -> list[tuple]:
    """Host-mediated management actions (guard rules encoded here; see README)."""
    scope = snap.cli_scope
    folder = snap.facts["group"].get("folder") or "{folder}"
    rows = []
    if scope != "disabled":
        rows.append(("NanoClawScheduledTask", "data/v2.db + task session inbound.db", "Create, Update, Delete", "ncl tasks", "Available", "no approval"))
        rows.append(("NanoClawContainerConfiguration", "data/v2.db (container_configs)", "Update", "ncl groups config", "Available", "held for approval"))
        rows.append(("NanoClawDestinationGrant", "data/v2.db (agent_destinations)", "Create, Delete", "ncl destinations", "Available", "held for approval"))
        rows.append(("NanoClawRoleMembershipState", "data/v2.db (members)", "Create, Delete", "ncl members", "Available", "held for approval"))
    if scope == "global":
        rows.append(("NanoClawMessagingRouteConfiguration", "data/v2.db (wirings, messaging groups, policies)", "Create, Update, Delete", "ncl (global scope)", "Available", "held for approval"))
        rows.append(("NanoClawRoleMembershipState", "data/v2.db (users, roles)", "Create, Update, Delete", "ncl (global scope)", "Available", "held for approval"))
    rows.append(("NanoClawAgentGroup", "data/v2.db + groups/<new folder>", "Create", "create_agent", "Available", "no approval (cli_scope=global)" if scope == "global" else "held for approval"))
    rows.append(("NanoClawAgentImage", "per-group image (Docker image store)", "Install, Update", "install_packages", "Available", "held for approval; rebuild + restart"))
    rows.append(("NanoClawContainerConfiguration", f"data/v2.db → groups/{folder}/container.json", "Configure", "add_mcp_server", "Available", "held for approval; restart"))
    return rows


def host_rows(snap: Snapshot) -> tuple[list[tuple], dict[URIRef, set[URIRef]]]:
    """Host table rows, plus the reached host steps whose effect is remote (adapter delivery)."""
    reached = reachable_host_steps(snap)
    remote_via_host = {step: srcs for step, srcs in reached.items() if step == AR.NanoClawChannelAdapterDelivery}
    rows = route_rows(snap, reached) + host_read_rows(snap) + local_delivery_rows(snap, reached) + management_rows(snap)
    return rows, remote_via_host
