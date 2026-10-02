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
from table_output import print_table

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


def names(nodes: set[Identifier]) -> str:
    """Render a set of RDF identifiers in stable, compact form."""
    return ", ".join(sorted(map(label, nodes))) or "(none recorded)"


def notes(graph: Graph, node: Identifier, predicate: URIRef = RDFS.comment) -> str:
    """Render any recorded prose for a node without inventing a description."""
    return " ".join(sorted(map(str, set(graph.objects(node, predicate)))))


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
        AR.mayResideInKind,
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
    for skill, control in combined.subject_objects(AR.subjectToControlKind):
        if (
            (skill, RDF.type, AR.Skill) not in combined
            or (control, RDF.type, AR.SecurityControlKind) not in combined
        ):
            raise SystemExit(f"Untyped skill control: {skill} -> {control}")
    for mount, resource in combined.subject_objects(AR.mountExposesKind):
        if (
            mount not in world
            or AR.NanoClawMount
            not in ancestors(combined, mount, AR.specializesKind)
            or resource not in world
        ):
            raise SystemExit(f"Untyped mount exposure: {mount} -> {resource}")
    components = set(combined.subjects(RDF.type, AR.SystemComponentKind))
    for subject, side in combined.subject_objects(AR.locatedOn):
        if subject not in world or side not in components:
            raise SystemExit(f"Untyped location side: {subject} -> {side}")
    for subject, side in combined.subject_objects(AR.executesOn):
        if subject not in invocations or side not in components:
            raise SystemExit(f"Untyped execution side: {subject} -> {side}")
    for mount, source in combined.subject_objects(AR.bindsFromKind):
        if (mount, AR.mountExposesKind, None) not in combined or source not in world:
            raise SystemExit(f"Untyped bind source: {mount} -> {source}")
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
    operation_rows = []
    skills = [ontology_id for ontology_id in manifest if catalog[ontology_id]["skill"]]
    for skill in skills:
        graph, node = catalog[skill]["graph"], catalog[skill]["node"]
        for operation in graph.objects(node, AR.declaresOperation):
            operations.add(operation)
            operation_rows.append((skill, operation, graph))
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
    operation_rows.sort(key=lambda row: (row[0], str(row[1])))
    calls.sort(key=lambda row: (row[0], str(row[1]), str(row[2])))
    native = sorted(set(combined.subjects(RDF.type, AR.NativeCapability)), key=str)
    native_touches = defaultdict(set)
    for capability in native:
        for resource in combined.objects(capability, AR.nativeResourceKind):
            native_touches[resource].update(
                combined.objects(capability, AR.nativeEffectType)
            )
    print_table(
        "Ontology report",
        ("Metric", "Value"),
        [
            ("Loaded skills", ", ".join(sorted(skills)) or "(none)"),
            ("Operations", str(len(operations))),
            ("Potential effect/resource rows", str(len(effect_rows))),
            ("Native endpoint capabilities", str(len(native))),
            ("Potential Internet calls", str(len(calls))),
        ],
        (32, 88),
    )
    if skills:
        print_table(
            "Skill control context (candidate gates, not blanket grants)",
            ("Skill", "Relevant controls"),
            [
                (
                    skill,
                    names(
                        set(
                            catalog[skill]["graph"].objects(
                                catalog[skill]["node"], AR.subjectToControlKind
                            )
                        )
                    ),
                )
                for skill in sorted(skills)
            ],
            (28, 92),
        )
    if operation_rows:
        rows = []
        for skill, operation, graph in operation_rows:
            key = f"{skill} / {label(operation)}"
            rows.extend(
                [
                    (key, "Via", names(set(graph.objects(operation, AR.invokedThroughKind)))),
                    (key, "Targets", names(set(graph.objects(operation, AR.targetsKind)))),
                    (key, "Requires", names(set(graph.objects(operation, AR.requires)))),
                    (key, "Evidence", names(set(graph.objects(operation, AR.sourceStatus)))),
                    (key, "Adaptation", names(set(graph.objects(operation, AR.adaptationStatus)))),
                ]
            )
            if note := notes(graph, operation, AR.sourceNote):
                rows.append((key, "Note", note))
            for effect_type, resource in sorted(
                {
                    (effect_type, resource)
                    for effect in graph.objects(operation, AR.hasPotentialEffect)
                    for effect_type in graph.objects(effect, AR.effectType)
                    for resource in graph.objects(effect, AR.affectsKind)
                },
                key=lambda row: (str(row[0]), str(row[1])),
            ):
                rows.append((key, "Effect", f"{label(effect_type)} → {label(resource)}"))
        print_table(
            "Skill operations (possible effects, not observed actions)",
            ("Skill / operation", "Field", "Details"),
            rows,
            (38, 14, 70),
        )
    if native:
        rows = []
        for capability in native:
            key = label(capability)
            endpoint = combined.value(capability, AR.nativeEndpointKind)
            resource = combined.value(capability, AR.nativeResourceKind)
            effect_types_text = names(
                set(combined.objects(capability, AR.nativeEffectType))
            )
            rows.extend(
                [
                    (key, "Endpoint", label(endpoint)),
                    (key, "Effects", f"{effect_types_text} → {label(resource)}"),
                    (key, "Scope", names(set(combined.objects(capability, AR.nativeScopeKind)))),
                    (key, "Requires", names(set(combined.objects(capability, AR.nativeRequires)))),
                    (key, "Note", notes(combined, capability, AR.sourceNote)),
                ]
            )
        print_table(
            "Native endpoint capabilities (independent of skills; conditional)",
            ("Capability", "Field", "Details"),
            rows,
            (36, 14, 72),
        )
    mounts = sorted(set(combined.subjects(AR.mountExposesKind, None)), key=str)
    if mounts:
        rows = []
        for mount in mounts:
            key = label(mount)
            rows.extend(
                [
                    (key, "Mode", names(set(combined.objects(mount, AR.mountAccessMode)))),
                    (key, "Container path", names(set(combined.objects(mount, AR.containerPath)))),
                    (key, "Exposes", names(set(combined.objects(mount, AR.mountExposesKind)))),
                ]
            )
            for source in sorted(combined.objects(mount, AR.bindsFromKind), key=str):
                pattern = names(set(combined.objects(source, AR.hostPathPattern)))
                rows.append((key, "Host source", f"{label(source)} ({pattern})"))
            conditions = set(combined.objects(mount, AR.mountConditionalOn))
            if conditions:
                rows.append((key, "Requires", names(conditions)))
        print_table(
            "Container mount exposures and host sources (alternatives; not effective file permissions)",
            ("Mount", "Field", "Details"),
            rows,
            (36, 14, 72),
        )
    affected = set(touches) | set(native_touches)
    if affected:
        rows = []
        for resource in sorted(affected, key=str):
            key = label(resource)
            start = len(rows)
            if definition := notes(combined, resource):
                rows.append((key, "Definition", definition))
            parents = ancestors(combined, resource, AR.specializesKind)
            if parents:
                rows.append((key, "Subtypes of", names(parents)))
            containers = set(combined.subjects(AR.containsKind, resource))
            if containers:
                rows.append((key, "Contained in", names(containers)))
            locations = set(combined.transitive_objects(resource, AR.mayResideInKind)) - {
                resource
            }
            if locations:
                rows.append((key, "May reside in", names(locations)))
            mounts_for_resource = {
                mount
                for location in locations | {resource}
                for mount in combined.subjects(AR.mountExposesKind, location)
            }
            if mounts_for_resource:
                rows.append((key, "Possible mounts", names(mounts_for_resource)))
            controls = set(combined.objects(resource, AR.protectedByKind))
            for parent in parents:
                controls.update(combined.objects(parent, AR.protectedByKind))
            if controls:
                rows.append((key, "Controls", names(controls)))
            if len(rows) == start:
                rows.append((key, "Context", "(no further description recorded)"))
        print_table(
            "Affected resource kinds (type-level context)",
            ("Resource kind", "Field", "Details"),
            rows,
            (36, 18, 68),
        )
    if calls:
        rows = []
        for skill, operation, call, graph in calls:
            key = f"{skill} / {label(operation)}"
            vias = names(set(graph.objects(call, AR.callViaKind)))
            conditions = set(graph.objects(operation, AR.requires)) | set(
                graph.objects(call, AR.callConditionalOn)
            )
            stage = label(graph.value(call, AR.callStage))
            initiator = label(graph.value(call, AR.callInitiatorKind))
            endpoint = label(graph.value(call, AR.callEndpointKind))
            pattern = graph.value(call, AR.callEndpointPattern) or "(not established)"
            rows.extend(
                [
                    (key, "Call", label(call)),
                    (key, "Stage / initiator", f"{stage} / {initiator}"),
                    (key, "Via", vias),
                    (key, "Endpoint", endpoint),
                    (key, "Pattern", str(pattern)),
                    (key, "Conditions", names(conditions)),
                ]
            )
        print_table(
            "Potential Internet calls (possibilities, not observed traffic)",
            ("Skill / operation", "Field", "Details"),
            rows,
            (38, 18, 68),
        )

    analysis_touches = defaultdict(set)
    for source in (touches, native_touches):
        for kind, effect_types in source.items():
            analysis_touches[kind].update(effect_types)
    resources = [
        resource_context(combined, kind, effect_types)
        for kind, effect_types in analysis_touches.items()
    ]
    analyze_pairs(resources, max_pairs=args.max_pairs, model=args.model)


if __name__ == "__main__":
    main()
