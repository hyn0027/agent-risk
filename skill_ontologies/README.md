# Endpoint and resource ontologies — prototype

Each per-skill `.trig` file contains one named graph derived from a `top_skills/*/SKILL.md`. Three universal named graphs load independently of skills. `local-filesystem.trig` and `freeform-internet.trig` are **resource-only** graphs. `shell-execution.trig` describes a shell invocation hierarchy and process-related resources, but contains no operations or effects. `manifest.json` selects these graphs for every load; **always loaded is a loading policy, not an ontological category**.

All graphs use `ar: <urn:agent-risk:>`. These are local identifiers, not dereferenceable Web URLs. For a published ontology, use an owned, persistent HTTPS namespace. `vocabulary.ttl` defines the common terms, and `shapes.ttl` validates skill operations. The source skills are not invoked by these files.

## Resource relationships

Resource kinds are currently RDF *individuals* typed `ar:WorldSurfaceKind`, rather than OWL classes. The following relationships can overlap and form multiple hierarchies:

- `ar:specializesKind` means **is-a**: `ar:LocalAudioFile ar:specializesKind ar:LocalFile`. A kind may have multiple broader kinds. The loader follows all parents for the "Broader kinds" column.
- `ar:containsKind` means **part/containment**: `ar:LocalDirectory ar:containsKind ar:LocalFile`. Containment does not imply subtype.
- `ar:mayBeStoredAsKind` is a weaker physical-representation link: logical OpenClaw configuration may be stored as a local file. It does not assert that every configuration action directly edits a file.

Because kinds are individuals, `ar:specializesKind` is a project-specific property, **not** `rdfs:subClassOf` or OWL subclass reasoning. The loader uses graph traversal to compute broader kinds; it rejects cycles in the is-a relation. A future migration to OWL classes would be a schema change, not just a spelling change.

Per-skill kinds link directly to general kinds. For example, `ar:LocalSecretFile` is-a `ar:LocalFile`, and a Discord media send directly affects `ar:LocalFile` as a source. There is no module-level `usesSharedKind` citation: the resource relationship itself is the link across named graphs.

Named provider endpoints (GitHub REST, Discord, Slack, Imgflip API, etc.) remain distinct from the freeform-internet taxonomy. Only unspecified websites and ordinary URL downloads are linked to general internet kinds. This classifies the described resource/access context; it does not establish actual reachability or authentication.

## Shell invocation hierarchy

`ar:ShellExecution` is an `ar:InvocationSurfaceKind`, not a world resource or a generic operation. `ar:ShellCommandExecution` and `ar:ShellScriptExecution` are narrower invocation kinds under it. A command launched through a shell need not be a *shell-language script*: the Node and Python CLIs in these skills are linked to `ShellCommandExecution`, not `ShellScriptExecution`. The universal graph also models `ShellProcess`, output, environment, exit status, script file, and working-directory resource kinds.

`ar:specializesInvocationKind` links concrete call channels to the general mechanism. For example, the GitHub skill's `CurlCLI` and `GitCLI` are kinds of shell-command execution, while `GitHubREST` remains a separate remote endpoint. An operation is **shell-mediated** if one of its `ar:invokedThroughKind` channels reaches `ShellExecution` through this hierarchy. This is not a claim that the GitHub API, its resources, or every GitHub-skill orchestration step is a subtype of a shell script. In `gh-issues`, eight described operations are shell-mediated; the two subagent-spawn operations and Telegram notification are not.

## Loading and validation

Run `python loader.py --universal-only` to inspect the three always-loaded graphs without skill operations. The old `--resources-only` and `--baseline-only` spellings remain aliases. Run `python loader.py discord gh-issues` to add those two skill graphs; no arguments select those two by default. The loader requires `rdflib` and `pyshacl`.

The loader preserves one named graph per file, verifies each selected skill's `SKILL.md` SHA-256 against `manifest.json`, validates the union against `shapes.ttl`, checks resource and invocation relationships, and prints resource kinds, invocation hierarchies, and skill-stated potential effects with a shell-mediated flag. Loading policy and source hashes are metadata outside the ontology. Loading a graph does **not** prove runtime permissions. No harness hook, graph unloading mechanism, or verified harness tool inventory is installed in this prototype.

On the combined graph, a SPARQL property path can query all broader resource kinds:

```sparql
PREFIX ar: <urn:agent-risk:>
SELECT ?narrow ?broader WHERE {
  ?narrow ar:specializesKind+ ?broader .
}
```

Do not combine `ar:specializesKind` and `ar:containsKind` in one path and interpret the result as a subtype. A file being inside a directory is not a kind of directory.

For shell mediation on the combined graph:

```sparql
PREFIX ar: <urn:agent-risk:>
SELECT DISTINCT ?operation WHERE {
  ?operation ar:invokedThroughKind/ar:specializesInvocationKind* ar:ShellExecution .
}
```

## Limits

This is a manually reviewed first-pass model for the ten current skill files, not an exhaustive code audit. The TaskFlow example has no identified local-file or freeform-internet resource and was left unchanged. Generic shell and delegated workers can have open-ended effects; the universal shell graph intentionally does not enumerate every possible command or downstream mutation. Skill operations describe *potential* effects, not observed changes; joint effects such as reading a credential and later transmitting that specific value still require call arguments, dataflow, and state-transition facts. The universal graphs do not define actual sandbox roots, destinations, accounts, network rights, or shell privileges. Add those from a separately verified harness/runtime inventory.
