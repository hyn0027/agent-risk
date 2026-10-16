"""What the remote effects may set off further in the remote environment.

Starts from the direct effects of the remote table (rows the gateway lets through)
and follows the environment graph, up to MAX_STEPS steps:

- triggers: ar:mayTrigger on the kind (or a kind it specializes) whose
  ar:onEffectType is the effect: the environment itself causes ar:effectType on
  ar:affectsKind (e.g. a created commit starts a workflow run);
- containment down: Delete on a kind deletes the kinds it contains, and so on;
- containment up (one level, final): Create, Update, Delete, or Execute on a kind
  updates the contents of the kinds that directly contain it (ar:containsKind),
  e.g. a new issue updates its repository; this does not propagate further;
- references (on Delete, final): deleting a kind affects the kinds that refer to
  it (ar:referencesKind and its sub-properties), e.g. a deleted label or branch
  leaves dangling references in issues or pull requests.

Triggers and deletions chain; the other two end where they apply.

Reads and transmissions change nothing and do not propagate. For each influenced
resource, the shortest path per effect is kept, with the tools and Cedar entries
that start it. All of it is read from the model; nothing is inferred elsewhere.
"""

from rdflib import URIRef

from ..common.namespaces import AR
from ..common.rdf import short
from .modifications.common import ancestors
from .snapshot import Snapshot

MAX_STEPS = 4
CHANGES = {"Create", "Update", "Delete", "Execute", "Delegate", "Configure", "Install"}
REFERENCE_PROPS = (AR.referencesKind, AR.authoredByKind, AR.assignedToKind)


def starts(rows: list[tuple]) -> list[tuple[URIRef, str, str, str, str]]:
    """(kind, effect, starter label, Cedar entry, status) for each changing effect of the remote rows."""
    out = []
    for res, loc, effects, via, status, _gate in rows:
        kind = AR[res.strip(" └")]
        cedar = next((line[len("cedar: "):] for line in loc.splitlines() if line.startswith("cedar: ")), "-")
        labels = [line.rstrip(":") for line in via.splitlines() if line and not line.startswith(" ")]
        for effect in (e.strip() for e in effects.split(",")):
            if effect in CHANGES:
                for label in labels:
                    for st in status.splitlines():
                        out.append((kind, effect, label, cedar, st))
    return out


def steps(snap: Snapshot, kind: URIRef, effect: str) -> list[tuple[URIRef, str, str, bool]]:
    """(next kind, next effect, how, final) one step from (kind, effect); a final step
    does not propagate further."""
    m, out = snap.model, []
    for a in ancestors(snap, kind):
        for node in m.objects(a, AR.mayTrigger):
            on = m.value(node, AR.onEffectType)
            target, eff = m.value(node, AR.affectsKind), m.value(node, AR.effectType)
            if on is not None and short(on) == effect and target is not None and eff is not None:
                note = m.value(node, URIRef("http://www.w3.org/2000/01/rdf-schema#comment"))
                out.append((target, short(eff), f"triggers{f' ({note})' if note else ''}", False))
    if effect == "Delete":
        for child in sorted(set(m.objects(kind, AR.containsKind)), key=short):
            out.append((child, "Delete", "contains", False))
        for prop in REFERENCE_PROPS:
            for referrer in sorted(set(m.subjects(prop, kind)) - {kind}, key=short):
                out.append((referrer, "Update", f"referenced by ({short(prop)}): dangling reference", True))
    if effect in {"Create", "Update", "Delete", "Execute"}:
        for container in sorted(set(m.subjects(AR.containsKind, kind)), key=short):
            out.append((container, "Update", "contents of", True))
    return out


def assess_downstream(snap: Snapshot, rows: list[tuple]) -> list[tuple]:
    """Rows (resource, influence, paths, started by, status), most influenced first."""
    best: dict[tuple[URIRef, str], list[str]] = {}       # (kind, effect) -> shortest path (lines)
    starters: dict[URIRef, set[str]] = {}
    statuses: dict[URIRef, set[str]] = {}
    for kind, effect, label, cedar, status in starts(rows):
        first = f"{label} [cedar: {cedar}]: {effect} {short(kind)}"
        frontier = [(kind, effect, [first], False)]
        seen = {(kind, effect)}
        for depth in range(MAX_STEPS + 1):
            nxt = []
            for k, e, path, final in frontier:
                key = (k, e)
                if key not in best or len(path) < len(best[key]):
                    best[key] = path
                starters.setdefault(k, set()).add(f"{label} [cedar: {cedar}]")
                statuses.setdefault(k, set()).add(status)
                if final or depth == MAX_STEPS:
                    continue
                for k2, e2, how, fin in steps(snap, k, e):
                    if (k2, e2) not in seen:
                        seen.add((k2, e2))
                        nxt.append((k2, e2, path + [f"  → {how}: {e2} {short(k2)}"], fin))
            frontier = nxt
    out = []
    for kind in sorted({k for k, _ in best}, key=lambda k: (-len([1 for kk, _ in best if kk == k]), short(k))):
        effects = sorted(e for k, e in best if k == kind)
        paths = "\n".join("\n".join(best[(kind, e)]) for e in effects)
        who = sorted(starters[kind])
        started = "\n".join(who[:6] + ([f"+{len(who) - 6} more"] if len(who) > 6 else []))
        out.append((short(kind), ", ".join(effects), paths, started, "\n".join(sorted(statuses[kind]))))
    return out
