"""Load the universal model and answer the questions the materializer asks of it."""

import re
from pathlib import Path

from rdflib import Dataset, Graph, URIRef

from ..common.namespaces import AR
from ..common.paths import MODEL_DIRS, SKILLS_DIR, VOCABULARY


def load_model() -> Graph:
    """The vocabulary plus every universal, NanoClaw, and Claude graph, merged."""
    model = Graph()
    model.parse(VOCABULARY, format="turtle")
    for path in [p for d in MODEL_DIRS for p in sorted(d.glob("*.trig"))]:
        for graph in Dataset().parse(path, format="trig").graphs():
            for triple in graph:
                model.add(triple)
    return model


def pinned_source(model: Graph) -> tuple[Path | None, str]:
    """NanoClaw checkout and revision the model is pinned to (nanoclaw-core)."""
    repo = next(model.objects(AR.NanoClawCoreModule, AR.sourceRepositoryPath), None)
    revision = str(next(model.objects(AR.NanoClawCoreModule, AR.sourceRevision), ""))
    return (Path(str(repo)) if repo is not None else None), revision


def skill_directories() -> dict[str, Path]:
    """Skill directory name -> skill graph file."""
    found = {}
    for path in sorted(SKILLS_DIR.glob("*.trig")):
        match = re.search(r'ar:skillDirectory "([^"]+)"', path.read_text())
        if match:
            found[match.group(1)] = path
    return found


def side_of(model: Graph, kind: URIRef) -> URIRef | None:
    """executesOn / locatedOn, inherited along the specialization hierarchy."""
    seen, todo = set(), [kind]
    while todo:
        k = todo.pop()
        if k in seen:
            continue
        seen.add(k)
        side = model.value(k, AR.executesOn) or model.value(k, AR.locatedOn)
        if side is not None:
            return side
        todo.extend(model.objects(k, AR.specializesInvocationKind))
        todo.extend(model.objects(k, AR.specializesKind))
    return None


def mount_kind(model: Graph, dest: str, rw: bool) -> URIRef | None:
    """Most specific mount kind whose modeled containerPath matches (trailing * = prefix)."""
    best: tuple[int, URIRef] | None = None
    for kind, path in model.subject_objects(AR.containerPath):
        path = str(path)
        hit = dest.startswith(path[:-1]) if path.endswith("*") else dest == path
        modes = set(model.objects(kind, AR.mountAccessMode))
        if hit and (not modes or (AR.ReadWriteMountMode if rw else AR.ReadOnlyMountMode) in modes):
            if best is None or len(path) > best[0]:
                best = (len(path), kind)
    return best[1] if best else None
