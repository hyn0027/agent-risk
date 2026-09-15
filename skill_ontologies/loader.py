from pathlib import Path
import hashlib
import json
import sys

from rdflib import Dataset, Graph, Namespace, URIRef
from rdflib.namespace import RDF
from pyshacl import validate


ONTOLOGY_DIR = Path(__file__).resolve().parent
AR = Namespace("urn:agent-risk:")

# --universal-only selects all always-loaded graphs without skill graphs.
# Previous spellings remain aliases.
arguments = sys.argv[1:]
universal_only = arguments in (
    ["--universal-only"], ["--resources-only"], ["--baseline-only"]
)
if any(arg.startswith("--") for arg in arguments) and not universal_only:
    raise SystemExit("Use --universal-only by itself, or pass skill directory names.")
loaded_skills = set() if universal_only else set(arguments) or {"discord", "gh-issues"}

manifest = json.loads((ONTOLOGY_DIR / "manifest.json").read_text())
modules = {module["directory"]: module for module in manifest["modules"]}
unknown = loaded_skills - modules.keys()
if unknown:
    raise SystemExit(f"Unknown skills: {', '.join(sorted(unknown))}")

active = Dataset()  # Retains provenance as one named graph per source file.
combined = Graph()  # Union for cross-graph checks, hierarchy, and SHACL.
vocabulary = Graph().parse(
    str(ONTOLOGY_DIR / manifest["vocabulary"]), format="turtle"
)
for triple in vocabulary:
    combined.add(triple)


def load_named_graph(entry):
    parsed = Dataset()
    parsed.parse(str(ONTOLOGY_DIR / entry["file"]), format="trig")
    graph_id = URIRef(entry["graph"])
    source_graph = parsed.graph(graph_id)
    if len(source_graph) == 0:
        raise SystemExit(f"Missing or empty named graph: {graph_id}")
    target_graph = active.graph(graph_id)
    for triple in source_graph:
        target_graph.add(triple)
        combined.add(triple)
    return target_graph


# Loading policy lives in the manifest, not in the ontology vocabulary.
always_loaded_graphs = manifest["alwaysLoadedGraphs"]
for entry in always_loaded_graphs:
    graph = load_named_graph(entry)
    if any(graph.subjects(RDF.type, AR.Operation)) or any(
        graph.subjects(RDF.type, AR.PotentialEffect)
    ):
        raise SystemExit(f"Always-loaded graph contains an operation/effect: {entry['file']}")
    if any(graph.triples((None, AR.declaresOperation, None))) or any(
        graph.triples((None, AR.hasPotentialEffect, None))
    ):
        raise SystemExit(f"Always-loaded graph contains an operation relation: {entry['file']}")
    if entry.get("resourcesOnly") and any(
        graph.subjects(RDF.type, AR.InvocationSurfaceKind)
    ):
        raise SystemExit(f"Resource-only graph contains an invocation kind: {entry['file']}")

# Skill-declared dependencies are loaded once, before the corresponding skill graph.
# Ontology modules are not universally active; selecting an unrelated skill leaves
# these mediator kinds out of the active union.
ontology_modules = {entry["id"]: entry for entry in manifest.get("ontologyModules", [])}
if len(ontology_modules) != len(manifest.get("ontologyModules", [])):
    raise SystemExit("Duplicate ontology module id in manifest")
resolved_dependencies = []
visiting = set()
loaded_dependencies = set()


def load_dependency(module_id):
    if module_id in loaded_dependencies:
        return
    if module_id in visiting:
        raise SystemExit(f"Cycle in ontology dependencies at {module_id}")
    entry = ontology_modules.get(module_id)
    if entry is None:
        raise SystemExit(f"Unknown ontology dependency: {module_id}")
    visiting.add(module_id)
    for required_id in entry.get("dependsOn", []):
        load_dependency(required_id)
    load_named_graph(entry)
    visiting.remove(module_id)
    loaded_dependencies.add(module_id)
    resolved_dependencies.append(module_id)


