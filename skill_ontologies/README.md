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
llm_annotation.py                    optional LLM joint-risk annotation
materialize.py                       instantiate the model for one live NanoClaw session
observations/                        session snapshots written by materialize.py (git-ignored)
examples/*.ttl                       standalone concrete observation fixtures
```

The loader never fetches or dynamically introduces a dependency. A dependency named by any selected ontology must already appear in `manifest.json`; otherwise loading aborts before the combined graph is assembled.

### Sources and evidence boundary

This directory combines two kinds of source-derived model:

- `universal/` describes the generic resource vocabulary and the NanoClaw harness architecture that is present independently of a selected skill.
- `skills/` describes interfaces and potential effects asserted by individual `top_skills/*/SKILL.md` files, plus support graphs shared only by those skills.

The NanoClaw model was checked against local checkout commit `64064244396ecbfee72fcd2c069290fb21d9c6ee` (branch `customized`: upstream `7902716b` plus local commits). It models architecture abstractly: installed channel adapters appear only as the generic adapter kinds, and per-install settings (such as whether egress lockdown is enabled) are conditions, not facts. Host-only behavior that an agent cannot trigger is out of scope, as is model-provider API traffic. Repository code is treated as the primary source; the [shared architecture discussion](https://chatgpt.com/s/cx_6ab168a066788191a0767199e971bbd4) was useful orientation but is not the authority when it differs from code. The model is not a statement about the live configuration of any NanoClaw installation.

All graphs use `ar: <urn:agent-risk:>`. These are local identifiers, not dereferenceable Web URLs. A published ontology should use an owned persistent HTTPS namespace.

```text
skill_ontologies/
  manifest.json          one list of selected ontology IDs
  loader.py              dependency checks, validation, reports
  llm_annotation.py      resource pairing, prompts, and OpenAI calls
  materialize.py         live-session instantiation and per-session report
  observations/          snapshot graphs (git-ignored; contain real identifiers)
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
| Native capability | `ar:NativeCapability` | Potential action of a loaded harness endpoint, independent of skill text | container file read; shell file write |
| Potential effect | `ar:PotentialEffect` | Possible typed consequence of an operation | create a message; transmit to a channel |
| Potential Internet call | `ar:PotentialInternetCall` | Possible outbound request, distinguished from the operation and its world effect | a later host Discord API request |
| Requirement | `ar:Requirement` | Condition needed for the modeled action/effect | destination exists; permission is granted |
| Security control kind | `ar:SecurityControlKind` | Kind of configuration or enforcement point | destination ACL; mount allowlist |
| Mount access mode | `ar:MountAccessMode` | Read-only or read-write at one mount boundary, not effective OS permission | `ar:ReadOnlyMountMode` |
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
  = combined validation and reporting graph
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

The manifest currently lists ten shared ontologies and four skill ontologies. Five shared ontologies describe NanoClaw itself: core, messaging/mailboxes, management controls, container/filesystem runtime, and network/OneCLI paths. Generic tool, filesystem, internet, and shell graphs are also selected. Git resource definitions live under `skills/` even though they are selected on every run; folder placement and load policy are separate concerns.

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

During dependency preflight, the loader parses graph metadata, checks that selected ontology IDs exist, and requires every dependency to already be selected in `manifest.json`. It does not assemble the combined graph until this preflight succeeds. As selected graphs are added, it verifies module source revisions and skill-source hashes. A missing or unknown dependency produces a warning and aborts; dependencies are never introduced automatically. Individual named graphs remain in the catalog; no redundant dataset copy is constructed.

`manifest.json` is the only ontology-selection configuration file and is a literal JSON array. The loader resolves each ID against RDF metadata; no type label is needed in the list. To change the loaded ontologies, edit this list and run `python loader.py`. Use `--max-pairs N` to limit LLM annotation and `--model MODEL` to select the model. API credentials may be supplied by environment variables or a local `.env` file.

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

Every always-loaded graph is checked to contain no `ar:Operation`, `ar:PotentialEffect`, `ar:declaresOperation`, or `ar:hasPotentialEffect`. The NanoClaw runtime, network, and messaging graphs may declare `ar:NativeCapability` facts instead; these describe conditional endpoint affordances, not skill actions or observed calls. `local-filesystem.trig` and `freeform-internet.trig` are additionally marked `resourcesOnly` and cannot declare invocation kinds.

