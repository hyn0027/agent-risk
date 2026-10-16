"""Where the installed skills' operations take effect in this session.

For each ``ar:Operation`` a loaded skill declares, each ``ar:hasPotentialEffect``
(effect type, affected kind) is placed by the affected kind's side in the model:

``container``  the observed mounts exposing the kind or a kind it may reside in
               (mutating effects only where the mount is read-write), with the
               host path the mount binds from
``host``       the kind's model location (``hostPathPattern``, else containing kind)
``remote``     the open ``routesToKind`` paths from the operation's endpoints; a
               path through the OneCLI gateway yields one row per Cedar permit
               applying to the agent

Status follows the operation's ``ar:requires`` exactly as for native
capabilities. Controls are ``ar:protectedByKind`` of the kinds involved and
nothing else (the skill-wide ``ar:subjectToControlKind`` is not attributed to
single effects).
"""

from rdflib import URIRef
from rdflib.namespace import RDF

from ..common.namespaces import AR, OBS
from ..common.rdf import short
from .constants import AVAILABLE, CONDITIONAL, MUTATING_EFFECTS, SUBPATHS, UNAVAILABLE, UNKNOWN, UNSATISFIED
from .gateway_policy import policy_entries
from .modifications.common import ancestors, endpoint_name, gate, host_backing, kind_location, location, render_paths, route_paths
from .modifications.remote import GET_ONLY, credential_tokens, via_gateway
from .snapshot import Snapshot


def residence(snap: Snapshot, kind: URIRef) -> set[URIRef]:
    """Kinds ``kind`` (or a kind it specializes) may reside in, transitively."""
    m, seen, todo = snap.model, set(), list(ancestors(snap, kind))
    while todo:
        k = todo.pop()
        for loc in m.objects(k, AR.mayResideInKind):
            if loc not in seen:
                seen.add(loc)
                todo.extend(ancestors(snap, loc))
    return seen


def containers(snap: Snapshot, kind: URIRef) -> list[URIRef]:
    """``kind`` followed by the kinds containing it (``containsKind``), nearest first."""
    m, order, todo = snap.model, [kind], [kind]
    while todo:
        k = todo.pop(0)
        for a in sorted(ancestors(snap, k), key=short):
            for parent in sorted(m.subjects(AR.containsKind, a), key=short):
                if parent not in order:
                    order.append(parent)
                    todo.append(parent)
    return order


def effective_side(snap: Snapshot, kind: URIRef) -> URIRef | None:
    """The kind's side, else the side of a kind it may reside in, else of a containing kind."""
    for k in containers(snap, kind):
        side = snap.side_of(k)
        if side is not None:
            return side
        for home in sorted(residence(snap, k), key=short):
            side = snap.side_of(home)
            if side is not None:
                return side
    return None


def container_locations(snap: Snapshot, kind: URIRef) -> list[tuple[str, str, bool]]:
    """(container path, host backing, writable) of the observed mounts exposing ``kind``,
    else exposing the nearest kind containing it."""
    for k in containers(snap, kind):
        locs = mount_locations(snap, k)
        if locs:
            return locs
    return []


def mount_locations(snap: Snapshot, kind: URIRef) -> list[tuple[str, str, bool]]:
    """Mounts exposing ``kind`` itself (or a specialization); only when there are
    none, mounts exposing a kind it may reside in. A mount exposing the kind
    itself shadows its parent mounts, as the nested mount does in the container."""
    homes = residence(snap, kind)
    exact = [mnt for mnt in snap.mounts if any(
        (t := snap.graph.value(loc, RDF.type)) is not None and kind in ancestors(snap, t)
        for loc in snap.graph.objects(snap.node(f"mount{mnt['Destination']}"), OBS.exposes))]
    out = []
    for mnt in exact or snap.mounts:
        dest = mnt["Destination"]
        for loc in snap.graph.objects(snap.node(f"mount{dest}"), OBS.exposes):
            exposed = snap.graph.value(loc, RDF.type)
            if exposed is None or not (kind in ancestors(snap, exposed) or ancestors(snap, exposed) & homes):
                continue
            tail = SUBPATHS.get(kind, "")
            if isinstance(tail, dict):
                tail = tail.get(exposed, "")
            hpath = host_backing(snap, dest)
            out.append((f"{dest}/{tail}" if tail else dest, f"{hpath}/{tail}" if tail else hpath, bool(mnt["RW"])))
            break
    return sorted(set(out))


