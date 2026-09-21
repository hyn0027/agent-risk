from pathlib import Path
import hashlib
import json
import subprocess
import sys

from rdflib import Dataset, Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from owlrl import DeductiveClosure, OWLRL_Semantics
from pyshacl import validate


ONTOLOGY_DIR = Path(__file__).resolve().parent
AR = Namespace("urn:agent-risk:")
SH = Namespace("http://www.w3.org/ns/shacl#")

# --universal-only selects all always-loaded graphs without skill graphs.
# --data FILE adds concrete observations for OWL-RL classification and SHACL.
# Previous universal-only spellings remain aliases.
arguments = sys.argv[1:]
universal_flags = {"--universal-only", "--resources-only", "--baseline-only"}
universal_only = False
data_path = None
skill_arguments = []
index = 0
while index < len(arguments):
    argument = arguments[index]
    if argument in universal_flags:
        universal_only = True
    elif argument == "--data":
        index += 1
        if index == len(arguments):
            raise SystemExit("--data requires an RDF file path")
        data_path = Path(arguments[index]).expanduser()
    elif argument.startswith("--"):
        raise SystemExit("Use --universal-only, --data FILE, or skill directory names.")
    else:
        skill_arguments.append(argument)
    index += 1
if universal_only and skill_arguments:
    raise SystemExit("--universal-only cannot be combined with skill directory names.")
loaded_skills = set() if universal_only else set(skill_arguments) or {"discord", "gh-issues"}

manifest = json.loads((ONTOLOGY_DIR / "manifest.json").read_text())

# Pin the universal environment model to the NanoClaw checkout it was reviewed
# against. Like skill hashes below, this detects source drift; it does not
# attest to a deployed process or live configuration.
environment_source = manifest.get("environmentSource")
if environment_source:
    repository_path = Path(environment_source["repositoryPath"])
    expected_revision = environment_source["revision"]
    if not repository_path.exists():
        raise SystemExit(f"NanoClaw source checkout not found: {repository_path}")
    result = subprocess.run(
        ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"Cannot read NanoClaw source revision: {result.stderr.strip()}")
    actual_revision = result.stdout.strip()
    if actual_revision != expected_revision:
        raise SystemExit(
            "NanoClaw ontology is stale: source checkout is at "
            f"{actual_revision}, expected {expected_revision}."
        )
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


# The manifest catalogs graph modules; load-config.json holds deployment policy.
ontology_modules = {entry["id"]: entry for entry in manifest.get("ontologyModules", [])}
if len(ontology_modules) != len(manifest.get("ontologyModules", [])):
    raise SystemExit("Duplicate ontology module id in manifest")
load_config_path = ONTOLOGY_DIR / manifest["loadConfig"]
load_config = json.loads(load_config_path.read_text())
always_loaded_ids = load_config.get("alwaysLoaded", [])
if len(always_loaded_ids) != len(set(always_loaded_ids)):
    raise SystemExit("Duplicate module id in load-config.json alwaysLoaded")
unknown_always_loaded = set(always_loaded_ids) - ontology_modules.keys()
if unknown_always_loaded:
    raise SystemExit(
        "Unknown always-loaded ontology modules: "
        + ", ".join(sorted(unknown_always_loaded))
    )

# Dependency resolution is deliberately static. A dependency declaration never
# causes a graph to load: every required module must already be introduced by
# load-config.json. Preflight completes before any named graph is loaded.
dependency_requirements = []
for module_id in always_loaded_ids:
    for required_id in ontology_modules[module_id].get("dependsOn", []):
        dependency_requirements.append((module_id, required_id))
for skill_name in sorted(loaded_skills):
    for required_id in modules[skill_name].get("dependsOn", []):
        dependency_requirements.append((skill_name, required_id))

