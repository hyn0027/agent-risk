# Endpoint and resource ontologies — prototype

`skills/` contains graphs derived from individual `top_skills/*/SKILL.md` files plus domain-specific support graphs shared by related skills. `skills/git-resources.trig`, for example, is a declared dependency of the two Git-related skills rather than a universal environment model. Cross-domain graphs and schemas live in `universal/`. `load-config.json` currently introduces six modules before any skill is selected: tool endpoints, local filesystem, freeform internet, shell execution, Git resources, and OpenClaw messaging. `local-filesystem.trig` and `freeform-internet.trig` are **resource-only** graphs. These support graphs contain no operations or effects. `manifest.json` catalogs graphs and skill dependencies; `load-config.json` contains the static loading policy. **Folder placement and loading policy are separate from ontological category.**

All graphs use `ar: <urn:agent-risk:>`. These are local identifiers, not dereferenceable Web URLs. For a published ontology, use an owned, persistent HTTPS namespace. `universal/vocabulary.ttl` defines the common terms, and `universal/shapes.ttl` validates skill operations. The source skills are not invoked by these files.

```text
skill_ontologies/
  manifest.json          graph catalog and skill dependencies
  load-config.json       complete set of preloaded ontology modules
  loader.py              loads and validates a selected graph union
  README.md
  examples/              small observation graphs for inference/validation
  universal/             reusable vocabulary, shapes, and shared graphs
  skills/                skill graphs and domain-specific support graphs
```

## Resource relationships

Resource kinds remain RDF *individuals* typed `ar:WorldSurfaceKind` for the effect model, and are also usable as RDFS/OWL classes through OWL 2 punning. The following relationships can overlap and form multiple hierarchies:

- `ar:specializesKind` means **is-a**: `ar:LocalAudioFile ar:specializesKind ar:LocalFile`. A kind may have multiple broader kinds. The loader follows all parents for the "Broader kinds" column.
- `ar:containsKind` means **part/containment**: `ar:LocalDirectory ar:containsKind ar:LocalFile`. Containment does not imply subtype.
- `ar:mayBeStoredAsKind` is a weaker physical-representation link: logical OpenClaw configuration may be stored as a local file. It does not assert that every configuration action directly edits a file.

`ar:specializesKind` remains the project-facing property. In its separate reasoning graph, the loader projects every such edge to an explicit `rdfs:subClassOf` axiom and declares both endpoints as OWL classes. Thus every existing subtype edge supplies an OWL **necessary** superclass condition while preserving the current effect-query interface. The loader still uses direct graph traversal for its readable hierarchy and rejects cycles. This avoids trying to make a custom property a subproperty of the reserved `rdfs:subClassOf` predicate, which would not be clean OWL-DL modeling.

Per-skill kinds link directly to general kinds. For example, `ar:LocalSecretFile` is-a `ar:LocalFile`, and a Discord media send directly affects `ar:LocalFile` as a source. There is no module-level `usesSharedKind` citation: the resource relationship itself is the link across named graphs.

Named provider endpoints (GitHub REST, Discord, Slack, Imgflip API, etc.) remain distinct from the freeform-internet taxonomy. Only unspecified websites and ordinary URL downloads are linked to general internet kinds. This classifies the described resource/access context; it does not establish actual reachability or authentication.

## Tool-endpoint interface and hierarchy

`ar:ToolEndpointKind` is an RDF class under `ar:InvocationSurfaceKind`. `ar:ToolEndpoint` is the common parent **kind** (an individual of that class); concrete callable kinds use `ar:specializesInvocationKind` to reach it. Like resource specialization, the loader projects this relation into the OWL reasoning graph as `rdfs:subClassOf`.