### Loader sequence

For an agent modifying this project, the order matters:

1. Read `manifest.json` as a JSON array of unique ontology IDs.
2. Discover every `*.trig` file under `universal/` and `skills/`. Each must contain exactly one non-empty named graph.
3. In one pass, identify each graph as a module or skill from its RDF metadata and reject duplicate IDs.
4. Resolve the manifest IDs and check every selected graph's declared dependencies. Missing dependencies warn and abort before any active graph is loaded.
5. Load the vocabulary and selected graphs in manifest order, checking module source pins and skill-source hashes as they are added.
6. Check typed relationship endpoints, subtype cycles, endpoint parentage, shared-graph restrictions, and equivalent-class shape coverage.
7. Run SHACL over the assembled graph.
8. Print loaded skill operations, potential effect/resource rows, and modeled potential Internet calls.
9. Combine skill-declared effects with native endpoint capability effects, form unordered pairs of distinct affected resource kinds, apply `max_pairs`, and ask an OpenAI model about joint consequences. `max_pairs=0` skips annotation.

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
- `ar:subjectToControlKind`: controls relevant to some paths of a skill, not a conjunctive permission check on every operation.
- `ar:mayResideInKind`: possible location of a file/resource kind, not a claim about every concrete file.
- `ar:mountExposesKind`, `ar:mountAccessMode`, and `ar:mountConditionalOn`: what one mount can expose, its mode, and any unresolved condition.

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

Several sessions in the same agent group can share group working files and memory. Session separation therefore does not by itself establish confidentiality. A scheduled task runs in its own per-series task session, not in the session that created it.

