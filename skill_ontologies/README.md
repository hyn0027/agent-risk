# NanoClaw endpoint and resource ontologies — prototype

This directory combines two different kinds of model:

- `universal/` describes the generic resource vocabulary and the NanoClaw harness architecture that is present independently of a selected skill.
- `skills/` describes interfaces and potential effects asserted by individual `top_skills/*/SKILL.md` files, plus support graphs shared only by those skills.

The NanoClaw model was checked against local checkout commit `7902716b5b930215dbee4f56b8fb5b938d40468d`. Repository code is treated as the primary source; the [shared architecture discussion](https://chatgpt.com/s/cx_6ab168a066788191a0767199e971bbd4) was useful orientation but is not the authority when it differs from code. The model is not a statement about the live configuration of any NanoClaw installation.

All graphs use `ar: <urn:agent-risk:>`. These are local identifiers, not dereferenceable Web URLs. A published ontology should use an owned persistent HTTPS namespace.

```text
skill_ontologies/
  manifest.json          graph catalog, source revision, and dependencies
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
    openclaw-skill-surfaces.trig
    ...one graph per skill...
```

## Static loading policy

`load-config.json` preloads eleven modules. Five describe NanoClaw itself: core, messaging/mailboxes, management controls, container/filesystem runtime, and network/OneCLI paths. Generic tool, filesystem, internet, and shell graphs are also preloaded. Git resource definitions and the legacy OpenClaw skill-interface vocabulary live under `skills/` even though the current static policy preloads them; folder placement and loading policy are separate concerns.

Dependencies never load dynamically. Before parsing any named graph, the loader verifies that every declared dependency is already in `alwaysLoaded`. A missing dependency produces a warning and aborts with no ontology graphs loaded.

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

`send_message`, `send_file`, `edit_message`, `add_reaction`, `ask_user_question`, and `send_card` are separate endpoint kinds. This matters because NanoClaw does not expose one universal OpenClaw-style `message` action with all read, search, delete, poll, pin, presence, and channel-management operations.

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

## OpenClaw skill compatibility

Some source skills explicitly require OpenClaw interfaces. Their shared types now live in `skills/openclaw-skill-surfaces.trig`, not `universal/`:

- OpenClaw broad `message` tool;
- `openclaw message` and configuration CLIs;
- OpenClaw channel plugin/adapter;
- OpenClaw TaskFlow runtime and configuration.

Loading this compatibility graph preserves what the source says. It does **not** claim NanoClaw implements those interfaces. For example, the Discord skill's read/search/delete/poll/pin/presence actions cannot honestly be mapped to NanoClaw's narrower built-in messaging MCP without an additional adapter, MCP server, or rewritten skill.

The loader's `Messaging-route` column recognizes both NanoClaw and legacy messaging interfaces through their common messaging ancestor. `NanoClaw-mailbox` is stricter: it is `yes` only when the operation's declared invocation route actually reaches a NanoClaw mailbox write/read stage. The current OpenClaw-native skills therefore show a messaging route but no NanoClaw-mailbox route. That is a compatibility warning, not a validation error.

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

The old `--resources-only` and `--baseline-only` spellings remain aliases for `--universal-only`. No arguments select `discord` and `gh-issues`, matching the original prototype behavior.

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
```

Do not merge subtype, containment, route, and protection edges into one undifferentiated reachability relation. A file inside a directory is not a kind of directory; a route protected by a policy is not proof the policy allows it; a possible path is not proof that credentials and permissions make it executable.

## Limits

This is a manually reviewed architecture model, not a complete code audit or deployed inventory. It does not observe installed channel adapters, live users or roles, actual mount paths, filesystem modes, container network membership, OneCLI policies, credentials, provider tool inventories, or remote MCP behavior. The repository documentation itself warns that some design documents can drift; stable source links in the graph pin the inspected commit, but later NanoClaw revisions require re-review.

Most kinds are primitive because the code does not provide reliable necessary-and-sufficient recognition facts in RDF form. `routesToKind` is an over-approximation of possible mediation, not temporal semantics or guaranteed transitive execution. Inferring which resources can actually change still requires concrete tool availability, arguments, identity, authority, configuration, current state, and policy decisions. Generic shell execution and delegated workers remain open-ended.