unknown_required = {
    required_id
    for _, required_id in dependency_requirements
    if required_id not in ontology_modules
}
missing_dependencies = [
    (requester, required_id)
    for requester, required_id in dependency_requirements
    if required_id in ontology_modules and required_id not in always_loaded_ids
]
if unknown_required or missing_dependencies:
    for required_id in sorted(unknown_required):
        print(
            f"WARNING: required ontology dependency {required_id} is not cataloged "
            "in manifest.json",
            file=sys.stderr,
        )
    for requester, required_id in missing_dependencies:
        print(
            f"WARNING: {requester} requires ontology dependency {required_id}, but "
            f"{manifest['loadConfig']} does not introduce it in alwaysLoaded",
            file=sys.stderr,
        )
    raise SystemExit(
        "Dependency preflight failed; no ontology graphs were loaded. "
        f"Add every required module to {manifest['loadConfig']} alwaysLoaded."
    )

always_loaded_graphs = [ontology_modules[module_id] for module_id in always_loaded_ids]
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

for skill_name in sorted(loaded_skills):
    module = modules[skill_name]
    source = Path(manifest["sourceRoot"]) / skill_name / "SKILL.md"
    actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual_hash != module["skillSha256"]:
        raise SystemExit(f"Ontology for {skill_name} is stale: SKILL.md has changed.")
    load_named_graph(module)

observation_subjects = set()
asserted_observation_types = set()
if data_path is not None:
    if not data_path.is_absolute():
        data_path = (Path.cwd() / data_path).resolve()
    observations = Graph().parse(str(data_path))
    observation_subjects = set(observations.subjects())
    asserted_observation_types = set(observations.triples((None, RDF.type, None)))
    observation_graph = active.graph(URIRef("urn:agent-risk:g_observations"))
    for triple in observations:
        observation_graph.add(triple)
        combined.add(triple)

typed_kinds = set(combined.subjects(RDF.type, AR.WorldSurfaceKind))
typed_invocation_kinds = set(combined.subjects(RDF.type, AR.InvocationSurfaceKind))
relations = (
    (AR.specializesKind, "is-a"),
    (AR.containsKind, "contains"),
    (AR.mayBeStoredAsKind, "may be stored as"),
    (AR.sharesKind, "shares"),
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
for subject, control in combined.subject_objects(AR.protectedByKind):
    if subject not in (typed_invocation_kinds | typed_kinds):
        raise SystemExit(f"Untyped protected surface: {subject} -> {control}")
    if control not in typed_kinds or (control, RDF.type, AR.SecurityControlKind) not in combined:
        raise SystemExit(f"Untyped security control: {subject} -> {control}")

subtype_kinds = set(combined.subjects(AR.specializesKind, None)) | set(
    combined.subjects(AR.specializesInvocationKind, None)
)
defined_kinds = {
    kind for kind in combined.subjects(OWL.equivalentClass, None)
    if kind in typed_kinds or kind in typed_invocation_kinds
}

shapes = Graph().parse(str(ONTOLOGY_DIR / manifest["shapes"]), format="turtle")
shape_targets = set(shapes.objects(None, SH.targetClass))
missing_validation_shapes = defined_kinds - shape_targets
if missing_validation_shapes:
    raise SystemExit(
        "Necessary-and-sufficient kinds missing SHACL validation shapes: "
        + ", ".join(sorted(str(kind) for kind in missing_validation_shapes))
    )
conforms, _, report = validate(combined, shacl_graph=shapes)
if not conforms:
    raise SystemExit(f"SHACL validation failed:\n{report}")

# OWL supplies positive, open-world inference for necessary-and-sufficient
# definitions. A second, focus-limited SHACL pass checks inferred observation
# memberships without applying ontology-meta-shapes to OWL's internal blank nodes.
reasoned = Graph()
for triple in combined:
    reasoned.add(triple)
for predicate in (AR.specializesKind, AR.specializesInvocationKind):
    for narrower, broader in combined.subject_objects(predicate):
        reasoned.add((narrower, RDF.type, OWL.Class))
        reasoned.add((broader, RDF.type, OWL.Class))
        reasoned.add((narrower, RDFS.subClassOf, broader))
DeductiveClosure(OWLRL_Semantics).expand(reasoned)
if observation_subjects:
    conforms, _, report = validate(
        reasoned,
        shacl_graph=shapes,
        focus_nodes=list(observation_subjects),
    )
    if not conforms:
        raise SystemExit(f"SHACL validation failed for observation data:\n{report}")


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
        channel == AR.MessagingChannelInvocation
        or AR.MessagingChannelInvocation in invocation_ancestors(channel)
        for channel in combined.objects(operation, AR.invokedThroughKind)
    )