for skill_name in sorted(loaded_skills):
    for required_id in modules[skill_name].get("dependsOn", []):
        load_dependency(required_id)

for skill_name in sorted(loaded_skills):
    module = modules[skill_name]
    source = Path(manifest["sourceRoot"]) / skill_name / "SKILL.md"
    actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual_hash != module["skillSha256"]:
        raise SystemExit(f"Ontology for {skill_name} is stale: SKILL.md has changed.")
    load_named_graph(module)

typed_kinds = set(combined.subjects(RDF.type, AR.WorldSurfaceKind))
typed_invocation_kinds = set(combined.subjects(RDF.type, AR.InvocationSurfaceKind))
relations = (
    (AR.specializesKind, "is-a"),
    (AR.containsKind, "contains"),
    (AR.mayBeStoredAsKind, "may be stored as"),
)
for predicate, relation_name in relations:
    for subject, related in combined.subject_objects(predicate):
        if subject not in typed_kinds or related not in typed_kinds:
            raise SystemExit(
                f"Untyped kind in {relation_name} relation: {subject} -> {related}"
            )
if combined.query(
    "ASK { ?kind <urn:agent-risk:specializesKind>+ ?kind }"
).askAnswer:
    raise SystemExit("Cycle in is-a hierarchy")
for narrower, broader in combined.subject_objects(AR.specializesInvocationKind):
    if narrower not in typed_invocation_kinds or broader not in typed_invocation_kinds:
        raise SystemExit(f"Untyped invocation kind: {narrower} -> {broader}")
if combined.query(
    "ASK { ?kind <urn:agent-risk:specializesInvocationKind>+ ?kind }"
).askAnswer:
    raise SystemExit("Cycle in invocation-kind hierarchy")
for source, destination in combined.subject_objects(AR.routesToKind):
    if source not in typed_invocation_kinds or destination not in (
        typed_invocation_kinds | typed_kinds
    ):
        raise SystemExit(f"Untyped mediation route: {source} -> {destination}")

shapes = Graph().parse(str(ONTOLOGY_DIR / manifest["shapes"]), format="turtle")
conforms, _, report = validate(combined, shacl_graph=shapes)
if not conforms:
    raise SystemExit(f"SHACL validation failed:\n{report}")


def label(value):
    return str(value).rsplit(":", 1)[-1]


def ancestors(kind):
    """All broader kinds, across any active graph; multiple parents are allowed."""
    seen = set()
    frontier = list(combined.objects(kind, AR.specializesKind))
    while frontier:
        parent = frontier.pop()
        if parent not in seen:
            seen.add(parent)
            frontier.extend(combined.objects(parent, AR.specializesKind))
    return sorted(seen, key=str)


def invocation_ancestors(kind):
    seen = set()
    frontier = list(combined.objects(kind, AR.specializesInvocationKind))
    while frontier:
        parent = frontier.pop()
        if parent not in seen:
            seen.add(parent)
            frontier.extend(combined.objects(parent, AR.specializesInvocationKind))
    return seen


declared_tool_endpoint_kinds = set(combined.subjects(RDF.type, AR.ToolEndpointKind))
for kind in declared_tool_endpoint_kinds:
    if kind not in typed_invocation_kinds:
        raise SystemExit(f"Tool endpoint kind is not an invocation kind: {kind}")
    if kind != AR.ToolEndpoint and AR.ToolEndpoint not in invocation_ancestors(kind):
        raise SystemExit(f"Tool endpoint kind lacks ToolEndpoint parent: {kind}")
tool_endpoint_rows = sorted(
    {(label(kind), "declared" if kind in declared_tool_endpoint_kinds else "inherited")
     for kind in typed_invocation_kinds
     if kind == AR.ToolEndpoint or AR.ToolEndpoint in invocation_ancestors(kind)}
)