`ShellExecution` and the agent-facing `OpenClawMessageTool` are separate children of `ToolEndpoint`. The shell-invoked `OpenClawMessageCLI` is a tool endpoint through `ShellCommandExecution`; it remains distinct from the agent-facing tool. `MCPToolEndpoint` is another child, representing an *individual callable MCP tool* discovered with `tools/list` and invoked with `tools/call`, not its server, transport, resources, or prompts. This branch intentionally has no concrete server/tools or effect claims. [MCP's tool specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) defines those calls and notes that the available set depends on current capability and authorization.

Existing directly callable `SubagentSpawnTool`, `ProcessControlTool`, `ConnectChannelTool`, and `SkillWorkshopTool` also cite the parent. Provider APIs and channel-plugin adapters remain invocation/mediation surfaces rather than automatically becoming agent-facing tool endpoints. The loader prints declared endpoint kinds and narrower inherited kinds; it checks that every explicitly typed `ToolEndpointKind` has a path to the parent. The common operation-to-endpoint relation remains `ar:invokedThroughKind`, and mediation beyond a tool remains `ar:routesToKind`. This is a taxonomy/interface for analysis, not an inventory of tools actually exposed by a harness.

## Shell invocation hierarchy

`ar:ShellExecution` is a tool-endpoint kind, not a world resource or a generic operation. `ar:ShellCommandExecution` and `ar:ShellScriptExecution` are narrower invocation kinds under it. A command launched through a shell need not be a *shell-language script*: the Node and Python CLIs in these skills are linked to `ShellCommandExecution`, not `ShellScriptExecution`. The universal graph also models `ShellProcess`, output, environment, exit status, script file, and working-directory resource kinds.

`ar:specializesInvocationKind` links concrete call channels to the general mechanism. For example, the GitHub skill's `CurlCLI` and `GitCLI` are kinds of shell-command execution, while `GitHubREST` remains a separate remote endpoint. An operation is **shell-mediated** if one of its `ar:invokedThroughKind` channels reaches `ShellExecution` through this hierarchy. This is not a claim that the GitHub API, its resources, or every GitHub-skill orchestration step is a subtype of a shell script. In `gh-issues`, eight described operations are shell-mediated; the two subagent-spawn operations and Telegram notification are not.

## OpenClaw messaging mediation

Official OpenClaw documentation distinguishes the core-owned agent-facing `message` tool from the shell-invoked `openclaw message` CLI. The tool routes through a channel-plugin action adapter; the CLI resolves a channel plugin. Neither tool/CLI is a subtype of the plugin or adapter: `ar:routesToKind` records the mediation route, while `ar:specializesInvocationKind` records *is-a*. The CLI is a subtype of `ShellCommandExecution`. `DiscordAdapter` and `TelegramAdapter` are narrower `OpenClawChannelAdapter` invocation kinds. `SlackMessageChannel` is narrower only than the abstract `MessagingChannelInvocation`: the TaskFlow example says to post to Slack but gives no exact send API, so claiming it uses OpenClaw's shared message tool or plugin adapter would overstate the source.

The `discord`, `gh-issues`, `configure-channel`, `coding-agent`, and `taskflow-inbox-triage` entries retain explicit `openclaw-messaging` dependencies even though `load-config.json` currently introduces that module for every run. This redundancy is intentional: it records what each skill needs and lets the loader detect a future configuration mismatch. Dependency declarations never load graphs. Before loading any named graph, the loader verifies that every selected skill dependency already appears in `alwaysLoaded`; if not, it prints a warning and aborts. `configure-channel` and `coding-agent` use `OpenClawMessageCLI`, while Discord and GitHub notifications explicitly use the agent-facing `message` tool.

The mediator graph contains no operations or effects. Its routes describe possible type-level pathways, not deployed channel accounts, available actions, permissions, delivery, or recipient attention. Action discovery and permission checks are context-sensitive, so runtime authority must be verified independently. See [OpenClaw plugin architecture](https://docs.openclaw.ai/plugins/architecture), [channel plugin guide](https://docs.openclaw.ai/plugins/sdk-channel-plugins), and [`openclaw message` CLI](https://docs.openclaw.ai/cli/message).

## Qualified subtype definitions

Every `specializesKind` or `specializesInvocationKind` assertion is a **necessary-only** definition: an instance of the narrower kind must also belong to the broader kind. A kind becomes **necessary-and-sufficient** only when it has an `owl:equivalentClass` class expression. The loader audits every subtype and labels it `necessary only (primitive)` or `necessary+sufficient (OWL + SHACL)`. It also requires every equivalent-class kind to have a SHACL shape targeting that kind.

`skills/git-resources.trig` demonstrates the pattern without making the false claim that every Git repository is simply a directory containing `.git`:

- `GitMetadataEntryCandidate` is exactly a filesystem entry whose name is `.git`.
- `ConventionalGitWorkingTreeCandidate` is exactly a local directory containing such an entry.
- `ConventionalGitWorkingTree` additionally requires an explicit `gitRepositoryValidated true` observation.
- `LocalGitRepository` remains a primitive broader kind because bare repositories, linked worktrees, and externally selected Git directories do not all satisfy the `.git`-entry condition.

OWL-RL performs positive, open-world classification. SHACL separately checks necessary evidence for asserted or inferred members under the supplied observation graph. This means missing facts do not prove non-membership, while a resource explicitly claimed to be a conventional working tree fails validation if its `.git` evidence is absent.

## Loading and validation

Run `python loader.py --universal-only` to inspect the six modules named by `load-config.json` without skill operations. The old `--resources-only` and `--baseline-only` spellings remain aliases. Run `python loader.py discord gh-issues` to add those two skill graphs; no arguments select those two by default. `coding-agent` and `gh-issues` require `git-resources`, but do not load it dynamically—the current configuration introduces it beforehand. The loader requires `rdflib`, `owlrl`, and `pyshacl`.

To classify concrete observations and validate the inferred types:

```bash
python loader.py coding-agent --data examples/git-working-tree.ttl
```

The example infers `GitMetadataEntryCandidate`, `ConventionalGitWorkingTreeCandidate`, and `ConventionalGitWorkingTree`. Running the same command with `examples/invalid-git-working-tree.ttl` intentionally fails SHACL validation.

The loader preserves one named graph per file, verifies each selected skill's `SKILL.md` SHA-256 against `manifest.json`, performs dependency preflight against `load-config.json`, validates the graph union against `shapes.ttl`, and performs optional OWL-RL classification. It never dynamically loads a dependency. Loading a graph does **not** prove runtime permissions. No harness hook, graph unloading mechanism, or verified harness tool inventory is installed in this prototype.

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

To list callable endpoint kinds, including future subclasses added by other graphs:

```sparql
PREFIX ar: <urn:agent-risk:>
SELECT DISTINCT ?kind WHERE {
  ?kind ar:specializesInvocationKind* ar:ToolEndpoint .
}
```

## Limits

This is a manually reviewed first-pass model for the ten current skill files, not an exhaustive code audit. Most current subtype kinds remain primitive because the available skills do not provide reliable necessary-and-sufficient recognition criteria; the loader reports this explicitly instead of manufacturing definitions. OWL-RL is not a complete OWL 2 DL reasoner, and SHACL validation only evaluates facts present in the loaded data. The TaskFlow example has no identified local-file or freeform-internet resource; its Slack messaging route is illustrative. Generic shell and delegated workers can have open-ended effects. Skill operations describe *potential* effects, not observed changes; joint effects still require call arguments, dataflow, and state-transition facts. The universal graphs do not define actual sandbox roots, destinations, accounts, network rights, or shell privileges. Add those from a separately verified harness/runtime inventory.