def route_reaches(source, target):
    """Follow type-level mediation routes; results are possible paths, not runtime reachability."""
    seen = set()
    frontier = list(combined.objects(source, AR.routesToKind))
    while frontier:
        item = frontier.pop()
        if item == target:
            return True
        if item in seen:
            continue
        seen.add(item)
        if item in typed_invocation_kinds:
            frontier.extend(combined.objects(item, AR.routesToKind))
    return False


def nanoclaw_mailbox_route(operation):
    return any(
        route_reaches(channel, AR.NanoClawOutboundMailboxWrite)
        or route_reaches(channel, AR.NanoClawInboundMailboxWrite)
        for channel in combined.objects(operation, AR.invokedThroughKind)
    )


legacy_openclaw_surfaces = {
    AR.OpenClawMessageTool,
    AR.OpenClawMessageCLI,
    AR.OpenClawConfigCLI,
    AR.OpenClawTaskFlowRuntime,
}
legacy_openclaw_operations = sorted(
    {
        operation
        for operation in combined.subjects(RDF.type, AR.Operation)
        if any(
            channel in legacy_openclaw_surfaces
            or AR.OpenClawChannelPlugin in invocation_ancestors(channel)
            for channel in combined.objects(operation, AR.invokedThroughKind)
        )
    },
    key=str,
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
control_rows = sorted(
    {
        (label(subject), label(control))
        for subject, control in combined.subject_objects(AR.protectedByKind)
    }
)
definition_rows = sorted(
    {
        (
            label(kind),
            "necessary+sufficient (OWL + SHACL)"
            if kind in defined_kinds else "necessary only (primitive)",
        )
        for kind in subtype_kinds
    }
)
classification_rows = sorted(
    {
        (
            label(subject),
            label(kind),
            "asserted" if (subject, RDF.type, kind) in asserted_observation_types
            else "inferred",
        )
        for subject in observation_subjects
        for kind in defined_kinds
        if (subject, RDF.type, kind) in reasoned
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
        "yes" if nanoclaw_mailbox_route(row.operation) else "no",
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


print(f"Load configuration: {manifest['loadConfig']}")
print("Always-loaded modules: " + ", ".join(always_loaded_ids))
print("Dynamic dependency loading: disabled")
print("Dependency preflight: satisfied")
print(f"Loaded skills: {', '.join(sorted(loaded_skills)) or '(none)'}")
if legacy_openclaw_operations:
    print(
        "Compatibility note: "
        f"{len(legacy_openclaw_operations)} selected operation(s) use OpenClaw-specific "
        "interfaces and are not automatically mapped to NanoClaw endpoints."
    )
print(f"Observation data: {data_path if data_path is not None else '(none)'}")
print(f"Resource kinds: {len(resource_rows)}")
print(f"Resource relationships: {len(relationship_rows)}")
print(f"Invocation subtype links: {len(invocation_rows)}")
print(f"Tool endpoint kinds: {len(tool_endpoint_rows)}")
print(f"Invocation routes: {len(route_rows)}")
print(f"Security-control links: {len(control_rows)}")
print(f"Subtype definitions: {len(definition_rows)} ({len(defined_kinds)} necessary+sufficient)")
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
if control_rows:
    print()
    print_table(("Surface kind", "Protected by control"), control_rows)
if definition_rows:
    print()
    print_table(("Subtype kind", "Definition strength"), definition_rows)
if data_path is not None:
    print()
    if classification_rows:
        print_table(("Observed resource", "Defined kind", "Classification"), classification_rows)
    else:
        print("No necessary-and-sufficient kind classifications were inferred from the observations.")
if effect_rows:
    print()
    print_table(("Graph", "Operation", "Effect", "Resource kind", "Broader kinds", "Shell-mediated", "Messaging-route", "NanoClaw-mailbox"), effect_rows)
