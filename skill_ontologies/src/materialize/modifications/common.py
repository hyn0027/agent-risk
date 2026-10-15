"""Helpers shared by the inside / host / remote modification tables."""

import re
from collections.abc import Callable

from rdflib import URIRef

from ...common.namespaces import AR
from ...common.rdf import short
from ..constants import CONTAINER_ONLY, REPORTED_EFFECTS, STATUS_RANK, UNAVAILABLE
from ..provider_tools import tool_status, tools_implementing
from ..snapshot import Snapshot

# (capability, status, reported effect types)
CapabilityHit = tuple[URIRef, URIRef, set[URIRef]]

ENDPOINT_NAMES = {
    AR.NanoClawContainerShellExecution: "shell",
    AR.NanoClawProviderFileTool: "file tools",
    AR.NanoClawSendMessageTool: "send_message",
    AR.NanoClawSendFileTool: "send_file",
    AR.NanoClawProviderSubagentTool: "subagent tool",
    AR.NanoClawProviderWebFetchTool: "web fetch",
    AR.NanoClawProviderWebSearchTool: "web search",
    AR.NanoClawContainerTasksCLI: "ncl tasks",
    AR.NanoClawContainerGroupAdminCLI: "ncl (own group)",
    AR.NanoClawContainerGlobalAdminCLI: "ncl (global scope)",
}


def reported_capabilities(snap: Snapshot, pred: Callable[[URIRef], bool]) -> list[CapabilityHit]:
    """Capabilities that are not unavailable, read or change something, and match ``pred``.

    Requires ``assess_capabilities`` to have filled ``snap.cap_status``.
    """
    out = []
    for cap, status in snap.cap_status.items():
        if cap in snap.refined_by:
            continue  # reported through its provider-specific refinements
        effects = set(snap.model.objects(cap, AR.nativeEffectType)) & REPORTED_EFFECTS
        if effects and status != UNAVAILABLE and pred(cap):
            out.append((cap, status, effects))
    return out


def merge(snap: Snapshot, items: list[CapabilityHit]) -> tuple[str, str, str]:
    """(effects, via, best status) for a group of capabilities, as display strings."""
    m = snap.model
    effects = sorted({short(e) for _, _, es in items for e in es})
    via = sorted({endpoint_name(snap, m.value(c, AR.nativeEndpointKind)) for c, _, _ in items})
    status = min((st for _, st, _ in items), key=lambda st: STATUS_RANK[st])
    return ", ".join(effects), ", ".join(via), short(status)


def endpoint_name(snap: Snapshot, endpoint: URIRef) -> str:
    """Provider tool name (e.g. "Write"); for a generic endpoint, the enabled
    provider tools implementing it (e.g. "Bash"); else a friendly or local name."""
    name = snap.model.value(endpoint, AR.providerToolName)
    if name is not None:
        return str(name)
    enabled = [n for _, n in tools_implementing(snap.model, endpoint) if tool_status(snap.facts["claude_tools"], n)[0]]
    if enabled:
        return ", ".join(enabled)
    return ENDPOINT_NAMES.get(endpoint, short(endpoint))


def host_backing(snap: Snapshot, dest: str | None) -> str:
    """Host path behind a container mount path, or 'container only'."""
    mnt = next((x for x in snap.mounts if x["Destination"] == dest), None)
    return snap.host_path(mnt.get("Source")) if mnt else CONTAINER_ONLY


def tool_label(kind: URIRef) -> str:
    """NanoClaw MCP tools by their real names (NanoClawSendMessageTool -> send_message);
    other kinds by their local name without the NanoClaw prefix."""
    local = short(kind)
    if local.startswith("NanoClaw") and local.endswith("Tool"):
        return re.sub(r"(?<!^)(?=[A-Z])", "_", local[len("NanoClaw"):-len("Tool")]).lower().replace("m_c_p", "mcp")
    return local.replace("NanoClaw", "")


def dedupe(rows: list[tuple], width: int) -> list[tuple]:
    """Drop rows repeating (resource, ...first ``width`` columns)."""
    seen, out = set(), []
    for row in rows:
        key = (row[0].strip(" └"),) + tuple(row[1:width])
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out