def shell_mediated(operation):
    return any(
        channel == AR.ShellExecution or AR.ShellExecution in invocation_ancestors(channel)
        for channel in combined.objects(operation, AR.invokedThroughKind)
    )


def messaging_route(operation):
    return any(
        channel in (AR.OpenClawMessageTool, AR.OpenClawMessageCLI)
        or channel == AR.MessagingChannelInvocation
        or AR.MessagingChannelInvocation in invocation_ancestors(channel)
        for channel in combined.objects(operation, AR.invokedThroughKind)
    )


resource_rows = sorted(
    {
        (label(URIRef(entry["graph"])), label(kind))
        for entry in always_loaded_graphs
        for kind in active.graph(URIRef(entry["graph"])).subjects(
            RDF.type, AR.WorldSurfaceKind
        )
    }
)
relationship_rows = sorted(
    {
        (label(subject), relation_name, label(related))
        for predicate, relation_name in relations
        for subject, related in combined.subject_objects(predicate)
    }
)
invocation_rows = sorted(
    {
        (label(narrower), label(broader))
        for narrower, broader in combined.subject_objects(AR.specializesInvocationKind)
    }
)
route_rows = sorted(
    {
        (label(source), label(destination))
        for source, destination in combined.subject_objects(AR.routesToKind)
    }
)

effect_query = """
PREFIX ar: <urn:agent-risk:>

SELECT DISTINCT ?graph ?operation ?effectType ?resourceKind
WHERE {
  GRAPH ?graph {
    ?skill a ar:Skill ; ar:declaresOperation ?operation .
    ?operation ar:hasPotentialEffect ?effect .
    ?effect ar:effectType ?effectType ; ar:affectsKind ?resourceKind .
  }
}
ORDER BY ?graph ?operation ?effectType ?resourceKind
"""
effect_rows = [
    (
        label(row.graph), label(row.operation), label(row.effectType),
        label(row.resourceKind),
        ", ".join(label(parent) for parent in ancestors(row.resourceKind)),
        "yes" if shell_mediated(row.operation) else "no",
        "yes" if messaging_route(row.operation) else "no",
    )
    for row in active.query(effect_query)
]


def print_table(headers, rows):
    widths = [
        max(len(header), *(len(row[i]) for row in rows))
        for i, header in enumerate(headers)
    ]

    def print_row(values):
        print("  ".join(value.ljust(width) for value, width in zip(values, widths)))

    print_row(headers)
    print_row(tuple("-" * width for width in widths))
    for row in rows:
        print_row(row)


print("Always-loaded graphs: " + ", ".join(e["file"] for e in always_loaded_graphs))
print("Auto-loaded ontology dependencies: " + (", ".join(resolved_dependencies) or "(none)"))
print(f"Loaded skills: {', '.join(sorted(loaded_skills)) or '(none)'}")
print(f"Resource kinds: {len(resource_rows)}")
print(f"Resource relationships: {len(relationship_rows)}")
print(f"Invocation subtype links: {len(invocation_rows)}")
print(f"Tool endpoint kinds: {len(tool_endpoint_rows)}")
print(f"Invocation routes: {len(route_rows)}")
print(f"Skill potential-effect rows: {len(effect_rows)}\n")
print_table(("Graph", "Resource kind"), resource_rows)
if relationship_rows:
    print()
    print_table(("Kind", "Relation", "Related kind"), relationship_rows)
if invocation_rows:
    print()
    print_table(("Invocation kind", "Broader invocation kind"), invocation_rows)
if tool_endpoint_rows:
    print()
    print_table(("Tool endpoint kind", "Classification"), tool_endpoint_rows)
if route_rows:
    print()
    print_table(("Invocation kind", "Routes to kind"), route_rows)
if effect_rows:
    print()
    print_table(("Graph", "Operation", "Effect", "Resource kind", "Broader kinds", "Shell-mediated", "Messaging-route"), effect_rows)
