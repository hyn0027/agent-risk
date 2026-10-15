"""What this session can change inside its container.

Rows: (resource, container path, host backing, effects, via, status, scope). A
write through a bind mount also changes the listed host backing.
"""

from rdflib import URIRef
from rdflib.namespace import RDF

from ...common.namespaces import AR, OBS
from ...common.rdf import short
from ..constants import CONTAINER_ONLY, SUBPATHS
from ..snapshot import Snapshot
from .common import CapabilityHit, host_backing, merge, mutating_capabilities

PERSISTENCE = {
    AR.NanoClawSessionWorkspace: "this session",
    AR.NanoClawAgentGroupWorkspace: "agent group (all its sessions)",
    AR.NanoClawProviderStateDirectory: "agent group (all its sessions)",
    AR.NanoClawContainerLayer: "ephemeral (discarded with the container)",
}

# Container paths of resources targeted by a specific capability.
KNOWN_PATHS = {
    AR.NanoClawInboundMailbox: "/workspace/inbound.db",
    AR.NanoClawOutboundMessage: "/workspace/outbound.db",
    AR.NanoClawProviderStateDirectory: "/home/node/.claude",
    AR.NanoClawTaskRunLog: "/workspace/agent/tasks/",
}


def exposed_kinds(snap: Snapshot, dest: str) -> list[URIRef]:
    return [snap.graph.value(loc, RDF.type) for loc in snap.graph.objects(snap.node(f"mount{dest}"), OBS.exposes)]


def writable_locations(snap: Snapshot) -> tuple[list[tuple[URIRef, str | None]], set[URIRef]]:
    """(location kind, mount path or None for the container layer) and read-only-mounted kinds.

    A kind exposed by a mount is skipped as a location when it resides in
    another kind the same mount exposes (it becomes a sub-row instead).
    """
    m = snap.model
    ro_kinds, locations = set(), []
    for mnt in snap.mounts:
        exposed = exposed_kinds(snap, mnt["Destination"])
        for kind in exposed:
            nested = any(other in m.objects(kind, AR.mayResideInKind) for other in exposed if other != kind)
            if mnt["RW"] and not nested:
                locations.append((kind, mnt["Destination"]))
            elif not mnt["RW"]:
                ro_kinds.add(kind)
    if not snap.facts["inspect"]["HostConfig"].get("ReadonlyRootfs"):
        locations.append((AR.NanoClawContainerLayer, None))
    return locations, ro_kinds


def location_rows(snap: Snapshot) -> list[tuple]:
    """Each writable location and the modeled resources residing in it."""
    m = snap.model
    fs_caps = mutating_capabilities(snap, lambda c: m.value(c, AR.nativeScopeKind) == AR.NanoClawContainerFileSystem)
    if not fs_caps:
        return []
    effects, via, status = merge(snap, fs_caps)
    locations, ro_kinds = writable_locations(snap)
    rows = []
    for kind, dest in locations:
        cpath = dest or "/ (writable layer: /tmp, /home/node, ...)"
        hpath = host_backing(snap, dest) if dest else CONTAINER_ONLY
        rows.append((short(kind), cpath, hpath, effects, via, status, PERSISTENCE.get(kind, "-")))
        for sub in sorted(m.subjects(AR.mayResideInKind, kind)):
            if sub in ro_kinds or (sub, RDF.type, AR.WorldSurfaceKind) not in m:
                continue
            tail = SUBPATHS.get(sub, "")
            sub_c = f"{dest}/{tail}" if dest and tail else cpath
            sub_h = f"{hpath}/{tail}" if dest and tail else hpath
            rows.append((f"└ {short(sub)}", sub_c, sub_h, effects, via, status, PERSISTENCE.get(kind, "-")))
    return rows


def targeted_rows(snap: Snapshot) -> list[tuple]:
    """Capabilities aimed at a specific in-container resource.

    Delivery (a host-side step) and remote resources go to the other tables.
    """
    m = snap.model
    specific = mutating_capabilities(
        snap,
        lambda c: m.value(c, AR.nativeScopeKind) != AR.NanoClawContainerFileSystem
        and m.value(c, AR.nativeResourceKind) != AR.NanoClawDestinationGrant
        and snap.side_of(m.value(c, AR.nativeResourceKind)) != AR.ExternalNetwork,
    )
    grouped: dict[URIRef, list[CapabilityHit]] = {}
    for item in specific:
        grouped.setdefault(m.value(item[0], AR.nativeResourceKind), []).append(item)
    gates = {
        AR.NanoClawOutboundMessage: "host delivery and action guards decide",
        AR.NanoClawProviderStateDirectory: "affects later sessions of the group",
        AR.NanoClawInboundMailbox: "projected destinations grant nothing",
        AR.RemoteNetworkEndpoint: "leaves via the OneCLI gateway only (lockdown on)" if snap.lockdown_on else "gateway or direct (lockdown off)",
    }
    rows = []
    for kind, items in sorted(grouped.items(), key=lambda kv: short(kv[0])):
        effects, via, status = merge(snap, items)
        cpath = KNOWN_PATHS.get(kind)
        if cpath:
            parent = max((x["Destination"] for x in snap.mounts if cpath.startswith(x["Destination"])), key=len, default=None)
            hpath = f"{host_backing(snap, parent)}{cpath[len(parent):]}" if parent else CONTAINER_ONLY
        else:
            in_container = snap.side_of(kind) == AR.NanoClawAgentContainer
            cpath = "in container" if in_container else short(m.value(items[0][0], AR.nativeScopeKind))
            hpath = CONTAINER_ONLY if in_container else "— (remote)"
        rows.append((short(kind), cpath, hpath, effects, via, status, gates.get(kind, "-")))
    return rows


def read_only_rows(snap: Snapshot) -> list[tuple]:
    rows = []
    for mnt in snap.mounts:
        if not mnt["RW"]:
            kinds = exposed_kinds(snap, mnt["Destination"])
            rows.append((", ".join(short(k) for k in kinds) or "-", mnt["Destination"], host_backing(snap, mnt["Destination"]), "none", "-", "Unavailable", "read-only mount"))
    return rows


def inside_rows(snap: Snapshot) -> list[tuple]:
    return location_rows(snap) + targeted_rows(snap) + read_only_rows(snap)
