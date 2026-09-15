from pathlib import Path
import hashlib
import json
import sys

from rdflib import Dataset, Graph, Namespace, URIRef
from rdflib.namespace import RDF
from pyshacl import validate

ONTOLOGY_DIR = Path(__file__).resolve().parent
AR = Namespace("urn:agent-risk:")

# Pass skill directory names as arguments, or use these defaults.
# --baseline-only runs without any skill graphs.
arguments = sys.argv[1:]
if "--baseline-only" in arguments and arguments != ["--baseline-only"]:
    raise SystemExit("Use --baseline-only by itself.")
loaded_skills = (
    set() if arguments == ["--baseline-only"]
    else set(arguments) or {"discord", "gh-issues"}
)

manifest = json.loads((ONTOLOGY_DIR / "manifest.json").read_text())
modules = {module["directory"]: module for module in manifest["modules"]}

unknown = loaded_skills - modules.keys()
if unknown:
    raise SystemExit(f"Unknown skills: {', '.join(sorted(unknown))}")

# Preserve separate named graphs for querying.
active = Dataset()

# SHACL validates the union of the vocabulary, baselines, and loaded skill graphs.
combined = Graph()
vocabulary = Graph().parse(
    str(ONTOLOGY_DIR / manifest["vocabulary"]),
    format="turtle",
)
for triple in vocabulary:
    combined.add(triple)

# These resource catalogues are loaded even when access to their concrete
# resources is not confirmed by a runtime inventory.
shared_kinds = set()
for baseline in manifest["baselines"]:
    parsed = Dataset()
    parsed.parse(str(ONTOLOGY_DIR / baseline["file"]), format="trig")

    graph_id = URIRef(baseline["graph"])
    source_graph = parsed.graph(graph_id)
    if len(source_graph) == 0:
        raise SystemExit(f"Missing or empty baseline graph: {graph_id}")

    target_graph = active.graph(graph_id)
    for triple in source_graph:
        target_graph.add(triple)
        combined.add(triple)
    if any(target_graph.subjects(RDF.type, AR.Operation)):
        raise SystemExit(f"Baseline must not contain operations: {graph_id}")
    shared_kinds.update(target_graph.objects(None, AR.declaresKind))

for skill_name in sorted(loaded_skills):
    module = modules[skill_name]

    source = Path(manifest["sourceRoot"]) / skill_name / "SKILL.md"
    actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual_hash != module["skillSha256"]:
        raise SystemExit(f"Ontology for {skill_name} is stale: SKILL.md has changed.")

    parsed = Dataset()
    parsed.parse(str(ONTOLOGY_DIR / module["file"]), format="trig")

    graph_id = URIRef(module["graph"])
    source_graph = parsed.graph(graph_id)
    if len(source_graph) == 0:
        raise SystemExit(f"Missing or empty named graph: {graph_id}")

    target_graph = active.graph(graph_id)
    for triple in source_graph:
        target_graph.add(triple)
        combined.add(triple)
    for shared_kind in target_graph.objects(None, AR.usesSharedKind):
        if shared_kind not in shared_kinds:
            raise SystemExit(f"Unresolved shared-kind citation in {skill_name}: {shared_kind}")
    for _, parent_kind in target_graph.subject_objects(AR.specializesKind):
        if parent_kind not in shared_kinds:
            raise SystemExit(f"Unresolved shared-kind specialization in {skill_name}: {parent_kind}")

shapes = Graph().parse(
    str(ONTOLOGY_DIR / manifest["shapes"]),
    format="turtle",
)
conforms, _, report = validate(combined, shacl_graph=shapes)
if not conforms:
    raise SystemExit(f"SHACL validation failed:\n{report}")

baseline_query = """
PREFIX ar: <urn:agent-risk:>

SELECT DISTINCT ?graph ?kind
WHERE {
  GRAPH ?graph {
    ?baseline a ar:HarnessBaseline ; ar:declaresKind ?kind .
  }
}
ORDER BY ?graph ?kind
"""

citation_query = """
PREFIX ar: <urn:agent-risk:>

SELECT DISTINCT ?graph ?sharedKind
WHERE {
  GRAPH ?graph {
    ?skill a ar:Skill ; ar:usesSharedKind ?sharedKind .
  }
}
ORDER BY ?graph ?sharedKind
"""

effect_query = """
PREFIX ar: <urn:agent-risk:>

SELECT DISTINCT ?graph ?operation ?effectType ?resourceKind
WHERE {
  GRAPH ?graph {
    ?skill a ar:Skill ; ar:declaresOperation ?operation .
    ?operation ar:hasPotentialEffect ?effect .
    ?effect ar:effectType ?effectType ;
            ar:affectsKind ?resourceKind .
  }
}
ORDER BY ?graph ?operation ?effectType ?resourceKind
"""

def label(value):
    """Display the local part of an urn:agent-risk: identifier."""
    return str(value).rsplit(":", 1)[-1]


baseline_rows = [
    (label(row.graph), label(row.kind))
    for row in active.query(baseline_query)
]
citation_rows = [
    (label(row.graph), label(row.sharedKind))
    for row in active.query(citation_query)
]
parent_by_kind = {
    narrower: parent
    for module in manifest["modules"]
    if module["directory"] in loaded_skills
    for narrower, parent in active.graph(URIRef(module["graph"])).subject_objects(AR.specializesKind)
}
effect_rows = [
    (
        label(row.graph), label(row.operation), label(row.effectType),
        label(row.resourceKind),
        label(row.resourceKind) if row.resourceKind in shared_kinds else
        label(parent_by_kind[row.resourceKind]) if row.resourceKind in parent_by_kind else "",
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


print(f"Always-loaded baselines: {', '.join(b['name'] for b in manifest['baselines'])}")
print(f"Loaded skills: {', '.join(sorted(loaded_skills)) or '(none)'}")
print(f"Shared resource kinds: {len(baseline_rows)}")
print(f"Skill shared-kind citations: {len(citation_rows)}")
print(f"Skill potential-effect rows: {len(effect_rows)}\n")
print_table(("Graph", "Shared resource kind"), baseline_rows)
if citation_rows:
    print()
    print_table(("Skill graph", "Cited shared kind"), citation_rows)
if effect_rows:
    print()
    print_table(("Graph", "Operation", "Effect", "Resource kind", "Shared parent"), effect_rows)
