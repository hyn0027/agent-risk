"""What this session can reach or change beyond the local machine.

Rows: (resource, remote location, effects, path off the machine, status, gate).
Container-originated requests leave through the OneCLI gateway (and directly
when lockdown is off); messages leave through the host's channel adapter;
provider web search runs at the model provider. Reads are included because the
remote party sees the request. Model-provider traffic is out of scope.
"""

from rdflib import URIRef

from ...common.namespaces import AR
from ...common.rdf import short
from ..constants import LOCAL_CHANNELS, UNAVAILABLE
from ..snapshot import Snapshot
from .common import endpoint_name, tool_label

ENDPOINT_NAMES = {
    AR.NanoClawContainerShellExecution: "shell (curl, scripts, ...)",
    AR.NanoClawProviderWebFetchTool: "web fetch",
    AR.NanoClawProviderWebSearchTool: "web search",
}


def network_route(snap: Snapshot) -> tuple[str, str]:
    """(path off the machine, gate) for container-originated requests."""
    f = snap.facts
    agent = f["onecli_agent"]
    rule_count = len([r for r in f["rules"] if not r.get("agentId") or (agent and r.get("agentId") == agent["id"])])
    lockdown = snap.lockdown_on
    leave = "container ▸ OneCLI gateway ▸ Internet" if lockdown else "container ▸ OneCLI gateway or direct ▸ Internet"
    gate = f"gateway policy ({rule_count} rule(s) in scope); credentials injected per host" + ("; direct route blocked" if lockdown else "; direct route open")
    return leave, gate


def capability_rows(snap: Snapshot) -> list[tuple]:
    m = snap.model
    leave, gate = network_route(snap)
    rows = []
    for cap, status in sorted(snap.cap_status.items(), key=lambda kv: short(kv[0])):
        resource = m.value(cap, AR.nativeResourceKind)
        if cap in snap.refined_by or status == UNAVAILABLE or snap.side_of(resource) != AR.ExternalNetwork:
            continue
        endpoint = m.value(cap, AR.nativeEndpointKind)
        effects = ", ".join(sorted(short(e) for e in m.objects(cap, AR.nativeEffectType)))
        name = ENDPOINT_NAMES.get(endpoint) or endpoint_name(snap, endpoint)
        if snap.side_of(endpoint) == AR.ExternalNetwork:
            rows.append((short(resource), "search results (any site)", effects, f"{name}: query sent inside the model request ▸ OneCLI gateway ▸ model provider, which runs the search", short(status), "local controls see only the model request, not the searches or sites; disable via the tool allowlist"))
        else:
            rows.append((short(resource), "any public host", effects, f"{name}: {leave}", short(status), gate))
    return rows


def mcp_rows(snap: Snapshot) -> list[tuple]:
    leave, gate = network_route(snap)
    rows = []
    for name, spec in (snap.facts["config"].get("mcp_servers") or {}).items():
        if isinstance(spec, dict) and spec.get("url"):
            host = spec["url"].split("/")[2] if "//" in spec["url"] else spec["url"]
            rows.append(("RemoteMCPService", host, "Transmit", f"MCP server '{name}': {leave}", "Available", gate + "; the service's own calls happen remotely"))
    return rows


def message_rows(snap: Snapshot, via_host: dict[URIRef, set[URIRef]]) -> list[tuple]:
    if AR.NanoClawChannelAdapterDelivery not in via_host:
        return []
    tools = ", ".join(sorted(tool_label(e) for e in via_host[AR.NanoClawChannelAdapterDelivery]))
    return [
        ("MessagingMessage", f"{d.get('channel_type')}: {d.get('display_name') or d['local_name']}", "Create, Transmit", f"{tools} ▸ outbound mailbox ▸ host delivery ▸ {d.get('channel_type')} adapter", "Available", "destination grant; origin chat always allowed; the host holds the channel credentials")
        for d in snap.facts["grants"]
        if d["target_type"] == "channel" and d.get("channel_type") not in LOCAL_CHANNELS
    ]


def remote_rows(snap: Snapshot, via_host: dict[URIRef, set[URIRef]]) -> list[tuple]:
    return capability_rows(snap) + mcp_rows(snap) + message_rows(snap, via_host)