A provider subagent (for example Claude's Task tool) is not a NanoClaw agent group: it runs in the same container with the same files, tools, network route, and gateway identity, so it adds no isolation. A separately isolated agent requires `create_agent`.

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

The split records the intended write ownership, which is a convention rather than a mount-level boundary:

- host writes the inbound side and the container reads it. The runner opens it read-only, but the file sits on the read-write `/workspace` mount, so any container process can alter it (`NativeShellInboundMailboxMutation`);
- container writes the outbound side and the host reads it. Any container process can insert rows, not only the built-in tools (`NativeShellOutboundMailboxWrite`), and the host also writes there in two cases: a direct reply when the command gate denies a command, and cleanup of orphaned processing claims;
- host delivery records and container processing acknowledgements remain on their owning sides.

Destinations are split in two. `NanoClawDestinationGrant` is the central record that host delivery authorizes non-origin sends against. `NanoClawProjectedDestination` is the session's copy, used only to resolve a name; editing it grants nothing. The session's origin chat is always permitted.

`send_message`, `send_file`, `edit_message`, `add_reaction`, `ask_user_question`, and `send_card` are separate endpoint kinds. NanoClaw does not expose one universal message action with read, search, delete, poll, pin, presence, and channel-management operations.

## Management paths and authorization

Container and host invocations of `ncl` are distinct:

```text
Container: ncl → shell → outbound cli_request → host guard → action
Host:      ncl → shell → Unix socket → host dispatch → action
```

The container path is subject to `cli_scope` and action-specific guards. The host socket path is treated as trusted operator access by the current implementation. The ontology distinguishes scope eligibility from action decisions: `global` scope does not mean that every action bypasses approval. Under the default `group` scope, container `ncl` reaches its own group's `groups`, `sessions`, `destinations`, `members`, and `tasks`; task commands need no approval, while writes to the others are held for approval (`NanoClawContainerTasksCLI`, `NanoClawContainerGroupAdminCLI`). `global` scope adds the remaining resources, with every write held (`NanoClawContainerGlobalAdminCLI`).

Built-in `create_agent`, `install_packages`, and `add_mcp_server` tools emit structured host actions through the outbound mailbox. `install_packages` and `add_mcp_server` are always held for admin approval; `create_agent` is held unless the requesting group has `cli_scope=global`. Adding an MCP server and later calling its tools are different events. Approval of installation is not a general runtime policy for each third-party MCP call.

Inside the container, the Claude provider runs with `bypassPermissions`: every allowed tool call is auto-approved (`NanoClawProviderToolPolicyControl`). Per-call approval does not exist; privileged effects are gated host-side instead.

The modeled controls include user/group admission, inbound command gate, CLI scope, host ALLOW/HOLD/DENY guard, human approval, destination ACLs, mount allowlisting, container isolation, optional resource limits, gateway policy, and optional egress lockdown. Host `ncl` access is separately associated with the operator's Unix-socket boundary; the inspected CLI guard treats host callers as trusted rather than applying the container `cli_scope` rule. A `protectedByKind` edge is a candidate enforcement relationship, not runtime evidence.

## Filesystem and shell boundaries

`NanoClawContainerShellExecution` is a subtype of generic shell execution and runs inside the session container. It is not arbitrary host-shell access. The model separates:

- session workspace (`/workspace`, RW);
- agent-group workspace (`/workspace/agent`, RW but with nested RO configuration files);
- composed standing instructions and `container.json` (RO nested mounts);
- runner source and shared skills (RO);
- operator-configured additional mounts under `/workspace/extra`.

A write to a container path backed by a read-write host mount may change the underlying host directory. Additional mounts are modeled as protected by the host-side allowlist, but the actual path, realpath result, blocked patterns, and mode must be supplied by runtime observation.

### Container side and host side

Every NanoClaw location and step is assigned to the component it belongs to:

- `ar:locatedOn` on resource kinds and `ar:executesOn` on invocation kinds name `ar:NanoClawAgentContainer`, `ar:NanoClawHostProcess`, `ar:OneCLIGateway`, or `ar:ExternalNetwork` (everything beyond the local machine). Both are inherited along the specialization hierarchy unless a narrower kind states its own.
- Remote kinds (`Internet`, `RemoteNetworkEndpoint`, `RemoteWebResource`, `RemoteService` and so `RemoteMCPService`, `MessagingPlatform` and its groups, threads, and messages) are on `ar:ExternalNetwork`. Exceptions: `NanoClawHostReachableService` is on the host, and local channels (CLI, Emacs) deliver on the host; a snapshot resolves that per channel. Provider web search executes on `ar:ExternalNetwork` (at the model provider), while web fetch, shell requests, and MCP clients start in the container and cross the gateway.
- Container-side location kinds (`NanoClawSessionWorkspace`, `NanoClawAgentGroupWorkspace`, `NanoClawProviderStateDirectory`, ...) are **views at container paths**. The host directory behind each is a separate host-side kind (`NanoClawHostSessionDirectory`, `NanoClawHostGroupDirectory`, `NanoClawHostProviderStateDirectory`, ...) with an `ar:hostPathPattern` relative to the checkout.
- Each mount kind states its `ar:containerPath` (a trailing `*` marks a prefix) and its host source with `ar:bindsFromKind`. A write through the container view changes that host location; the host side can also have writers the container never sees (inbound rows, attachments, task-log appends, files recomposed at spawn).
- The container's writable layer and its processes (`NanoClawContainerProcess`, which includes local MCP servers) have no host counterpart. There is no agent-reachable host shell: host-side effects happen only through fixed host steps such as `NanoClawHostDeliveryInvocation`, `NanoClawHostCommandDispatch`, `NanoClawHostTaskLogAppend`, `NanoClawHostImageBuild`, `NanoClawHostConfigMaterialization`, and `NanoClawHostAttachmentStaging`.
- Container entry points route directly to the host step they cause (for example `NanoClawInstallPackagesTool → NanoClawHostImageBuild`). Host delivery is a hub every outbound row passes through, so tools are not routed to the whole fan-out behind it.

The loader checks that sides name a system component, that `bindsFromKind` appears only on mounts, and (via SHACL) that every mount has one container path and one host source on the host side.

### Permission and mount mapping

The ontology names individual mount kinds and their **mount-layer** access modes:

| NanoClaw location | Mount mode | Meaning |
|---|---|---|
| `/workspace` | RW | Session directory: both mailbox files, heartbeat, `outbox/`, and `inbox/` attachments |
| `/app/.nanoclaw-session.json` | RO | Host-written session identity file |
| `/workspace/agent` | RW | Group working files, persistent memory, conversation archives, task run logs, and `plugin-data/`, shared by the group's sessions |
| `/workspace/agent/container.json`, `CLAUDE.md`, and `plugins/` | RO | Nested mounts that override the writable parent at those paths; some depend on materialization/provider choice |
| `/app/src` and `/app/skills` | RO | Shared runner and installed skill content; the skills mount requires the directory to exist |
| `/home/node/.claude` | RW in the default Claude configuration | Group-scoped provider state, including settings loaded by later sessions of the group; other providers may contribute different mounts |
| `/workspace/extra/<name>` | RO or RW, conditional | Operator-selected host directory; no allowlist means no additional mount. RW requires both `readonly: false` in group config and `allowReadWrite: true` on the matched root |
| OneCLI CA and credential-stub paths | RO, conditional | Gateway-contributed files; credential stubs are not the underlying secrets |

The container's private writable layer is a possible local-file location but **not** a host bind mount. `ar:mayResideInKind` links file kinds in each skill to plausible locations; `ar:mountExposesKind` then links locations to mount kinds. For example, a coding worktree may be in the group workspace, an extra host mount, or a container-private layer. This is a set of alternatives, not one simultaneous permission or a claim that an arbitrary host repository is visible. A diagram template may be in read-only shared skills, while an output artifact needs a writable target. File-writing operations now explicitly require `ar:cond_container_file_writable`; file-reading operations that depend on a concrete path require `ar:cond_container_file_readable`.

Host-mediated operations are different: a container `ncl` request for a scheduled task is checked by CLI scope and host action guards, then the host may write a task log. The container's mount mode is not the host's write authorization for that action.

An admitted extra mount is read-only unless both RW conditions hold. The allowlist checks the **mount root** realpath against roots and blocked patterns; it does not inspect every descendant. Host OS file modes/ACLs, container identity, symlinks, nested mounts, provider tool policy, and the concrete path can restrict access further. The host project root is not automatically mounted. Loaded skill instructions do not themselves confer file, network, messaging, or service permissions. Each skill has `ar:subjectToControlKind` edges for relevant control families; those edges do not mean every control is on every route or that authorization succeeded.

For a type-level *candidate* mount-mode query after loading the selected graphs:

```sparql
PREFIX ar: <urn:agent-risk:>
SELECT ?location ?mount ?mode WHERE {
  ar:LocalGitRepository ar:mayResideInKind+ ?location .
  ?mount ar:mountExposesKind ?location ; ar:mountAccessMode ?mode .
}
```

The query does not return container-private locations (which are not mounts), decide which alternative was configured, account for nested path overrides, or compute effective access. That requires a runtime inventory of mount specs, canonical paths, process identity, OS permissions, tool policy, and remote-service authorization. SHACL validates the declarations' structure and RO/RW consistency; it does not evaluate those runtime facts.

## Network, OneCLI, and MCP

The ontology deliberately separates proxy configuration from forced egress:

```text
Proxy-aware request → OneCLI proxy/gateway → remote endpoint
Direct request      ───────────────────────→ remote endpoint
```

With egress lockdown disabled—the default—the direct path may exist. Effective lockdown places the agent on a Docker internal network and blocks the direct path; it does not transparently convert arbitrary sockets into proxy requests. Gateway policy applies only to requests reaching the gateway.

OneCLI gateway processing is modeled separately from the credential vault, per-agent identity, credential stubs, and CA material. The gateway identity is per agent group, so gateway credentials and policy cannot distinguish a group's sessions or subagents.

Provider web tools are split by where they run: `NanoClawProviderWebFetchTool` fetches from inside the container (gateway or direct route), while `NanoClawProviderWebSearchTool` runs on the model provider's side: the query leaves inside the model request (through the gateway), but the searches and site contacts happen at the provider, so local egress controls cannot restrict them. With lockdown off, the direct route can also reach services on the Docker host (`NanoClawHostReachableService`). For intercepted HTTPS, the gateway can access decrypted HTTP contents. This does not establish which contents are logged or how long they are retained.

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

Do not put skill operations or `ar:PotentialEffect` nodes in an always-loaded module. Always-loaded graphs describe the environment available for composition; selected skill graphs introduce claims about actions. Native endpoint affordances may be declared as `ar:NativeCapability` with endpoint, effect type, resource kind, scope, requirements, and source note, without pretending that a skill invoked them.

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

The prototype has no packaging wrapper. Run it from this directory with Python 3 and install its dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Edit `manifest.json` to select the ontologies, then run (this annotates all pairs):

```bash
python3 loader.py
```

The execution flow lives in `loader.main()` behind an `if __name__ == "__main__"` guard. Importing `loader` does not read ontologies, print reports, or call the LLM; call `loader.main()` explicitly to run the workflow.

For example, add `coding-agent` to the manifest alongside its declared dependencies to include that skill. Remove `discord` or `gh-issues` from the list to exclude them. The files in `examples/` remain standalone observation fixtures for external RDF/OWL/SHACL experiments; this loader does not read them.

### Reading the report

The loader prints aligned, wrapping tables for its summary, skill control context, operations, native capabilities, mount exposures, affected resources, and Internet calls. Each selected skill operation shows its invocation endpoint(s), targets, requirements, source/adaptation evidence, available source note, and typed resource effects. Native endpoint capabilities from loaded universal graphs (currently file-tool read/write, shell execution and file/network access, direct shell writes to mailbox, task-log, and provider-settings state, provider web fetch and search, subagent start, and built-in message/file-send paths) are **conditional possibilities**, not extra skill operations, confirmed tool exposure, or permission grants. Resource rows include definitions when recorded, subtype and direct containment context, plausible file locations/mounts, and relevant controls. Internet calls show initiator, endpoint, and conditions. No runtime mount inventory, effective ACL decision, or observed action is inferred.

Both **skill-declared effects and native endpoint capability effects** are passed to the LLM pair annotator. This permits cross-surface assessments such as native file reading combined with a skill's message creation, and it can increase the number and cost of pair assessments. The annotator prints its pair selection, per-pair assessments, effect types, and summary in tables; the saved JSONL format is unchanged. It counts unordered pairs of distinct resource kinds across both sources. Repeated touches to one kind are consolidated into a single set of effect types. Skill, operation, and native-capability provenance remains in the local report but is excluded from the annotation input.

### Optional joint-consequence analysis

`llm_annotation.py` owns the resource pairing, prompt, response schema, API calls, and annotation output. `loader.py` builds a list of resource descriptions and effect types, then calls `analyze_pairs(resources, model=..., max_pairs=...)`. The annotation module never receives the ontology graph, selected skills, operation identifiers, source paths, adaptation mappings, or invocation routes. Continue running `loader.py` as the entry point; importing `llm_annotation.py` alone does not run an analysis.

Each resource description contains its RDF kind identifier, label, definition, subtype ancestors (`parents`), possible containing kinds (`contained_in`), and deduplicated effect types (`effects`, such as `Read`, `Update`, or `Transmit`). Definitions project `rdfs:label`, `rdfs:comment`, `skos:definition`, and `owl:equivalentClass`, including connected OWL expressions and definitions of referenced terms. They are serialized as sorted, canonical N-Triples (also valid Turtle), stabilizing blank-node identifiers for prompt caching across runs. They exclude graph/skill provenance and source metadata. Related kinds carry their own definitions. A missing definition is `null`; the loader does not invent prose. Parents follow explicit `ar:specializesKind` links; containing kinds follow inverse `ar:containsKind` links, transitively. Containment is not subtype, ownership, or proof of co-location. Resource/platform names remain meaningful (for example, `DiscordMessage`); this removes explicit skill provenance, not every possible inference about capability from a resource's name or definition.

To cap the number of annotated pairs, run `python3 loader.py --max-pairs 50`. Omit the flag to include every pair, or use `--max-pairs 0` to skip annotation. The limit must be a non-negative integer. Resource order is shuffled on each run before forming pairs; a limit selects the first N combinations of that shuffled order. This removes the fixed RDF-identifier ordering, but is not a uniform sample of pairs: early combinations share resources. The catalog remains sorted for stable prompt caching when the selected resource set is unchanged. The report shows both the selected and total pair counts; unselected pairs remain unanalyzed. The underlying `analyze_pairs(resources, model="gpt-6-luna", max_pairs=50)` function remains available for programmatic use.

Put `OPENAI_API_KEY=...` in this directory's `.env` file or your process environment. `.env` is git-ignored; do not commit or print it. The default model is `gpt-6-luna`; use `--model MODEL` to override it, or pass `model=...` to `analyze_pairs`. `OPENAI_MODEL` is no longer used. A supplied model must support the Responses API and structured outputs and be available to your API account. Running the loader directly makes paid API requests for the selected pairs, without an environment toggle or confirmation prompt. Use `--max-pairs 0` to skip annotation. Missing API credentials are reported by the OpenAI SDK.

```bash
python3 loader.py --model gpt-6-luna --max-pairs 50
```

The loader makes one sequential OpenAI Responses API call per resource pair, returning one assessment object per call. A shared resource catalog contains definitions, subtype/containment context, and effect types from skill operations and native endpoint capabilities; each call adds only the two resource kind identifiers to that shared prefix. The simplified prompt asks for a consequence requiring **both** resources in one hypothetical agent session, grounded only in the catalog. `Read` means access, not mutation; skill identity, capability identity, and actual execution are not assumed. Each flagged result prints both resources' possible effect types, the consequence, why both matter, and necessary assumptions. The printed effects are the supplied possibilities, not observed actions or a claim that every effect occurs. Removing operation and capability provenance deliberately loses which effects belong to the same action, their prerequisites, and whether a native endpoint is actually exposed. The model's answer is a brainstorming aid, **not a sound inference or proof of an exploitable path**. The ontology is a may-effect model; it does not establish action order, argument values, concrete instances, permissions, runtime reachability, or that two effects actually occur in one session. Without a limit, cost scales approximately quadratically in the number of distinct affected kinds. A supplied `max_pairs` caps the pairs sent for annotation; omitted pairs are not assessed. For example, `--max-pairs 50` makes up to 50 assessment calls, depending on the available pairs.

### Saved assessments

Each annotation run creates `results/assessments-<UTC timestamp>.jsonl` and prints its absolute path. Each line is a JSON object with `model`, `first`, `second`, and `assessment`. The two resource objects include the definitions, hierarchy context, and possible effects supplied for that pair. The assessment contains `joint_risk`, `consequence`, `why_both`, and `assumptions`; negative assessments are saved too. Each completed assessment is appended and the file closed before continuing, preserving earlier results if a later call fails or the run is interrupted. A partial file contains only completed assessments, not evidence that every selected pair was analyzed. Runs use separate files rather than overwriting previous results. `--max-pairs 0` creates no result file. The `results/` directory is git-ignored because outputs may contain sensitive resource descriptions. These files save parsed assessments, not raw API responses, and are not used as an answer cache.

### Prompt caching

The instructions, output schema, and catalog are identical across assessments. Only resources appearing in selected pairs are included in the catalog. GPT-6 and GPT-5.6 requests use an explicit cache breakpoint after the catalog, with `prompt_cache_options={"mode": "explicit", "ttl": "30m"}`; the changing pair is not written to that prefix cache. A stable `prompt_cache_key` is supplied for all models; older models use their automatic prefix caching instead of the newer explicit controls. This is API prompt caching, not a local cache of generated answers. Each response's reported cached-input-token count is printed when usage is available. Cache hits are not guaranteed: minimum prefix lengths, expiry, model changes, and changes to the resource catalog can prevent reuse. The first cache write may cost more than ordinary input; reuse can reduce input-processing cost. See the [official prompt-caching guide](https://developers.openai.com/api/docs/guides/prompt-caching).

### Expected failures and what they mean

| Error | Meaning | Correct response |
|---|---|---|
| `Unknown ontologies in manifest.json` | A listed ID matches no discovered graph | Fix the selection or graph metadata |
| `--max-pairs must be non-negative` | A negative annotation limit was supplied | Use zero to skip, a positive limit, or omit the flag for all pairs |
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

## Instantiating the model for a live session

The universal graphs describe what *any* NanoClaw session might do. `materialize.py` turns them into a snapshot of *one* running session: it observes that session's actual configuration, records it as typed instances of the ontology's kinds, settles the model's requirements for it, and reports what that session can still reach or change.

```bash
python3 materialize.py                      # most recently active session with a running container
python3 materialize.py --session <id>       # a specific session (its container must be running)
python3 materialize.py --no-write           # print the report without saving a snapshot
python3 materialize.py --nanoclaw <path>    # checkout to inspect (default: nanoclaw-core's sourceRepositoryPath)
python3 materialize.py --out <dir>          # snapshot directory (default: observations/)
```

It needs a running NanoClaw service, Docker, and the `onecli` CLI. `ncl`, `onecli`, `docker`, and `git` are found on `PATH` or in `~/.local/bin`, where NanoClaw setup installs them. It changes nothing in NanoClaw: every read goes through read-only interfaces.

### How it works

1. **Load the model.** `vocabulary.ttl` plus every `universal/*.trig` graph. If the checkout's `HEAD` differs from `nanoclaw-core`'s pinned `sourceRevision`, it warns that the results may be stale. Skill graphs are only consulted to match installed skills by `skillDirectory`.
2. **Collect facts** (`collect()`), names and settings only, never secret values, tokens, or environment values:

   | Source | Facts |
   |---|---|
   | host `ncl ... --json` | session, agent group, group config (`cli_scope`, provider, MCP servers, packages, extra mounts), other sessions in the group, messaging groups, wirings, destination grants, roles, members |
   | session `inbound.db` (opened read-only) | projected destinations |
   | `docker inspect` / `docker network inspect` | mounts with RO/RW mode, image, user, hardening flags, resource limits, networks and whether they are internal |
   | `docker exec ... command -v curl` | whether a network client exists in the container |
   | `onecli agents/secrets/rules list` | gateway identity and secret mode (never the access token), secret names and host patterns, rule count in scope |
   | the checkout | installed `container/skills`, whether the agent-to-agent module is present, `HEAD` |

3. **Instantiate** (`Snapshot.build()`). Mounts are matched to mount kinds by the model's `ar:containerPath` (most specific match). Each mount yields a container-side location instance (`obs:onSide ar:NanoClawAgentContainer`) and a separate host-side instance of its `ar:bindsFromKind` kind (`obs:onSide ar:NanoClawHostProcess`, host path relative to the checkout), linked by `obs:bindsFrom` / `obs:backedBy`. Each fact becomes an instance typed with an existing kind (`a ar:NanoClawSession`, `a ar:NanoClawSessionWorkspaceMount`, `a ar:NanoClawDestinationGrant`, `a ar:NanoClawEgressLockdownControl`, ...) and linked with `obs:` properties (`obs:inAgentGroup`, `obs:mountedIn`, `obs:exposes`, `obs:accessMode`, ...). Every instance carries `obs:evidenceKind`: `obs:Observed` (read from the running container or gateway) or `obs:FromConfiguration` (read from configuration). Observed mounts are classified by container path, and each mount's location is typed with the kinds the model says it exposes. Mismatches are reported as model/runtime differences: a mount whose mode contradicts its kind, an unknown mount path, or a projected destination with no central grant.
4. **Resolve requirements** (`resolve_conditions()`). Each `ar:Requirement` in the universal graphs gets an `obs:ConditionEvaluation` with status `obs:Satisfied`, `obs:Unsatisfied`, or `obs:Unknown` and a reason, e.g. `cond_additional_mount_admitted` is unsatisfied when no `/workspace/extra` mount exists, and `cond_default_claude_provider` is satisfied when the provider is Claude and `/home/node/.claude` is mounted. Requirements that depend on a concrete path or a per-request decision (`cond_container_file_readable`, `cond_container_file_writable`, `cond_network_route_permitted`) stay **unknown**, never assumed satisfied; any requirement without an evaluator is also unknown.
5. **Assess** (`capabilities()`, `routes()`, `modifications()`):
   - every `ar:NativeCapability` becomes `obs:Available` (all requirements satisfied), `obs:Conditional` (some unknown), or `obs:Unavailable` (some unsatisfied), with the concrete instances it can reach. File-writing capabilities reach only read-write mounts and the writable container layer; reads reach every mount.
   - routes and management paths are assessed from observed facts: lockdown on (the container is on an internal network) blocks the direct route and host services; `cli_scope` decides which container `ncl` paths exist and whether `create_agent` needs approval.
   - what the session can change is reported in two tables. **Inside the container**: each writable location with the modeled resources residing there (minus those shadowed by a read-only mount), capabilities aimed at specific resources (mailboxes, task logs, provider settings, network, processes, subagents), and the read-only mounts as unmodifiable, each with the host path it writes through to, or "container only". **Outside the container**: host-side steps found by walking `routesToKind` from container-side tool endpoints (stopping at the delivery hub), with the entry points that trigger each, plus host-mediated management actions with their approval gates. **Outside this machine**: capabilities whose resource is on `ar:ExternalNetwork` (web fetch, shell network requests, provider web search), configured remote MCP servers, and messages delivered through a remote channel adapter to each channel destination grant. Model-provider API traffic is out of scope.
6. **Check and write.** Every `rdf:type` in the snapshot must be a kind declared in the model (or an `obs:` assessment class), otherwise it aborts. The snapshot is written as one named graph, `urn:agent-risk:snapshot:<session>:<timestamp>`, to `observations/<session>-<timestamp>.trig`.

### Reading the report

| Section | Meaning |
|---|---|
| Session snapshot | session, agent group, container, provider, `cli_scope`, lockdown, destination grants, MCP servers, gateway identity, rule count |
| Observed mounts (container view ← host source) | each mount's container path, mode, container-side kind, host path (relative to the checkout), and host-side kind |
| Requirements for this session | each requirement's status and reason |
| Native capabilities in this session | each capability's status, effects, resource kind, concrete reach, and the requirements blocking or pending it |
| Routes and management paths | network routes and container `ncl` / `create_agent` paths for this session |
| Modifiable inside the container | resource, container path, host backing (or "container only"), effects, via (shell, file tools, `send_message`, ...), status, and scope (e.g. "agent group (all its sessions)") |
| Changed outside the container, on the host | resource, host location, effects, the host step and container entry points that trigger it, status, and gate (e.g. "held for approval"); includes deliveries to local channels |
| Outside this machine (remote): reached or changed | remote resource, where, effects (reads included: the remote party sees the request), the path off the machine (container ▸ OneCLI gateway ▸ Internet, host delivery ▸ channel adapter, or provider-side search), status, and gate |
| Skills | installed container skills and whether a skill graph models them; with none, only native capabilities apply |
| Model/runtime differences | observations the model does not account for |

`Available` means nothing observed rules the effect out; it is still a may-effect, not evidence that it happened or would succeed. `Conditional` means it depends on a concrete path or a per-request gateway or remote decision.

### Limits of a snapshot

- **Live sessions only.** Mounts and network attachment are read from the running container; a session without one is rejected rather than reconstructed from configuration.
- **Point in time.** A later change (a new grant, MCP server, or mount) needs a new snapshot.
- **Display tables in the script.** Subpaths of resources inside a mount (`inbound.db`, `memory/`, `tasks/`, ...) and the effect and concrete location of each host step are listed in `materialize.py`, not the ontology.
- **Hard-coded management mapping.** The `ncl`, `create_agent`, `install_packages`, and `add_mcp_server` rows in `routes()` and `modifications()` encode NanoClaw's guard rules in the script, because the ontology states them only in comments. Update the script when those guards change.
- **Claude provider only.** Tool availability is resolved from the Claude provider's tool allowlist; other providers leave the tool requirements unknown.
- **Undeclared observation vocabulary.** `obs:` classes and properties are not yet declared in `vocabulary.ttl` or validated by SHACL; only instance types are checked.
- **Sensitive output.** Snapshots contain real session, group, and messaging identifiers, handles, and host paths. `observations/` is git-ignored; do not commit or share snapshots.

Example query over a snapshot (read-write mounts and what they expose):

```sparql
PREFIX ar:  <urn:agent-risk:>
PREFIX obs: <urn:agent-risk:observation:>
SELECT ?path ?kind WHERE {
  ?mount obs:containerPath ?path ; obs:accessMode ar:ReadWriteMountMode ; obs:exposes ?location .
  ?location a ?kind .
}
```

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
