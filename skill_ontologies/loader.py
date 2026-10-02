"""Validate selected skill ontologies and report their possible effects and calls."""

import argparse
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from pyshacl import validate
from rdflib import BNode, Dataset, Graph, Literal, Namespace, URIRef
from rdflib.compare import to_canonical_graph
from rdflib.namespace import OWL, RDF, RDFS, SKOS
from rdflib.term import Identifier

from llm_annotation import analyze_pairs

ROOT = Path(__file__).resolve().parent
AR = Namespace("urn:agent-risk:")
SH = Namespace("http://www.w3.org/ns/shacl#")


def parse_graph(path: Path) -> Graph:
    """Read the single populated named graph in a TriG file."""
    dataset = Dataset().parse(path, format="trig")
    graphs = [graph for graph in dataset.graphs() if len(graph)]
    if len(graphs) != 1 or not isinstance(graphs[0].identifier, URIRef):
        raise SystemExit(f"Expected one named graph in {path.relative_to(ROOT)}")
    return graphs[0]


def required_literal(graph: Graph, node: Identifier, predicate: URIRef) -> str:
    """Read one nonempty literal, used for required ontology metadata."""
    values = list(graph.objects(node, predicate))
    if len(values) != 1 or not isinstance(values[0], Literal) or not str(values[0]):
        raise SystemExit(f"Expected one literal {predicate} on {node}")
    return str(values[0])


def label(node: Identifier) -> str:
    """Shorten a local RDF identifier for the text report."""
    return str(node).rsplit(":", 1)[-1]


def print_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    """Print a small left-aligned table of string values."""
    widths = [max(map(len, column)) for column in zip(headers, *rows)]
    for row in [headers, tuple("-" * width for width in widths), *rows]:
        print("  ".join(value.ljust(width) for value, width in zip(row, widths)))


def ancestors(graph: Graph, kind: Identifier, predicate: URIRef) -> set[Identifier]:
    """Return all transitive parents of a kind under one relation."""
    return set(graph.transitive_objects(kind, predicate)) - {kind}


def describe_kind(graph: Graph, kind: Identifier) -> dict:
    """Extract a kind's description and OWL definition, excluding provenance."""
    definition = Graph()
    pending = [kind]
    seen = set()
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        for predicate, value in graph.predicate_objects(node):
            if predicate in (
                RDFS.label,
                RDFS.comment,
                SKOS.definition,
                OWL.equivalentClass,
            ) or (
                isinstance(node, BNode)
                and str(predicate).startswith((str(OWL), str(RDF)))
            ):
                definition.add((node, predicate, value))
                if not isinstance(value, Literal):
                    pending.append(value)
    lines = [
        f"{subject.n3()} {predicate.n3()} {value.n3()} ."
        for subject, predicate, value in to_canonical_graph(definition)
    ]
    return {
        "kind": str(kind),
        "label": str(graph.value(kind, RDFS.label) or label(kind)),
        "definition": "\n".join(sorted(lines)) or None,
    }


def resource_context(graph: Graph, kind: Identifier, effects: set[Identifier]) -> dict:
    """Describe a touched resource, its subtype/containment context, and effects."""
    containers = set(graph.transitive_subjects(AR.containsKind, kind)) - {kind}
    return {
        **describe_kind(graph, kind),
        "parents": [
            describe_kind(graph, parent)
            for parent in sorted(ancestors(graph, kind, AR.specializesKind), key=str)
        ],
        "contained_in": [
            describe_kind(graph, parent) for parent in sorted(containers, key=str)
        ],
        "effects": sorted(map(label, effects)),
    }


def route_reaches(
    graph: Graph, invocations: set[Identifier], source: Identifier, target: Identifier
) -> bool:
    """Check a possible mediation route, not actual runtime reachability."""
    seen = set()
    pending = [source]
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current not in seen and current in invocations:
            seen.add(current)
            pending.extend(graph.objects(current, AR.routesToKind))
    return False


