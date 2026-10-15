"""Helpers shared by the inside / host / remote modification tables."""

from collections.abc import Callable

from rdflib import URIRef

from ...common.namespaces import AR
from ...common.rdf import short
from ..constants import CONTAINER_ONLY, MUTATING_EFFECTS, STATUS_RANK, UNAVAILABLE
from ..snapshot import Snapshot

# (capability, status, mutating effect types)
CapabilityHit = tuple[URIRef, URIRef, set[URIRef]]

ENDPOINT_NAMES = {
    AR.NanoClawContainerShellExecution: "shell",
    AR.NanoClawProviderFileTool: "file tools",
    AR.NanoClawSendMessageTool: "send_message",
    AR.NanoClawSendFileTool: "send_file",
    AR.NanoClawProviderSubagentTool: "subagent tool",
    AR.NanoClawProviderWebFetchTool: "web fetch",
    AR.NanoClawProviderWebSearchTool: "web search",
}


def mutating_capabilities(snap: Snapshot, pred: Callable[[URIRef], bool]) -> list[CapabilityHit]:
    """Capabilities that are not unavailable, have a mutating effect, and match ``pred``.

    Requires ``assess_capabilities`` to have filled ``snap.cap_status``.
    """
    out = []
    for cap, status in snap.cap_status.items():
        effects = set(snap.model.objects(cap, AR.nativeEffectType)) & MUTATING_EFFECTS
        if effects and status != UNAVAILABLE and pred(cap):
            out.append((cap, status, effects))
    return out


def merge(snap: Snapshot, items: list[CapabilityHit]) -> tuple[str, str, str]:
    """(effects, via, best status) for a group of capabilities, as display strings."""
    m = snap.model
    effects = sorted({short(e) for _, _, es in items for e in es})
    via = sorted({ENDPOINT_NAMES.get(m.value(c, AR.nativeEndpointKind), short(m.value(c, AR.nativeEndpointKind))) for c, _, _ in items})
    status = min((st for _, st, _ in items), key=lambda st: STATUS_RANK[st])
    return ", ".join(effects), ", ".join(via), short(status)


def host_backing(snap: Snapshot, dest: str | None) -> str:
    """Host path behind a container mount path, or 'container only'."""
    mnt = next((x for x in snap.mounts if x["Destination"] == dest), None)
    return snap.host_path(mnt.get("Source")) if mnt else CONTAINER_ONLY


def tool_label(kind: URIRef) -> str:
    return short(kind).replace("NanoClaw", "").replace("Tool", "")


def dedupe(rows: list[tuple], width: int) -> list[tuple]:
    """Drop rows repeating (resource, ...first ``width`` columns)."""
    seen, out = set(), []
    for row in rows:
        key = (row[0].strip(" └"),) + tuple(row[1:width])
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out
