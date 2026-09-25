# NanoClaw skill-surface ontology prototype

## Start here

This project turns natural-language agent skills into a queryable, composable model of:

1. **what an environment contains** — files, repositories, mailboxes, messages, services, credentials, processes, and other resource kinds;
2. **how actions enter that environment** — shell, MCP tools, messaging tools, provider file/web tools, NanoClaw CLI paths, and other invocation kinds;
3. **what a skill says can be done** — named operations with prerequisites and provenance; and
4. **what those operations may affect** — typed potential effects such as read, create, update, delete, transmit, execute, configure, or notify.
5. **which outbound Internet requests they may eventually cause** — including requests made by a shell command, a delegated worker, or a host channel adapter after a local tool call.

The central analysis path is:

```text
selected skill
  → operation
  → invocation endpoint/channel
  → possible mediation route
  → potential effect
  → affected resource kind
  → broader resource kinds

selected skill → operation → potential Internet call → public endpoint kind
                                  ├─ call initiator and stage
                                  ├─ invocation path
                                  ├─ endpoint URL/template, if established
                                  └─ conditions and evidence
```

For example, the Discord skill does not merely say “send a message.” It records that the operation is invoked through `NanoClawSendMessageTool`, may traverse the outbound mailbox and channel adapter, may create a `DiscordMessage`, may transmit to a `DiscordChannel`, and requires a registered adapter, a projected destination, and platform permission.

The intended use is conservative security analysis: assemble the environment ontology with one or more skill ontologies, then ask which resources could possibly be reached or changed and through which interfaces. Results are **over-approximations of modeled possibility**, not proof that an action is enabled, authorized, successful, or observed at runtime.

### What this project is not

This is not:

- an ontology of the agent's beliefs, prompts, goals, or internal reasoning;
- a planner or workflow engine that predicts action order;
- a live inventory of deployed tools, mounts, credentials, users, or permissions;
- a policy-enforcement mechanism;
- proof that every effect in a skill will occur; or
- a claim that an original skill executes unchanged under NanoClaw.

The model describes **potential endpoints and world-facing consequences**. Runtime reachability still depends on concrete configuration, arguments, identity, authority, state, and policy decisions.

### Thirty-second orientation

```text
universal/*.trig                     always-available type/model modules
skills/<skill>.trig                  operations and potential effects for one skill
skills/git-resources.trig            shared support ontology, not a skill
universal/vocabulary.ttl             schema vocabulary
universal/shapes.ttl                 SHACL integrity constraints
manifest.json                        one list of selected ontology IDs
loader.py                            assembly, validation, and reports
examples/*.ttl                       standalone concrete observation fixtures
```

The loader never fetches or dynamically introduces a dependency. A dependency named by any selected ontology must already appear in `manifest.json`; otherwise loading aborts before an active dataset is assembled.

### Sources and evidence boundary

This directory combines two kinds of source-derived model:

- `universal/` describes the generic resource vocabulary and the NanoClaw harness architecture that is present independently of a selected skill.
- `skills/` describes interfaces and potential effects asserted by individual `top_skills/*/SKILL.md` files, plus support graphs shared only by those skills.