def main() -> None:
    """Load and validate selected ontologies, report effects, and annotate pairs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-pairs",
        type=int,
        help="Maximum pairs to annotate (default: all; 0: skip)",
    )
    parser.add_argument(
        "--model",
        default="gpt-6-luna",
        help="OpenAI model (default: gpt-6-luna)",
    )
    args = parser.parse_args()
    if args.max_pairs is not None and args.max_pairs < 0:
        parser.error("--max-pairs must be non-negative")

    manifest = json.loads((ROOT / "manifest.json").read_text())
    if (
        not isinstance(manifest, list)
        or not all(isinstance(item, str) and item for item in manifest)
        or len(manifest) != len(set(manifest))
    ):
        raise SystemExit("manifest.json must be a list of unique ontology IDs")

    # Discover every graph once. A support graph under skills/ is still a module
    # when its RDF metadata says ar:OntologyModule.
    catalog = {}
    paths = sorted((ROOT / "universal").glob("*.trig")) + sorted(
        (ROOT / "skills").glob("*.trig")
    )
    for path in paths:
        graph = parse_graph(path)
        nodes = [(node, False) for node in graph.subjects(RDF.type, AR.OntologyModule)]
        nodes += [(node, True) for node in graph.subjects(RDF.type, AR.Skill)]
        if len(nodes) != 1:
            raise SystemExit(
                f"Expected one module or skill in {path.relative_to(ROOT)}"
            )
        node, is_skill = nodes[0]
        key = AR.skillDirectory if is_skill else AR.ontologyModuleId
        ontology_id = required_literal(graph, node, key)
        if ontology_id in catalog:
            raise SystemExit(f"Duplicate ontology ID: {ontology_id}")
        catalog[ontology_id] = {
            "graph": graph,
            "node": node,
            "skill": is_skill,
        }

    unknown = set(manifest) - catalog.keys()
    if unknown:
        raise SystemExit(
            "Unknown ontologies in manifest.json: " + ", ".join(sorted(unknown))
        )

    # Dependencies are checked before the combined graph is populated. They never
    # trigger automatic loading.
    selected = set(manifest)
    missing = [
        (ontology_id, str(dependency))
        for ontology_id in manifest
        for dependency in catalog[ontology_id]["graph"].objects(
            catalog[ontology_id]["node"], AR.requiresOntologyModule
        )
        if str(dependency) not in selected or catalog[str(dependency)]["skill"]
    ]
    if missing:
        for ontology_id, dependency in missing:
            print(
                f"WARNING: {ontology_id} requires unselected module {dependency}",
                file=sys.stderr,
            )
        raise SystemExit("Dependency preflight failed; no ontology graphs were loaded")

    combined = Graph().parse(ROOT / "universal/vocabulary.ttl", format="turtle")

    for ontology_id in manifest:
        entry = catalog[ontology_id]
        graph, node = entry["graph"], entry["node"]

        if entry["skill"]:
            source = Path(required_literal(graph, node, AR.sourcePath))
            expected_hash = required_literal(graph, node, AR.sourceSha256)
            if hashlib.sha256(source.read_bytes()).hexdigest() != expected_hash:
                raise SystemExit(
                    f"Ontology for {ontology_id} is stale: source skill changed"
                )
        else:
            repos = list(graph.objects(node, AR.sourceRepositoryPath))
            revisions = list(graph.objects(node, AR.sourceRevision))
            if len(repos) != len(revisions) or len(repos) > 1:
                raise SystemExit(f"Invalid source pin for {ontology_id}")
            if repos:
                actual = subprocess.check_output(
                    ["git", "-C", str(repos[0]), "rev-parse", "HEAD"], text=True
                ).strip()
                if actual != str(revisions[0]):
                    raise SystemExit(f"{ontology_id} is stale: source checkout changed")

            if (
                any(graph.subjects(RDF.type, AR.Operation))
                or any(graph.subjects(RDF.type, AR.PotentialEffect))
                or any(graph.triples((None, AR.declaresOperation, None)))
                or any(graph.triples((None, AR.hasPotentialEffect, None)))
            ):
                raise SystemExit(
                    f"Always-loaded graph contains operations: {ontology_id}"
                )
            if graph.value(node, AR.resourcesOnly) == Literal(True) and any(
                graph.subjects(RDF.type, AR.InvocationSurfaceKind)
            ):
                raise SystemExit(
                    f"Resource-only graph contains invocation kinds: {ontology_id}"
                )

        combined += graph

    world = set(combined.subjects(RDF.type, AR.WorldSurfaceKind))
    invocations = set(combined.subjects(RDF.type, AR.InvocationSurfaceKind))
    for predicate in (
        AR.specializesKind,
        AR.containsKind,
        AR.mayBeStoredAsKind,
        AR.sharesKind,
    ):
        for subject, target in combined.subject_objects(predicate):
            if subject not in world or target not in world:
                raise SystemExit(
                    f"Untyped resource relation: {subject} {predicate} {target}"
                )
    for subject, target in combined.subject_objects(AR.specializesInvocationKind):
        if subject not in invocations or target not in invocations:
            raise SystemExit(f"Untyped invocation relation: {subject} -> {target}")
    for subject, target in combined.subject_objects(AR.routesToKind):
        if subject not in invocations or target not in world | invocations:
            raise SystemExit(f"Untyped route: {subject} -> {target}")
    for subject, control in combined.subject_objects(AR.protectedByKind):
        if (
            subject not in world | invocations
            or control not in world
            or (control, RDF.type, AR.SecurityControlKind) not in combined
        ):
            raise SystemExit(f"Untyped control: {subject} -> {control}")
    for predicate in (AR.specializesKind, AR.specializesInvocationKind):
        if combined.query(f"ASK {{ ?kind <{predicate}>+ ?kind }}").askAnswer:
            raise SystemExit(f"Cycle in {predicate}")

    for kind in combined.subjects(RDF.type, AR.ToolEndpointKind):
        if kind not in invocations or (
            kind != AR.ToolEndpoint
            and AR.ToolEndpoint
            not in ancestors(combined, kind, AR.specializesInvocationKind)
        ):
            raise SystemExit(f"Tool endpoint lacks the shared parent: {kind}")

    public_endpoints = set(combined.subjects(RDF.type, AR.PublicInternetEndpointKind))
    for endpoint in public_endpoints:
        if endpoint not in world or (
            endpoint != AR.PublicInternetEndpoint
            and AR.PublicInternetEndpoint
            not in ancestors(combined, endpoint, AR.specializesKind)
        ):
            raise SystemExit(f"Public endpoint lacks the shared parent: {endpoint}")
    for call, endpoint in combined.subject_objects(AR.callEndpointKind):
        if endpoint not in public_endpoints:
            raise SystemExit(
                f"Internet call has unqualified endpoint: {call} -> {endpoint}"
            )

    shapes = Graph().parse(ROOT / "universal/shapes.ttl", format="turtle")
    defined = set(combined.subjects(OWL.equivalentClass, None)) & (world | invocations)
    unshaped = defined - set(shapes.objects(None, SH.targetClass))
    if unshaped:
        raise SystemExit(
            "Equivalent kinds without SHACL shapes: " + ", ".join(map(str, unshaped))
        )
    conforms, _, report = validate(combined, shacl_graph=shapes)
    if not conforms:
        raise SystemExit(f"SHACL validation failed:\n{report}")

    effects = set()
    touches = defaultdict(set)
    calls = []
    operations = set()
    skills = [ontology_id for ontology_id in manifest if catalog[ontology_id]["skill"]]
    for skill in skills:
        graph, node = catalog[skill]["graph"], catalog[skill]["node"]
        for operation in graph.objects(node, AR.declaresOperation):
            operations.add(operation)
            for effect in graph.objects(operation, AR.hasPotentialEffect):
                for effect_type in graph.objects(effect, AR.effectType):
                    for resource in graph.objects(effect, AR.affectsKind):
                        touches[resource].add(effect_type)
                        effects.add(
                            (
                                skill,
                                label(operation),
                                label(effect_type),
                                label(resource),
                            )
                        )
            for call in graph.objects(operation, AR.mayInitiateInternetCall):
                if (call, RDF.type, AR.PotentialInternetCall) not in graph:
                    raise SystemExit(f"Undeclared Internet call: {call}")
                invoked = set(graph.objects(operation, AR.invokedThroughKind))
                vias = set(graph.objects(call, AR.callViaKind))
                if not any(
                    route_reaches(combined, invocations, source, via)
                    for source in invoked
                    for via in vias
                ):
                    raise SystemExit(
                        f"No operation-to-call route: {operation} -> {call}"
                    )
                calls.append((skill, operation, call, graph))

    effect_rows = sorted(effects)
    calls.sort(key=lambda row: (row[0], str(row[1]), str(row[2])))
    print(f"Loaded skills: {', '.join(sorted(skills)) or '(none)'}")
    print(f"Operations: {len(operations)}")
    print(f"Potential effect/resource rows: {len(effect_rows)}")
    print(f"Potential Internet calls: {len(calls)}")
    if effect_rows:
        print("\nPotential effects:")
        print_table(("Skill", "Operation", "Effect", "Resource kind"), effect_rows)
    if calls:
        print("\nPotential Internet calls (possibilities, not observed traffic):")
        for skill, operation, call, graph in calls:
            vias = ", ".join(sorted(map(label, graph.objects(call, AR.callViaKind))))
            conditions = set(graph.objects(operation, AR.requires)) | set(
                graph.objects(call, AR.callConditionalOn)
            )
            stage = label(graph.value(call, AR.callStage))
            initiator = label(graph.value(call, AR.callInitiatorKind))
            endpoint = label(graph.value(call, AR.callEndpointKind))
            pattern = graph.value(call, AR.callEndpointPattern) or "(not established)"
            print(f"  {skill} / {label(operation)} -> {label(call)}")
            print(f"    {stage}: {initiator} via {vias}")
            print(f"    endpoint: {endpoint}  [{pattern}]")
            print(
                f"    conditions: {', '.join(sorted(map(label, conditions))) or '(none recorded)'}"
            )

    resources = [
        resource_context(combined, kind, effect_types)
        for kind, effect_types in touches.items()
    ]
    analyze_pairs(resources, max_pairs=args.max_pairs, model=args.model)


if __name__ == "__main__":
    main()