def op_status(snap: Snapshot, op: URIRef) -> tuple[URIRef, str]:
    reqs = sorted(snap.model.objects(op, AR.requires))
    statuses = {r: snap.conditions.get(r, (UNKNOWN, ""))[0] for r in reqs}
    blocked = [r for r, s in statuses.items() if s == UNSATISFIED]
    pending = [r for r, s in statuses.items() if s == UNKNOWN]
    status = UNAVAILABLE if blocked else CONDITIONAL if pending else AVAILABLE
    why = "; ".join([f"blocked: {short(r)}" for r in blocked] + [f"pending: {short(r)}" for r in pending]) or "-"
    return status, why


def assess_operations(snap: Snapshot) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """(inside, host, remote) rows for the installed skills' operations, in the
    same column layout as the native rows of those tables. The via column names
    the operation: "<skill>/<operation> (<tools>)". Effects on a kind with no
    side in the model become findings."""
    m = snap.model
    agent = snap.facts["onecli_agent"]
    entries = policy_entries(snap.facts["gateway_policy"], agent["id"] if agent else None)
    inside, host, remote = [], [], []
    for skill in sorted(m.subjects(RDF.type, AR.Skill), key=short):
        name = str(m.value(skill, AR.skillDirectory) or short(skill))
        if name not in snap.facts.get("modeled_skills", []):
            continue
        for op in sorted(m.objects(skill, AR.declaresOperation), key=short):
            status, _ = op_status(snap, op)
            st = short(status)
            endpoints = sorted(m.objects(op, AR.invokedThroughKind), key=short)
            tools = ", ".join(sorted({endpoint_name(snap, e) for e in endpoints})) or "-"
            label = f"{name}/{short(op)}"
            via = f"{label} ({tools})"
            effects: dict[URIRef, set[URIRef]] = {}
            for eff in m.objects(op, AR.hasPotentialEffect):
                kind, etype = m.value(eff, AR.affectsKind), m.value(eff, AR.effectType)
                if kind is not None and etype is not None:
                    effects.setdefault(kind, set()).add(etype)

            def controls_of(*kinds: URIRef, extra: list[str] | None = None) -> str:
                return gate(snap, extra or [], *kinds)

            def eff_text(es: set[URIRef]) -> str:
                return ", ".join(sorted(short(e) for e in es))

            for kind, etypes in sorted(effects.items(), key=lambda kv: short(kv[0])):
                side = effective_side(snap, kind)
                res = short(kind)
                if side == AR.NanoClawAgentContainer:
                    locs = container_locations(snap, kind)
                    if not locs:
                        inside.append((res, "-", eff_text(etypes), via, st, controls_of(kind, *endpoints)))
                    for cpath, hpath, writable in locs:
                        where = location(cpath, "rw" if writable else "ro", hpath)
                        allowed = etypes if writable else etypes - MUTATING_EFFECTS
                        if allowed:
                            inside.append((res, where, eff_text(allowed), via, st, controls_of(kind, *endpoints)))
                        if etypes - allowed:
                            inside.append((res, where, eff_text(etypes - allowed), via, "Unavailable", controls_of(kind, *endpoints, extra=["mount: ro"])))
                elif side == AR.ExternalNetwork:
                    paths = [p for e in endpoints for p in route_paths(snap, e, kind)]
                    if not paths:
                        remote.append((res, "-", eff_text(etypes), f"{via}: -", "Unavailable", controls_of(kind, *endpoints, extra=["path: none"])))
                    for path in paths:
                        route = render_paths([path], via)
                        kinds = [*path, kind]
                        if not via_gateway(snap, path):
                            remote.append((res, "*", eff_text(etypes), route, st, controls_of(*kinds)))
                            continue
                        for entry in entries:
                            if tools in GET_ONLY and entry["methods"] is not None and "GET" not in entry["methods"]:
                                continue
                            remote.append((res, entry["label"], eff_text(etypes), route, st,
                                           controls_of(*kinds, extra=entry["tokens"] + credential_tokens(snap, entry["host"]))))
                elif side is not None:
                    host.append((res, kind_location(snap, kind), eff_text(etypes), via, st, controls_of(kind, *endpoints)))
                else:
                    snap.findings.append(f"{label}: {res}.side=none; effects={eff_text(etypes)}")
    return inside, host, remote
