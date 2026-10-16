"""What this session can reach or change beyond the local machine.

Rows: (resource, remote location, effects, path off the machine, status, gate).
Container-originated web requests leave only through the OneCLI gateway (the
CLI refuses to run unless the gateway is the Cedar deny-by-default build and
lockdown holds), so they are listed once per Cedar permit policy that lets them through; messages leave through the host's channel adapter;
provider web search runs at the model provider. Reads are included because the
remote party sees the request. Model-provider traffic is out of scope.
"""

from rdflib import URIRef

from ...common.namespaces import AR
from ...common.rdf import short
from ..constants import LOCAL_CHANNELS, UNAVAILABLE
from ..snapshot import Snapshot
from ..gateway_policy import host_allowed, patterns_overlap, policy_entries
from .common import endpoint_name, tool_label

ENDPOINT_NAMES = {
    AR.NanoClawContainerShellExecution: "shell (curl, scripts, ...)",
    AR.NanoClawProviderWebFetchTool: "web fetch",
    AR.NanoClawProviderWebSearchTool: "web search",
}


# Endpoints that can only send GET requests: they cannot use a policy that permits only other methods.
GET_ONLY = {"WebFetch", "web fetch"}

LEAVE = "container ▸ OneCLI gateway ▸ Internet"


def capability_rows(snap: Snapshot) -> list[tuple]:
    """Provider-side search as is; gateway-routed web capabilities once per policy entry that lets them through."""
    m = snap.model
    agent = snap.facts["onecli_agent"]
    entries = policy_entries(snap.facts["gateway_policy"], agent["id"] if agent else None)
    provider_rows = []
    by_entry: dict[tuple, set[str]] = {}  # (entry index, resource, effects, status) → endpoint names
    for cap, status in sorted(snap.cap_status.items(), key=lambda kv: short(kv[0])):
        resource = m.value(cap, AR.nativeResourceKind)
        if cap in snap.refined_by or status == UNAVAILABLE or snap.side_of(resource) != AR.ExternalNetwork:
            continue
        endpoint = m.value(cap, AR.nativeEndpointKind)
        effects = ", ".join(sorted(short(e) for e in m.objects(cap, AR.nativeEffectType)))
        name = ENDPOINT_NAMES.get(endpoint) or endpoint_name(snap, endpoint)
        if snap.side_of(endpoint) == AR.ExternalNetwork:
            provider_rows.append((short(resource), "search results (any site)", effects, f"{name}: query sent inside the model request ▸ OneCLI gateway ▸ model provider, which runs the search", short(status), "not gated by OneCLI policy: the provider runs the searches; disable via the tool allowlist"))
            continue
        for i, entry in enumerate(entries):
            if name in GET_ONLY and entry["methods"] is not None and "GET" not in entry["methods"]:
                continue
            by_entry.setdefault((i, short(resource), effects, short(status)), set()).add(name)
    secrets = snap.facts["secrets"]

    def credential_note(entry: dict) -> str:
        hit = [f"{s['name']} on {s['hostPattern']}" for s in secrets if s.get("hostPattern") and patterns_overlap(s["hostPattern"], entry["host"])]
        return f"; granted credential injected ({', '.join(hit)})" if hit else "; no granted credential"

    rows = [
        (resource, entries[i]["label"], effects, f"{', '.join(sorted(names))}: {LEAVE}", status, entries[i]["gate"] + credential_note(entries[i]))
        for (i, resource, effects, status), names in sorted(by_entry.items())
    ]
    return rows + provider_rows


def mcp_rows(snap: Snapshot) -> list[tuple]:
    """Remote MCP servers; each needs a Cedar permit policy for its host."""
    agent = snap.facts["onecli_agent"]
    agent_id = agent["id"] if agent else None
    rows = []
    for name, spec in (snap.facts["config"].get("mcp_servers") or {}).items():
        if isinstance(spec, dict) and spec.get("url"):
            host = spec["url"].split("/")[2].split(":")[0] if "//" in spec["url"] else spec["url"]
            allowed = host_allowed(snap.facts["gateway_policy"], agent_id, host)
            gate = "permitted by a Cedar policy" if allowed else "no Cedar policy permits this host"
            rows.append(("RemoteMCPService", host, "Transmit", f"MCP server '{name}': {LEAVE}", "Available" if allowed else "Unavailable", gate + "; the service's own calls happen remotely"))
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
