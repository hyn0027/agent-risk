from pathlib import Path
import hashlib
import json
import subprocess
import sys

from rdflib import Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from owlrl import DeductiveClosure, OWLRL_Semantics
from pyshacl import validate


ONTOLOGY_DIR = Path(__file__).resolve().parent
AR = Namespace("urn:agent-risk:")
SH = Namespace("http://www.w3.org/ns/shacl#")

# manifest.json intentionally contains only the default skill selection. Files,
# graph ids, hashes, dependencies, and source pins are owned by RDF metadata or
# derived from directory conventions.
manifest = json.loads((ONTOLOGY_DIR / "manifest.json").read_text())
unexpected_manifest_keys = set(manifest) - {"loadedSkills"}
if unexpected_manifest_keys:
    raise SystemExit(
        "manifest.json may contain only loadedSkills; unexpected keys: "
        + ", ".join(sorted(unexpected_manifest_keys))
    )
default_skills = manifest.get("loadedSkills", [])
if not isinstance(default_skills, list) or not all(
    isinstance(name, str) and name for name in default_skills
):
    raise SystemExit("manifest.json loadedSkills must be a list of non-empty strings")
if len(default_skills) != len(set(default_skills)):
    raise SystemExit("Duplicate skill in manifest.json loadedSkills")

# --universal-only selects all always-loaded graphs without skill graphs.
# --data FILE adds concrete observations for OWL-RL classification and SHACL.
# Explicit skill arguments override manifest.json loadedSkills.
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
loaded_skills = (
    set() if universal_only else set(skill_arguments) if skill_arguments else set(default_skills)
)


def parse_single_named_graph(path):
    parsed = Dataset()
    parsed.parse(str(path), format="trig")
    populated = [graph for graph in parsed.graphs() if len(graph)]
    if len(populated) != 1:
        raise SystemExit(
            f"{path.relative_to(ONTOLOGY_DIR)} must contain exactly one non-empty "
            f"named graph; found {len(populated)}."
        )
    graph = populated[0]
    if not isinstance(graph.identifier, URIRef):
        raise SystemExit(f"Named graph id must be an IRI in {path.relative_to(ONTOLOGY_DIR)}")
    return graph


def literal_values(graph, subject, predicate, description):
    values = list(graph.objects(subject, predicate))
    non_literals = [value for value in values if not isinstance(value, Literal)]
    if non_literals:
        raise SystemExit(f"{description} must use RDF literals")
    return [str(value) for value in values]


def one_literal(graph, subject, predicate, description):
    values = literal_values(graph, subject, predicate, description)
    if len(values) != 1 or not values[0]:
        raise SystemExit(f"{description} must have exactly one non-empty value")
    return values[0]


# Discover ontology modules by their own RDF metadata. This includes universal
# files and support modules such as skills/git-resources.trig.
ontology_modules = {}
candidate_graph_files = sorted((ONTOLOGY_DIR / "universal").glob("*.trig")) + sorted(
    (ONTOLOGY_DIR / "skills").glob("*.trig")
)
for path in candidate_graph_files:
    graph = parse_single_named_graph(path)
    module_resources = set(graph.subjects(RDF.type, AR.OntologyModule))
    if not module_resources:
        continue
    if len(module_resources) != 1:
        raise SystemExit(
            f"{path.relative_to(ONTOLOGY_DIR)} must contain one ar:OntologyModule"
        )
    module_resource = next(iter(module_resources))
    module_id = one_literal(
        graph, module_resource, AR.ontologyModuleId,
        f"ontology module id in {path.relative_to(ONTOLOGY_DIR)}",
    )
    if module_id in ontology_modules:
        raise SystemExit(f"Duplicate ontology module id: {module_id}")
    dependencies = sorted(set(literal_values(
        graph, module_resource, AR.requiresOntologyModule,
        f"dependencies for ontology module {module_id}",
    )))
    resources_only_values = list(graph.objects(module_resource, AR.resourcesOnly))
    resources_only = any(bool(value.toPython()) for value in resources_only_values)
    ontology_modules[module_id] = {
        "id": module_id,
        "file": str(path.relative_to(ONTOLOGY_DIR)),
        "graph": str(graph.identifier),
        "dependsOn": dependencies,
        "resourcesOnly": resources_only,
        "metadataResource": module_resource,
        "metadataGraph": graph,
    }

