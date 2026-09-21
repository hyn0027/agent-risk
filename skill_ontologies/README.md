# NanoClaw endpoint and resource ontologies — prototype

This directory combines two different kinds of model:

- `universal/` describes the generic resource vocabulary and the NanoClaw harness architecture that is present independently of a selected skill.
- `skills/` describes interfaces and potential effects asserted by individual `top_skills/*/SKILL.md` files, plus support graphs shared only by those skills.

The NanoClaw model was checked against local checkout commit `7902716b5b930215dbee4f56b8fb5b938d40468d`. Repository code is treated as the primary source; the [shared architecture discussion](https://chatgpt.com/s/cx_6ab168a066788191a0767199e971bbd4) was useful orientation but is not the authority when it differs from code. The model is not a statement about the live configuration of any NanoClaw installation.

All graphs use `ar: <urn:agent-risk:>`. These are local identifiers, not dereferenceable Web URLs. A published ontology should use an owned persistent HTTPS namespace.

```text
skill_ontologies/
  manifest.json          default loaded skill names only
  load-config.json       complete static set of preloaded modules
  loader.py              dependency checks, validation, inference, reports
  examples/              observation graphs for classification tests
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

## Static loading policy

`load-config.json` preloads ten modules. Five describe NanoClaw itself: core, messaging/mailboxes, management controls, container/filesystem runtime, and network/OneCLI paths. Generic tool, filesystem, internet, and shell graphs are also preloaded. Git resource definitions live under `skills/` even though the current static policy preloads them; folder placement and loading policy are separate concerns.

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

The loader discovers module graphs in `universal/*.trig` and `skills/*.trig`, and discovers skill graphs in `skills/*.trig`. Each file contains one named graph. Fixed infrastructure files remain at `universal/vocabulary.ttl`, `universal/shapes.ttl`, and `load-config.json`; this avoids duplicating their paths in a catalog.

During preflight, the loader parses graph metadata, checks that selected skills exist, verifies source hashes and the NanoClaw source revision, and requires every dependency to already be present in `load-config.json` `alwaysLoaded`. It does not add any skill graph to the active dataset until dependency preflight succeeds. A missing or unknown dependency produces a warning and aborts; dependencies are never introduced automatically.

`manifest.json` has one responsibility: default skill selection. Explicit command-line skill names replace this default.

```json
{
  "loadedSkills": ["discord", "gh-issues"]
}
```

Every always-loaded graph is checked to contain no `ar:Operation`, `ar:PotentialEffect`, `ar:declaresOperation`, or `ar:hasPotentialEffect`. `local-filesystem.trig` and `freeform-internet.trig` are additionally marked `resourcesOnly` and cannot declare invocation kinds.

## Resource and interface semantics

Resource kinds are RDF individuals typed `ar:WorldSurfaceKind`; invocation kinds are individuals typed `ar:InvocationSurfaceKind`. They are also usable as RDFS/OWL classes through OWL 2 punning.

- `ar:specializesKind`: resource **is-a** relationship.
- `ar:specializesInvocationKind`: interface/invocation **is-a** relationship.
- `ar:containsKind`: possible part or containment relationship, not subtype.
- `ar:mayBeStoredAsKind`: possible physical representation of logical state.
- `ar:sharesKind`: possible shared state scope, not containment or universal visibility.
- `ar:routesToKind`: possible mediation/dataflow step from an invocation kind.
- `ar:protectedByKind`: a security control relevant to a surface; it does not prove that the control is enabled or effective.

Multiple parents are allowed. The loader projects specialization edges into `rdfs:subClassOf` only in its separate OWL reasoning graph. It rejects hierarchy cycles and validates the type of every relationship endpoint.

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

## Qualified subtype definitions

Every specialization edge is a necessary-only definition. A kind becomes necessary-and-sufficient only with `owl:equivalentClass`; the loader then requires a corresponding SHACL target shape.

`skills/git-resources.trig` demonstrates the pattern without falsely defining every Git repository as a directory containing `.git`:

- `GitMetadataEntryCandidate`: exactly an entry named `.git`.
- `ConventionalGitWorkingTreeCandidate`: exactly a local directory containing such an entry.
- `ConventionalGitWorkingTree`: candidate plus explicit `gitRepositoryValidated true` evidence.
- `LocalGitRepository`: primitive broader kind because bare repositories, linked worktrees, and external Git directories need not contain a `.git` entry.

OWL-RL performs positive open-world inference. SHACL separately requires evidence for asserted or inferred observations. Missing facts do not prove non-membership.

## Run and validate

Install `rdflib`, `owlrl`, and `pyshacl`, then:

```bash
python loader.py --universal-only
python loader.py discord gh-issues
python loader.py coding-agent --data examples/git-working-tree.ttl
```

The old `--resources-only` and `--baseline-only` spellings remain aliases for `--universal-only`. With no arguments, the loader uses `manifest.json` `loadedSkills`; explicit skill arguments override that list.

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

# Possible NanoClaw mediation chain from a concrete endpoint.
SELECT ?next WHERE {
  ar:NanoClawSendMessageTool ar:routesToKind+ ?next .
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