The NanoClaw model was checked against local checkout commit `7902716b5b930215dbee4f56b8fb5b938d40468d`. Repository code is treated as the primary source; the [shared architecture discussion](https://chatgpt.com/s/cx_6ab168a066788191a0767199e971bbd4) was useful orientation but is not the authority when it differs from code. The model is not a statement about the live configuration of any NanoClaw installation.

All graphs use `ar: <urn:agent-risk:>`. These are local identifiers, not dereferenceable Web URLs. A published ontology should use an owned persistent HTTPS namespace.

```text
skill_ontologies/
  manifest.json          one list of selected ontology IDs
  loader.py              dependency checks, validation, reports
  examples/              sample observation graphs for external RDF tools
  universal/
    vocabulary.ttl
    shapes.ttl
    tool-endpoints.trig
    local-filesystem.trig
    freeform-internet.trig
    shell-execution.trig
    nanoclaw-core.trig
    nanoclaw-messaging.trig
    nanoclaw-control.trig
    nanoclaw-runtime.trig
    nanoclaw-network.trig
  skills/
    git-resources.trig
    ...one graph per skill...
```

### Non-negotiable project invariants

An agent changing this project should preserve these rules:

- `manifest.json` is one JSON array of unique ontology IDs.
- Every `.trig` file contains exactly one non-empty named graph with an IRI identifier.
- Every module graph contains exactly one `ar:OntologyModule` with a unique `ar:ontologyModuleId`.
- Every skill graph contains exactly one `ar:Skill` with a unique `ar:skillDirectory`, one source path, and one source hash.
- Dependency metadata validates a static load policy; it never triggers dynamic loading.
- Always-loaded graphs contain no operations, effects, or operation/effect links.
- A module marked `ar:resourcesOnly true` contains no invocation kinds.
- Every declared `ar:ToolEndpointKind` is an invocation kind and ultimately specializes `ar:ToolEndpoint`.
- Resource and invocation specialization graphs are acyclic.
- Every kind with an `owl:equivalentClass` definition has a SHACL target shape.
- Skill-source hashes and pinned repository revisions are drift detectors, not security attestations.

## Conceptual model

The ontology deliberately keeps several concepts separate because collapsing them creates misleading security conclusions.

| Concept | RDF type | Meaning | Example |
|---|---|---|---|
| Skill | `ar:Skill` | Provenance-bearing model derived from one `SKILL.md` | `ar:skill_discord` |
| Ontology module | `ar:OntologyModule` | Statically discoverable graph and its dependencies | `ar:NanoClawMessagingModule` |
| World surface kind | `ar:WorldSurfaceKind` | Kind of state, resource, component, recipient, or external object | `ar:LocalFile`, `ar:DiscordMessage` |
| Invocation surface kind | `ar:InvocationSurfaceKind` | Kind of path through which behavior is invoked or mediated | `ar:ShellExecution`, `ar:NanoClawOutboundMailboxWrite` |
| Tool endpoint kind | `ar:ToolEndpointKind` | Invocation kind callable by, or on behalf of, an agent | `ar:MCPToolEndpoint`, `ar:NanoClawSendMessageTool` |
| Operation | `ar:Operation` | Action described by a selected skill | `ar:op_discord_send` |
| Potential effect | `ar:PotentialEffect` | Possible typed consequence of an operation | create a message; transmit to a channel |
| Potential Internet call | `ar:PotentialInternetCall` | Possible outbound request, distinguished from the operation and its world effect | a later host Discord API request |
| Requirement | `ar:Requirement` | Condition needed for the modeled action/effect | destination exists; permission is granted |
| Security control kind | `ar:SecurityControlKind` | Kind of configuration or enforcement point | destination ACL; mount allowlist |
| Adaptation mapping | `ar:AdaptationMapping` | Auditable source-skill-to-NanoClaw translation | generic message send → NanoClaw send tool |

### Operations and effects

A skill connects operations to interfaces, resources, conditions, evidence, and effects:

```turtle
ar:op_discord_send a ar:Operation ;
  ar:invokedThroughKind ar:NanoClawSendMessageTool ;
  ar:targetsKind ar:DiscordChannel ;
  ar:requires ar:cond_discord_adapter_registered,
    ar:cond_discord_target_permission ;
  ar:sourceStatus ar:SkillText ;
  ar:adaptationStatus ar:InferredForNanoClaw ;
  ar:hasPotentialEffect [
    a ar:PotentialEffect ;
    ar:effectType ar:Create ;
    ar:affectsKind ar:DiscordMessage
  ] .
```

Important interpretation rules:

- `targetsKind` says what an operation is directed at; it is not itself an effect.
- `hasPotentialEffect` is a **may-effect**. It does not assert success or occurrence.
- `requires` records a condition but does not evaluate it.
- `sourceStatus` describes evidence from the source skill or bundled code.
- `adaptationStatus` separately marks environment-specific translation.
- `invokedThroughKind` identifies an entry point; `routesToKind` describes possible mediation after that point.
- A read effect is still security-relevant even when it does not mutate world state.

### Internet-call qualification

An `ar:PotentialInternetCall` is a **may-call** to an endpoint kind explicitly typed `ar:PublicInternetEndpointKind` and specialized from `ar:PublicInternetEndpoint`. The call names its initiating component (`callInitiatorKind`), invocation path (`callViaKind`), stage (`callStage`), destination kind (`callEndpointKind`), source evidence, and—only when supported—an `callEndpointPattern` URL or protocol template. It inherits the operation's `requires` conditions and can add `callConditionalOn` conditions. SHACL and the loader reject incomplete calls and destination kinds outside this public-endpoint hierarchy.

The boundary is public Internet egress, including a direct request or one mediated by OneCLI. A local shell process, stdio MCP call, Unix socket, mailbox write, container-to-host handoff, and private-network hop do **not** qualify by themselves. Nor does merely targeting a remote-looking resource or using a tool named `web` prove a concrete public endpoint. `routesToKind` is a possible architecture path; `mayInitiateInternetCall` is a separate, explicit operation-level claim.

For example, `op_discord_send` invokes a local MCP tool and writes the outbound mailbox; the modeled Internet call is the *later host adapter delivery* to `DiscordAPIEndpoint`. `op_meme_local_render` may fetch a template image only on a cache miss. `op_sherpa_download` has separate possible runtime-archive and voice-model calls. `op_prepare_worktree`'s `git fetch` qualifies only if the verified canonical remote is public-Internet-addressable. These call objects are categories of possible requests, not a packet count; retries, redirects, pagination, and downstream services may produce more calls.

The absence of a call object is **not proof of no egress**. In particular, arbitrary shell scripts, `op run` child commands, a delegated coding worker, optional browser/MCP servers, and provider web tools can perform additional calls that cannot be enumerated from these skill files. A direct 1Password CLI call is modeled only conditionally for cloud-backed modes; local desktop IPC is not itself Internet egress. Generic destinations such as `NotificationDestination` and `ConfiguredNanoClawChannel` are not automatically classified as public endpoints because they may resolve to local or private routes.

### Four relationships that must not be conflated

```text
specializesKind             subtype:       DiscordMessage is a MessagingMessage
containsKind                composition:   DiscordChannel may contain DiscordMessage
routesToKind                mediation:     SendMessageTool may route to mailbox write
protectedByKind             control link:  host delivery is subject to destination ACL
```

Only specialization means “is a.” Containment does not imply subtype. A route is a possible architecture path, not runtime reachability. A protection edge says a control is relevant, not that it is enabled or permits the action.

### Why both RDF/OWL and SHACL are used

- RDF/TriG preserves named-graph provenance and supports cross-skill composition.
- OWL class definitions support positive subtype and necessary-and-sufficient classification in an OWL reasoner.
- SHACL enforces structural expectations and closed-world validation requirements.
- Python performs checks that are operational or awkward to encode declaratively, including source hashes, Git revision pins, dependency policy, cycle detection, and report generation.

OWL uses open-world semantics: an absent fact is unknown, not false. SHACL is used where the project intentionally needs closed-world validation. The loader checks the OWL definitions and SHACL shapes but does not run an OWL reasoner over instance observations.

## What gets loaded

The active model is assembled as follows:

```text
vocabulary.ttl
  + shared ontology graphs listed in manifest.json
  + skill graphs listed in manifest.json
  = active named-graph dataset + combined validation graph
```

`manifest.json` lists selected ontology IDs without separate module and skill fields. RDF resources inside each graph own its identity, dependencies, and provenance. The loader discovers the corresponding graph files from that metadata.

The current module inventory is:

| Module ID | File | Responsibility |
|---|---|---|
| `tool-endpoints` | `universal/tool-endpoints.trig` | Common callable endpoint parent, messaging tools, and MCP tool/transport distinctions |
| `local-filesystem` | `universal/local-filesystem.trig` | Files, directories, metadata, symlinks, and structural entry observations |
| `freeform-internet` | `universal/freeform-internet.trig` | Uncontrolled Internet hosts, endpoints, services, web resources, logs, and accounts |
| `shell-execution` | `universal/shell-execution.trig` | Shell/command/script invocation and process-related resources |
| `nanoclaw-core` | `universal/nanoclaw-core.trig` | Host, database, agent groups, sessions, containers, runners, and provider runtime |
| `nanoclaw-messaging` | `universal/nanoclaw-messaging.trig` | Channels, destinations, inbound/outbound mailboxes, delivery, and built-in messaging tools |
| `nanoclaw-control` | `universal/nanoclaw-control.trig` | `ncl` management paths, tasks, guards, approval, roles, and destination controls |
| `nanoclaw-runtime` | `universal/nanoclaw-runtime.trig` | Container/host filesystems, mounts, shell/file tools, isolation, and resource limits |
| `nanoclaw-network` | `universal/nanoclaw-network.trig` | OneCLI, direct/proxied egress, local/remote MCP, and lockdown controls |
| `git-resources` | `skills/git-resources.trig` | Reusable Git resource kinds and qualified working-tree definitions |

`git-resources` lives under `skills/` because it is skill-oriented support vocabulary, but it is still an ontology module rather than an `ar:Skill`. It is selected because `gh-issues` requires it; `coding-agent` also requires it. Static dependency validation would reject either skill if this ontology were absent. Folder placement and loading policy are separate concerns.

The current skill inventory is:

| Skill directory | Graph file | Main modeled capability | Declared module dependencies |
|---|---|---|---|
| `1password-1.0.0` | `skills/1password.trig` | CLI/browser-oriented credential access and injection | `nanoclaw-runtime`, `nanoclaw-network` |
| `coding-agent` | `skills/coding-agent.trig` | Worktrees, coding workers, process control, PRs, notification | `git-resources`, `nanoclaw-runtime`, `nanoclaw-messaging`, `nanoclaw-network` |
| `configure-channel` | `skills/configure-channel.trig` | Channel inspection/configuration and delivery tests | `nanoclaw-messaging`, `nanoclaw-control` |
| `diagram-maker-1.0.0` | `skills/diagram-maker.trig` | Read/write/verify diagram artifacts | `nanoclaw-runtime` |
| `discord` | `skills/discord.trig` | Send text/files, edit, and react through NanoClaw messaging | `nanoclaw-messaging` |
| `gh-issues` | `skills/gh-issues.trig` | GitHub issue/PR orchestration, Git, delegation, notification | `git-resources`, `nanoclaw-core`, `nanoclaw-runtime`, `nanoclaw-network`, `nanoclaw-messaging` |
| `meme-maker-1.0.0` | `skills/meme-maker.trig` | Local/hosted meme rendering and catalog refresh | `nanoclaw-runtime`, `nanoclaw-network` |
| `sherpa-onnx-tts-1.0.0` | `skills/sherpa-onnx-tts.trig` | Download/configure/run local TTS and produce audio | `nanoclaw-core`, `nanoclaw-runtime`, `nanoclaw-network`, `nanoclaw-control` |
| `skill-creator-1.0.0` | `skills/skill-creator.trig` | Inspect, stage, edit, and validate skill files | `nanoclaw-runtime` |
| `taskflow-inbox-triage` | `skills/taskflow-inbox-triage.trig` | Approximate durable task coordination, triage, and notification | `nanoclaw-core`, `nanoclaw-messaging`, `nanoclaw-control` |

## Static loading policy

The manifest currently lists ten shared ontologies and two skill ontologies. Five shared ontologies describe NanoClaw itself: core, messaging/mailboxes, management controls, container/filesystem runtime, and network/OneCLI paths. Generic tool, filesystem, internet, and shell graphs are also selected. Git resource definitions live under `skills/` even though they are selected on every run; folder placement and load policy are separate concerns.

Dependencies never load dynamically. Every ontology module owns its metadata in RDF:

```turtle
ar:NanoClawMessagingModule a ar:OntologyModule ;
  ar:ontologyModuleId "nanoclaw-messaging" ;
  ar:requiresOntologyModule "tool-endpoints", "local-filesystem", "nanoclaw-core" .
```

Each skill likewise owns its directory name, source provenance, and dependencies on its `ar:Skill` resource:

```turtle
ar:skill_coding_agent a ar:Skill ;
  ar:skillDirectory "coding-agent" ;
  ar:sourcePath "/path/to/top_skills/coding-agent/SKILL.md" ;
  ar:sourceSha256 "..." ;
  ar:requiresOntologyModule "git-resources", "nanoclaw-runtime", "nanoclaw-messaging" ;
  ...
```

The loader discovers module graphs in `universal/*.trig` and `skills/*.trig`, and discovers skill graphs in `skills/*.trig`. Each file contains one named graph. Fixed infrastructure files remain at `universal/vocabulary.ttl` and `universal/shapes.ttl`; this avoids duplicating their paths in a catalog.

During dependency preflight, the loader parses graph metadata, checks that selected ontology IDs exist, verifies the NanoClaw source revision, and requires every dependency to already be selected in `manifest.json`. It does not create the active dataset until this dependency preflight succeeds. Before loading each selected skill graph, it separately verifies that skill's source hash. A missing or unknown dependency produces a warning and aborts; dependencies are never introduced automatically.

`manifest.json` is the only configuration file and is a literal JSON array. The loader resolves each ID against RDF metadata; no type label is needed in the list. To change the loaded ontologies, edit this list and run `python loader.py`. The loader accepts no command-line arguments.

```json
[
  "tool-endpoints",
  "local-filesystem",
  "freeform-internet",
  "shell-execution",
  "nanoclaw-core",
  "nanoclaw-messaging",
  "nanoclaw-control",
  "nanoclaw-runtime",
  "nanoclaw-network",
  "git-resources",
  "discord",
  "gh-issues"
]
```

Every always-loaded graph is checked to contain no `ar:Operation`, `ar:PotentialEffect`, `ar:declaresOperation`, or `ar:hasPotentialEffect`. `local-filesystem.trig` and `freeform-internet.trig` are additionally marked `resourcesOnly` and cannot declare invocation kinds.

### Loader sequence

For an agent modifying this project, the order matters:

1. Read `manifest.json` as a JSON array of unique ontology IDs.
2. Discover every `*.trig` file under `universal/` and `skills/`. Each must contain exactly one non-empty named graph.
3. In one pass, identify each graph as a module or skill from its RDF metadata and reject duplicate IDs.
4. Resolve the manifest IDs and check every selected graph's declared dependencies. Missing dependencies warn and abort before any active graph is loaded.
5. Load the vocabulary and selected graphs in manifest order, checking module source pins and skill-source hashes as they are added.
6. Check typed relationship endpoints, subtype cycles, endpoint parentage, shared-graph restrictions, and equivalent-class shape coverage.
7. Run SHACL over the assembled graph.
8. Print only loaded skill operations, their potential effect/resource rows, and their modeled potential Internet calls.

This sequence prevents a dependency declaration from silently widening the environment model. It also separates asserted named-graph data from the temporary union graph used for validation and reporting.

### Selection

`manifest.json` is the complete selection. To run only shared environment ontologies, remove the skill IDs from the list and run `python loader.py`. To add a skill, add its `ar:skillDirectory` value and every declared dependency it needs. Missing dependencies produce a warning and abort; none are added automatically.

## Resource and interface semantics

Resource kinds are RDF individuals typed `ar:WorldSurfaceKind`; invocation kinds are individuals typed `ar:InvocationSurfaceKind`. They are also usable as RDFS/OWL classes through OWL 2 punning.

- `ar:specializesKind`: resource **is-a** relationship.
- `ar:specializesInvocationKind`: interface/invocation **is-a** relationship.
- `ar:containsKind`: possible part or containment relationship, not subtype.
- `ar:mayBeStoredAsKind`: possible physical representation of logical state.
- `ar:sharesKind`: possible shared state scope, not containment or universal visibility.
- `ar:routesToKind`: possible mediation/dataflow step from an invocation kind.
- `ar:protectedByKind`: a security control relevant to a surface; it does not prove that the control is enabled or effective.

Multiple parents are allowed. The loader validates specialization edges and rejects hierarchy cycles, but keeps the default report focused on operations and effects. An external OWL reasoner can project these edges into `rdfs:subClassOf` when class-level reasoning is needed.

`ar:ToolEndpoint` is the common callable parent. Shell execution, messaging endpoints, MCP tool endpoints, NanoClaw built-in MCP tools, provider file/web tools, and both forms of `ncl` are represented beneath it. A mediation component such as a channel adapter or mailbox write is an invocation surface but is not automatically an agent-facing tool endpoint.

## NanoClaw core scopes

The central distinction is:

```text
NanoClaw host process
  ├─ central database: users, roles, groups, wirings, sessions, config
  └─ orchestration: routing, guards, container lifecycle, delivery

Agent group
  ├─ persistent identity and configuration
  ├─ shared workspace / standing instructions
  └─ shared long-term memory

Session
  ├─ distinct conversation and provider continuation
  ├─ distinct inbound/outbound mailbox pair
  └─ per-session container lifecycle
```

Several sessions in the same agent group can share group working files and memory. Session separation therefore does not by itself establish confidentiality.

## Messaging and mailbox routes

Inbound and outbound paths are modeled as separate chains:

```text
Inbound platform event
  → NanoClaw channel-adapter inbound
  → host router and access/command gates
  → inbound mailbox write
  → agent-runner mailbox read
  → configured provider

Built-in send/edit/reaction tool
  → outbound mailbox write
  → host delivery and authorization
  → channel-adapter delivery
  → external messaging platform
```

`NanoClawSessionMailbox` is storage-neutral. The inspected checkout registers SQLite and uses the familiar `inbound.db` / `outbound.db` split, but the ontology does not define the abstraction as SQLite-only.

The split records single-writer authority:

- host writes the inbound side and the container reads it;
- container writes the outbound side and the host reads it;
- host delivery records and container processing acknowledgements remain on their owning sides.

`send_message`, `send_file`, `edit_message`, `add_reaction`, `ask_user_question`, and `send_card` are separate endpoint kinds. NanoClaw does not expose one universal message action with read, search, delete, poll, pin, presence, and channel-management operations.

## Management paths and authorization

Container and host invocations of `ncl` are distinct:

```text
Container: ncl → shell → outbound cli_request → host guard → action
Host:      ncl → shell → Unix socket → host dispatch → action
```

The container path is subject to `cli_scope` and action-specific guards. The host socket path is treated as trusted operator access by the current implementation. The ontology distinguishes scope eligibility from action decisions: `global` scope does not mean that every action bypasses approval.

Built-in `create_agent`, `install_packages`, and `add_mcp_server` tools emit structured host actions through the outbound mailbox. Adding an MCP server and later calling its tools are different events. Approval of installation is not a general runtime policy for each third-party MCP call.

The modeled controls include user/group admission, inbound command gate, CLI scope, host ALLOW/HOLD/DENY guard, human approval, destination ACLs, mount allowlisting, container isolation, optional resource limits, gateway policy, and optional egress lockdown. A `protectedByKind` edge is a candidate enforcement relationship, not runtime evidence.

## Filesystem and shell boundaries

`NanoClawContainerShellExecution` is a subtype of generic shell execution and runs inside the session container. It is not arbitrary host-shell access. The model separates:

- session workspace (`/workspace`, RW);
- agent-group workspace (`/workspace/agent`, RW but with nested RO configuration files);
- composed standing instructions and `container.json` (RO nested mounts);
- runner source and shared skills (RO);
- operator-configured additional mounts under `/workspace/extra`.

A write to a container path backed by a read-write host mount may change the underlying host directory. Additional mounts are modeled as protected by the host-side allowlist, but the actual path, realpath result, blocked patterns, and mode must be supplied by runtime observation.

## Network, OneCLI, and MCP

The ontology deliberately separates proxy configuration from forced egress:

```text
Proxy-aware request → OneCLI proxy/gateway → remote endpoint
Direct request      ───────────────────────→ remote endpoint
```

With egress lockdown disabled—the default—the direct path may exist. Effective lockdown places the agent on a Docker internal network and blocks the direct path; it does not transparently convert arbitrary sockets into proxy requests. Gateway policy applies only to requests reaching the gateway.

OneCLI gateway processing is modeled separately from the credential vault, per-agent identity, credential stubs, and CA material. For intercepted HTTPS, the gateway can access decrypted HTTP contents. This does not establish which contents are logged or how long they are retained.

Third-party MCP has two important paths:

```text
Local stdio MCP:
provider ↔ stdio transport ↔ local MCP process
                              └─ optional, separate network request

Remote HTTP MCP:
provider → HTTP transport → remote MCP service
                              └─ its downstream API calls occur remotely
```

Local stdio is not Internet traffic. A local server's later HTTP call can use OneCLI or attempt direct egress. For remote MCP, local controls cover the client-to-MCP leg; the remote service's later calls do not automatically traverse the local gateway or mailbox.

## Skill adaptation policy

The former compatibility vocabulary has been removed. Skill graphs now name NanoClaw endpoints directly. This is a **translation of the ontology models**, not a claim that the original skill text can execute unchanged. The source `SKILL.md` hashes remain pinned as provenance and drift checks.

An operation translated beyond what its source states uses `ar:adaptationStatus ar:InferredForNanoClaw`. Its original `ar:sourceStatus` remains separate, so script-inspected and example-only evidence is not erased by the translation. The loader counts adapted operations and prints a note.

The detailed crosswalk is RDF inside each skill graph. Every skill links to named `ar:AdaptationMapping` resources with `ar:sourceAssumption`, `ar:nanoclawModel`, one or more `ar:adaptationDisposition` values, and `ar:semanticDifference`. When appropriate, `ar:adaptedOperation` links the crosswalk entry to the modeled operation. All skills also link to `ar:NanoClawSkillAdaptationPolicy`, which holds the shared interpretation rule and pinned NanoClaw revision.

Important conservative choices include:

- Discord retains only native send, file, edit, and reaction actions. Read/search/delete/poll/pin/thread/presence are omitted rather than invented.
- channel configuration uses host-side `ncl` resource management plus a separately registered adapter; it does not assume a generic credential/config command.
- coding workers execute inside the session container and need an explicitly visible repository mount. Background process control remains provider-dependent.
- GitHub orchestration maps ephemeral sub-agents to NanoClaw's long-lived `create_agent` plus named-destination messaging.
- TaskFlow is approximated with scheduled tasks, run logs, mailbox wakeups, and companion agents. It is not an exact suspend/wait/resume implementation.

`Messaging-route` detects operations beneath the generic messaging invocation family. `NanoClaw-mailbox` is stricter and is `yes` only when the declared route reaches a NanoClaw mailbox read or write stage.

## Extending the model

### Add a new universal or support module

1. Add one `.trig` file under `universal/` or `skills/`.
2. Put exactly one non-empty named graph in that file.
3. Declare exactly one `ar:OntologyModule` resource with a unique string ID.
4. Declare every module dependency with `ar:requiresOntologyModule`.
5. If the graph must contain resources only, set `ar:resourcesOnly true`.
6. If it models a particular source checkout, add both `ar:sourceRepositoryPath` and `ar:sourceRevision`.
7. Add the ontology ID to `manifest.json` only when it should be selected explicitly.
8. Run the validation commands below.

Minimal example:

```turtle
@prefix ar: <urn:agent-risk:> .

ar:g_example_resources {
  ar:ExampleResourcesModule a ar:OntologyModule ;
    ar:ontologyModuleId "example-resources" ;
    ar:requiresOntologyModule "local-filesystem" ;
    ar:resourcesOnly true .

  ar:ExampleArtifact a ar:WorldSurfaceKind ;
    ar:specializesKind ar:LocalFile .
}
```

Do not put skill operations or effects in an always-loaded module. Always-loaded graphs describe the environment available for composition; selected skill graphs introduce claims about actions.

### Add a new skill ontology

1. Read the entire source `SKILL.md` and any scripts or references needed to understand its actual interfaces.
2. Create one file under `skills/` with one named graph.
3. Declare exactly one `ar:Skill` resource.
4. Record the exact source directory name in `ar:skillDirectory`.
5. Record the absolute source file in `ar:sourcePath` and its SHA-256 in `ar:sourceSha256`.
6. Declare all required environment modules with `ar:requiresOntologyModule`.
7. Model resource kinds and invocation kinds separately.
8. Model each supported action as an `ar:Operation` with at least one invocation kind, potential effect, and evidence status.
9. Record requirements even when the loader cannot evaluate them.
10. Add explicit `ar:AdaptationMapping` entries for every non-trivial NanoClaw translation, approximation, condition, or omission.
11. Add the skill directory to `manifest.json` only if it should load by default.
12. Validate the new skill explicitly before changing defaults.

Minimal skeleton:

```turtle
@prefix ar: <urn:agent-risk:> .

ar:g_example_skill {
  ar:skill_example a ar:Skill ;
    ar:skillDirectory "example-skill" ;
    ar:sourcePath "/absolute/path/to/top_skills/example-skill/SKILL.md" ;
    ar:sourceSha256 "<sha256>" ;
    ar:requiresOntologyModule "nanoclaw-runtime" ;
    ar:governedByAdaptationPolicy ar:NanoClawSkillAdaptationPolicy ;
    ar:hasAdaptationMapping ar:adapt_example_action ;
    ar:declaresOperation ar:op_example_action .

  ar:ExampleOutput a ar:WorldSurfaceKind ;
    ar:specializesKind ar:LocalFile .

  ar:cond_example_writable a ar:Requirement .

  ar:op_example_action a ar:Operation ;
    ar:invokedThroughKind ar:NanoClawProviderFileTool ;
    ar:targetsKind ar:ExampleOutput ;
    ar:requires ar:cond_example_writable ;
    ar:sourceStatus ar:SkillText ;
    ar:adaptationStatus ar:InferredForNanoClaw ;
    ar:hasPotentialEffect [
      a ar:PotentialEffect ;
      ar:effectType ar:Create ;
      ar:affectsKind ar:ExampleOutput
    ] .

  ar:adapt_example_action a ar:AdaptationMapping ;
    ar:sourceAssumption "The source skill can write an output file." ;
    ar:nanoclawModel "NanoClawProviderFileTool in container-visible storage." ;
    ar:adaptationDisposition ar:ConditionalAdaptation ;
    ar:semanticDifference "The writable scope is limited to container-visible storage." ;
    ar:adaptedOperation ar:op_example_action .
}
```

Compute the source hash on macOS with:

```bash
shasum -a 256 /absolute/path/to/SKILL.md
```

When the source skill changes, do not merely update the hash. Re-review the skill, revise its ontology and adaptation mappings, and only then update `ar:sourceSha256`.

### Add or change a subtype definition

Use `ar:specializesKind` or `ar:specializesInvocationKind` for ordinary necessary-only taxonomy edges. Use `owl:equivalentClass` only when the RDF facts are genuinely sufficient to recognize membership.

Every modeled kind with `owl:equivalentClass` must also be targeted by a SHACL shape. The loader enforces this coverage rule. If recognition depends on an external check, represent the check result as observation data rather than pretending OWL performed it. `gitRepositoryValidated true` is the existing example.

### Modeling checklist

Before accepting a new graph, ask:

- Is this node a resource/state kind, an invocation path, an operation, or a concrete observation?
- Is the relationship subtype, containment, storage representation, sharing, mediation, or protection?
- Does the source actually assert the action, or is it a NanoClaw inference?
- Is the effect a possibility, and have its requirements been recorded?
- Does a remote MCP service create a control boundary different from a local stdio server?
- Does a container path map to a read-write host mount, a read-only mount, or container-local state?
- Does a messaging action use a built-in endpoint, a projected destination, an adapter, or an added third-party tool?
- Would the graph accidentally imply broader host, network, credential, or message-history authority than the source supports?
- Are unsupported actions omitted or explicitly recorded as unsupported rather than silently invented?

## Qualified subtype definitions

Every specialization edge is a necessary-only definition. A kind becomes necessary-and-sufficient only with `owl:equivalentClass`; the loader then requires a corresponding SHACL target shape.

`skills/git-resources.trig` demonstrates the pattern without falsely defining every Git repository as a directory containing `.git`:

- `GitMetadataEntryCandidate`: exactly an entry named `.git`.
- `ConventionalGitWorkingTreeCandidate`: exactly a local directory containing such an entry.
- `ConventionalGitWorkingTree`: candidate plus explicit `gitRepositoryValidated true` evidence.
- `LocalGitRepository`: primitive broader kind because bare repositories, linked worktrees, and external Git directories need not contain a `.git` entry.

An external OWL-RL reasoner can infer positive membership for concrete observations. SHACL can then check the required evidence. `loader.py` validates the selected ontology graphs and the matching SHACL shapes; it does not load observation files or perform instance classification. Missing facts do not prove non-membership.

## Run and validate

The prototype has no packaging wrapper. Run it from this directory with Python 3 and install `rdflib` and `pyshacl` in your environment:

```bash
python3 -m pip install rdflib pyshacl
```

The loader takes no arguments. Edit `manifest.json` to select the ontologies, then run:

```bash
python3 loader.py
```

For example, add `coding-agent` to the manifest alongside its declared dependencies to include that skill. Remove `discord` or `gh-issues` from the list to exclude them. The files in `examples/` remain standalone observation fixtures for external RDF/OWL/SHACL experiments; this loader does not read them.

### Reading the report

The loader prints the loaded skills, an operation count, one compact row per operation/effect/resource combination, and the modeled potential Internet calls with their initiator, endpoint, and conditions. Resource inventories, hierarchies, invocation routes, security controls, and subtype-definition tables are still loaded and validated but are no longer printed. The report describes modeled possibilities, not a trace of a running system.

### Expected failures and what they mean

| Error | Meaning | Correct response |
|---|---|---|
| `Unknown ontologies in manifest.json` | A listed ID matches no discovered graph | Fix the selection or graph metadata |
| `loader.py takes no arguments` | A command-line argument was supplied | Edit `manifest.json` and run `python3 loader.py` |
| `Duplicate ontology ID` | Two graphs claim the same identity | Give each graph a unique ID |
| `Expected one named graph` | A TriG file violates the discovery convention | Keep one populated named graph per file |
| `is stale: source checkout changed` | The pinned NanoClaw checkout moved | Re-review the changed source before updating the revision |
| `source skill has changed` | `SKILL.md` no longer matches `ar:sourceSha256` | Re-review and update the skill graph, then its hash |
| `Dependency preflight failed` | A declared requirement is unknown or absent from the selected ontologies | Add/review the required ontology and explicitly update `manifest.json` |
| `Always-loaded graph contains operations` | Environment and selected-skill responsibilities were mixed | Move operations/effects into a skill graph |
| `Cycle in` | A specialization path loops back to itself | Correct the taxonomy; do not use subtype for containment/routes |
| `Equivalent kinds without SHACL shapes` | An OWL definition lacks its closed-world validator | Add a corresponding target shape |
| `SHACL validation failed` | Selected ontology graph structure violates a shape | Read the focus node, path, and source shape in the report |

An absent dependency is intentionally not repaired automatically. Treat the abort as a request for an explicit environment-policy decision.

## Querying the model

`loader.py` contains a built-in potential-effect report, but the same TriG files can be loaded into RDFLib, Apache Jena, GraphDB, Stardog, RDF4J, or another RDF dataset implementation. Queries that rely on property paths require a SPARQL 1.1 implementation.

Useful SPARQL paths:

```sparql
PREFIX ar: <urn:agent-risk:>

# All broader resource kinds.
SELECT ?narrow ?broader WHERE {
  ?narrow ar:specializesKind+ ?broader .
}

# All shell-mediated operations.
SELECT DISTINCT ?operation WHERE {
  ?operation ar:invokedThroughKind/ar:specializesInvocationKind* ar:ShellExecution .
}

# Potentially affected resources, retaining skill-graph provenance.
SELECT DISTINCT ?graph ?skill ?operation ?effectType ?resourceKind WHERE {
  GRAPH ?graph {
    ?skill a ar:Skill ;
           ar:declaresOperation ?operation .
    ?operation ar:hasPotentialEffect ?effect .
    ?effect ar:effectType ?effectType ;
            ar:affectsKind ?resourceKind .
  }
}

# Potential effects on a resource kind or any of its subtypes.
SELECT DISTINCT ?operation ?effectType ?resourceKind WHERE {
  ?operation ar:hasPotentialEffect ?effect .
  ?effect ar:effectType ?effectType ;
          ar:affectsKind ?resourceKind .
  ?resourceKind ar:specializesKind* ar:LocalFile .
}

# Possible NanoClaw mediation chain from a concrete endpoint.
SELECT ?next WHERE {
  ar:NanoClawSendMessageTool ar:routesToKind+ ?next .
}

# Explicitly modeled Internet-call possibilities in selected skill graphs.
# Endpoint patterns are optional: an absent pattern means the exact URL is not established.
SELECT ?graph ?operation ?call ?stage ?initiator ?endpoint ?pattern WHERE {
  GRAPH ?graph {
    ?operation ar:mayInitiateInternetCall ?call .
    ?call a ar:PotentialInternetCall ;
          ar:callStage ?stage ;
          ar:callInitiatorKind ?initiator ;
          ar:callEndpointKind ?endpoint .
    OPTIONAL { ?call ar:callEndpointPattern ?pattern }
  }
}

# Calls to GitHub's Git or REST endpoint kinds, including narrower kinds.
SELECT DISTINCT ?operation ?call ?endpoint WHERE {
  ?operation ar:mayInitiateInternetCall ?call .
  ?call ar:callEndpointKind ?endpoint .
  VALUES ?githubEndpoint { ar:GitHubGitEndpoint ar:GitHubRESTEndpoint }
  ?endpoint ar:specializesKind* ?githubEndpoint .
}

# Auditable source-to-NanoClaw skill adaptations.
SELECT ?skill ?assumption ?nanoclawModel ?disposition ?difference WHERE {
  ?skill ar:hasAdaptationMapping ?mapping .
  ?mapping ar:sourceAssumption ?assumption ;
           ar:nanoclawModel ?nanoclawModel ;
           ar:adaptationDisposition ?disposition ;
           ar:semanticDifference ?difference .
}
```

Do not merge subtype, containment, route, and protection edges into one undifferentiated reachability relation. A file inside a directory is not a kind of directory; a route protected by a policy is not proof the policy allows it; a possible path is not proof that credentials and permissions make it executable.

## Limits

This is a manually reviewed architecture model, not a complete code audit or deployed inventory. It does not observe installed channel adapters, live users or roles, actual mount paths, filesystem modes, container network membership, OneCLI policies, credentials, provider tool inventories, or remote MCP behavior. The repository documentation itself warns that some design documents can drift; stable source links in the graph pin the inspected commit, but later NanoClaw revisions require re-review.

Most kinds are primitive because the code does not provide reliable necessary-and-sufficient recognition facts in RDF form. `routesToKind` is an over-approximation of possible mediation, not temporal semantics or guaranteed transitive execution. Inferring which resources can actually change still requires concrete tool availability, arguments, identity, authority, configuration, current state, and policy decisions. Generic shell execution and delegated workers remain open-ended.