# Discover skill graphs and their source-integrity metadata.
modules = {}
for path in sorted((ONTOLOGY_DIR / "skills").glob("*.trig")):
    graph = parse_single_named_graph(path)
    skill_resources = set(graph.subjects(RDF.type, AR.Skill))
    if not skill_resources:
        continue
    if len(skill_resources) != 1:
        raise SystemExit(f"{path.name} must contain exactly one ar:Skill resource")
    skill_resource = next(iter(skill_resources))
    directory = one_literal(graph, skill_resource, AR.skillDirectory, f"skill directory in {path.name}")
    if directory in modules:
        raise SystemExit(f"Duplicate skill directory metadata: {directory}")
    modules[directory] = {
        "directory": directory,
        "file": str(path.relative_to(ONTOLOGY_DIR)),
        "graph": str(graph.identifier),
        "skillResource": skill_resource,
        "sourcePath": one_literal(graph, skill_resource, AR.sourcePath, f"source path in {path.name}"),
        "sourceSha256": one_literal(graph, skill_resource, AR.sourceSha256, f"source hash in {path.name}"),
        "dependsOn": sorted(set(literal_values(
            graph, skill_resource, AR.requiresOntologyModule,
            f"dependencies for skill {directory}",
        ))),
    }

unknown = loaded_skills - modules.keys()
if unknown:
    raise SystemExit(f"Unknown skills: {', '.join(sorted(unknown))}")

load_config_path = ONTOLOGY_DIR / "load-config.json"
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

# Source pins belong to ontology modules. They detect source drift but do not
# attest to a deployed process or live configuration.
for module_id in always_loaded_ids:
    entry = ontology_modules[module_id]
    graph = entry["metadataGraph"]
    subject = entry["metadataResource"]
    repository_paths = literal_values(
        graph, subject, AR.sourceRepositoryPath, f"source repository for {module_id}"
    )
    revisions = literal_values(
        graph, subject, AR.sourceRevision, f"source revision for {module_id}"
    )
    if bool(repository_paths) != bool(revisions) or len(repository_paths) > 1 or len(revisions) > 1:
        raise SystemExit(f"{module_id} must declare one sourceRepositoryPath/sourceRevision pair")
    if repository_paths:
        repository_path = Path(repository_paths[0])
        expected_revision = revisions[0]
        if not repository_path.exists():
            raise SystemExit(f"Ontology source checkout not found: {repository_path}")
        result = subprocess.run(
            ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
            check=False, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise SystemExit(f"Cannot read ontology source revision: {result.stderr.strip()}")
        actual_revision = result.stdout.strip()
        if actual_revision != expected_revision:
            raise SystemExit(
                f"{module_id} ontology is stale: source checkout is at "
                f"{actual_revision}, expected {expected_revision}."
            )

# Dependency declarations never load graphs. Every requirement must already be
# listed in load-config.json, and preflight finishes before the active dataset
# receives any named graph.
dependency_requirements = []
for module_id in always_loaded_ids:
    dependency_requirements.extend(
        (module_id, required_id)
        for required_id in ontology_modules[module_id]["dependsOn"]
    )
for skill_name in sorted(loaded_skills):
    dependency_requirements.extend(
        (skill_name, required_id)
        for required_id in modules[skill_name]["dependsOn"]
    )

unknown_required = {
    required_id for _, required_id in dependency_requirements
    if required_id not in ontology_modules
}
missing_dependencies = [
    (requester, required_id) for requester, required_id in dependency_requirements
    if required_id in ontology_modules and required_id not in always_loaded_ids
]
if unknown_required or missing_dependencies:
    for required_id in sorted(unknown_required):
        print(
            f"WARNING: required ontology dependency {required_id} has no discoverable "
            "ar:OntologyModule metadata",
            file=sys.stderr,
        )
    for requester, required_id in missing_dependencies:
        print(
            f"WARNING: {requester} requires ontology dependency {required_id}, but "
            "load-config.json does not introduce it in alwaysLoaded",
            file=sys.stderr,
        )
    raise SystemExit(
        "Dependency preflight failed; no ontology graphs were loaded. "
        "Add every required module to load-config.json alwaysLoaded."
    )

active = Dataset()  # Retains provenance as one named graph per source file.
combined = Graph()  # Union for cross-graph checks, hierarchy, and SHACL.
vocabulary = Graph().parse(str(ONTOLOGY_DIR / "universal/vocabulary.ttl"), format="turtle")
for triple in vocabulary:
    combined.add(triple)


def load_named_graph(entry):
    source_graph = parse_single_named_graph(ONTOLOGY_DIR / entry["file"])
    graph_id = URIRef(entry["graph"])
    if source_graph.identifier != graph_id:
        raise SystemExit(f"Named graph id changed in {entry['file']}")
    target_graph = active.graph(graph_id)
    for triple in source_graph:
        target_graph.add(triple)
        combined.add(triple)
    return target_graph


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
    if entry["resourcesOnly"] and any(graph.subjects(RDF.type, AR.InvocationSurfaceKind)):
        raise SystemExit(f"Resource-only graph contains an invocation kind: {entry['file']}")

for skill_name in sorted(loaded_skills):
    module = modules[skill_name]
    source = Path(module["sourcePath"])
    if not source.exists():
        raise SystemExit(f"Skill source not found: {source}")
    actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual_hash != module["sourceSha256"]:
        raise SystemExit(f"Ontology for {skill_name} is stale: source skill has changed.")
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

shapes = Graph().parse(str(ONTOLOGY_DIR / "universal/shapes.ttl"), format="turtle")
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
    mailbox_stages = {
        AR.NanoClawOutboundMailboxWrite,
        AR.NanoClawInboundMailboxWrite,
        AR.NanoClawAgentRunnerMailboxRead,
    }
    return any(
        channel in mailbox_stages
        or any(route_reaches(channel, stage) for stage in mailbox_stages)
        for channel in combined.objects(operation, AR.invokedThroughKind)
    )


nanoclaw_adapted_operations = sorted(
    set(combined.subjects(AR.adaptationStatus, AR.InferredForNanoClaw)), key=str
)
adaptation_mappings = set(combined.subjects(RDF.type, AR.AdaptationMapping))
adaptation_disposition_links = set(
    combined.subject_objects(AR.adaptationDisposition)
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


print("Manifest defaults: " + (", ".join(default_skills) or "(none)"))
print("Load configuration: load-config.json")
print("Graph/catalog metadata: discovered from RDF and directory conventions")
print("Always-loaded modules: " + ", ".join(always_loaded_ids))
print("Dynamic dependency loading: disabled")
print("Skill dependency source: ar:requiresOntologyModule metadata in each skill graph")
print("Dependency preflight: satisfied")
print(f"Loaded skills: {', '.join(sorted(loaded_skills)) or '(none)'}")
if nanoclaw_adapted_operations:
    print(
        "Adaptation note: "
        f"{len(nanoclaw_adapted_operations)} selected operation(s) are conservative "
        "NanoClaw translations rather than claims made by their source skills."
    )
print(f"Observation data: {data_path if data_path is not None else '(none)'}")
print(f"Resource kinds: {len(resource_rows)}")
print(f"Resource relationships: {len(relationship_rows)}")
print(f"Invocation subtype links: {len(invocation_rows)}")
print(f"Tool endpoint kinds: {len(tool_endpoint_rows)}")
print(f"Invocation routes: {len(route_rows)}")
print(f"Security-control links: {len(control_rows)}")
print(f"Skill adaptation mappings: {len(adaptation_mappings)}")
print(f"Adaptation disposition links: {len(adaptation_disposition_links)}")
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
