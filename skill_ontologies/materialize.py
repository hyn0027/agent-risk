"""Instantiate the universal NanoClaw ontology for one concrete, running session.

Collects facts about a session from NanoClaw's own interfaces (host `ncl`, the
session's mailbox files, `docker inspect`, the OneCLI CLI, and the checkout's
directories), writes them as typed instances in a timestamped snapshot graph,
resolves the universal model's requirements for that session, and reports
which native capabilities and routes remain possible.

    python3 materialize.py                      # the most recently active running session
    python3 materialize.py --session <id>
    python3 materialize.py --no-write           # report only

Snapshots land in observations/ (git-ignored): they contain real identifiers,
handles, and paths. Secret values, tokens, and environment values are never
collected. Results are still may-claims: a capability marked available means
nothing observed rules it out, not that it was exercised or will succeed.
"""

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from rdflib import BNode, Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from table_output import print_table

ROOT = Path(__file__).resolve().parent
AR = Namespace("urn:agent-risk:")
OBS = Namespace("urn:agent-risk:observation:")

SATISFIED, UNSATISFIED, UNKNOWN = OBS.Satisfied, OBS.Unsatisfied, OBS.Unknown
OBSERVED, FROM_CONFIG = OBS.Observed, OBS.FromConfiguration


# Channel adapters that deliver to a client on this machine rather than a remote platform.
LOCAL_CHANNELS = {"cli", "emacs"}

# Claude provider tool names (container/agent-runner/src/providers/claude-config.ts TOOL_ALLOWLIST).
CLAUDE_FILE_TOOLS = {"Read", "Write", "Edit", "Glob", "Grep", "NotebookEdit"}
CLAUDE_WEB_TOOLS = {"WebFetch", "WebSearch"}
CLAUDE_SUBAGENT_TOOLS = {"Task"}


# ── collection ───────────────────────────────────────────────────────────────


def run(argv: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(argv, cwd=cwd, check=True, capture_output=True, text=True, timeout=60).stdout


def ncl(nanoclaw: Path, *args: str) -> object:
    out = json.loads(run([str(nanoclaw / "bin" / "ncl"), *args, "--json"], cwd=nanoclaw))
    if not out.get("ok"):
        raise SystemExit(f"ncl {' '.join(args)} failed: {out.get('error')}")
    return out["data"]


def tool(name: str) -> str:
    """Resolve a CLI from PATH, falling back to ~/.local/bin where NanoClaw setup installs it."""
    found = shutil.which(name) or shutil.which(name, path=str(Path.home() / ".local" / "bin"))
    if not found:
        raise SystemExit(f"'{name}' not found on PATH or in ~/.local/bin.")
    return found


def onecli(*args: str) -> object:
    return json.loads(run([tool("onecli"), *args])).get("data", [])


def sqlite_rows(path: Path, sql: str) -> list[dict]:
    if not path.exists():
        return []
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in con.execute(sql)]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def collect(nanoclaw: Path, session_id: str | None) -> dict:
    sessions = ncl(nanoclaw, "sessions", "list")
    running = sorted(
        (s for s in sessions if s["container_status"] == "running"),
        key=lambda s: s["last_active"] or "",
        reverse=True,
    )
    if session_id is None:
        if not running:
            raise SystemExit("No running session. Start one (send the agent a message) or pass --session.")
        session = running[0]
    else:
        session = next((s for s in sessions if s["id"] == session_id), None)
        if session is None:
            raise SystemExit(f"Unknown session {session_id}")
    group_id = session["agent_group_id"]

    containers = run([tool("docker"), "ps", "--format", "{{.Names}}"]).split()
    container_name = next((n for n in containers if n.endswith(session["id"])), None)
    if container_name is None:
        raise SystemExit(f"Session {session['id']} has no running container; this collector only reads live sessions.")
    inspect = json.loads(run([tool("docker"), "inspect", container_name]))[0]
    networks = {}
    for name in inspect["NetworkSettings"]["Networks"]:
        net = json.loads(run([tool("docker"), "network", "inspect", name]))[0]
        networks[name] = {
            "internal": bool(net.get("Internal")),
            "members": sorted(c["Name"] for c in net.get("Containers", {}).values()),
        }
    try:
        curl = run([tool("docker"), "exec", container_name, "sh", "-c", "command -v curl || true"]).strip()
    except subprocess.CalledProcessError:
        curl = ""

    group = next(g for g in ncl(nanoclaw, "groups", "list") if g["id"] == group_id)
    session_dir = nanoclaw / "data" / "v2-sessions" / group_id / session["id"]
    agents = [
        {k: a.get(k) for k in ("id", "name", "identifier", "secretMode")}  # never the access token
        for a in onecli("agents", "list")
    ]
    return {
        "session": session,
        "group": group,
        "config": ncl(nanoclaw, "groups", "config", "get", "--id", group_id),
        "group_sessions": [s for s in sessions if s["agent_group_id"] == group_id],
        "messaging_groups": ncl(nanoclaw, "messaging-groups", "list"),
        "wirings": [w for w in ncl(nanoclaw, "wirings", "list") if w["agent_group_id"] == group_id],
        "grants": [d for d in ncl(nanoclaw, "destinations", "list") if d["agent_group_id"] == group_id],
        "roles": ncl(nanoclaw, "roles", "list"),
        "members": [m for m in ncl(nanoclaw, "members", "list") if m.get("agent_group_id") == group_id],
        "projected": sqlite_rows(session_dir / "inbound.db", "SELECT name, type, channel_type, platform_id, agent_group_id FROM destinations"),
        "container_name": container_name,
        "inspect": inspect,
        "networks": networks,
        "curl": curl,
        "onecli_agent": next((a for a in agents if a["identifier"] == group_id), None),
        "secrets": [{k: s.get(k) for k in ("name", "type", "hostPattern")} for s in onecli("secrets", "list")],
        "rules": [{k: r.get(k) for k in ("name", "action", "hostPattern", "agentId", "enabled")} for r in onecli("rules", "list")],
        "container_skills": sorted(p.name for p in (nanoclaw / "container" / "skills").iterdir() if p.is_dir()),
        "a2a_installed": (nanoclaw / "src" / "modules" / "agent-to-agent").is_dir(),
        "nanoclaw_head": run([tool("git"), "-C", str(nanoclaw), "rev-parse", "HEAD"]).strip(),
        "nanoclaw_root": nanoclaw.resolve(),
    }


# ── model ────────────────────────────────────────────────────────────────────


def load_model() -> Graph:
    model = Graph()
    model.parse(ROOT / "universal" / "vocabulary.ttl", format="turtle")
    for path in sorted((ROOT / "universal").glob("*.trig")):
        for graph in Dataset().parse(path, format="trig").graphs():
            for triple in graph:
                model.add(triple)
    return model


def skill_directories() -> dict[str, Path]:
    found = {}
    for path in sorted((ROOT / "skills").glob("*.trig")):
        match = re.search(r'ar:skillDirectory "([^"]+)"', path.read_text())
        if match:
            found[match.group(1)] = path
    return found


def short(node: URIRef) -> str:
    text = str(node)
    return text.rsplit(":", 1)[-1] if text.startswith("urn:agent-risk:") else text


# ── instantiation ────────────────────────────────────────────────────────────


class Snapshot:
    def __init__(self, facts: dict, model: Graph, taken_at: str) -> None:
        self.facts, self.model = facts, model
        sid = facts["session"]["id"]
        stamp = taken_at.replace(":", "").replace("-", "").replace(".", "")
        self.inst = Namespace(f"urn:agent-risk:instance:{sid}:{stamp}:")
        self.graph = Graph(identifier=URIRef(f"urn:agent-risk:snapshot:{sid}:{stamp}"))
        self.graph.bind("ar", AR)
        self.graph.bind("obs", OBS)
        self.graph.bind("inst", self.inst)
        self.taken_at = taken_at
        self.conditions: dict[URIRef, tuple[URIRef, str]] = {}
        self.findings: list[str] = []

    def mount_kind(self, dest: str, rw: bool) -> URIRef | None:
        """Most specific mount kind whose modeled containerPath matches (trailing * = prefix)."""
        best: tuple[int, URIRef] | None = None
        for kind, path in self.model.subject_objects(AR.containerPath):
            path = str(path)
            hit = dest.startswith(path[:-1]) if path.endswith("*") else dest == path
            modes = set(self.model.objects(kind, AR.mountAccessMode))
            if hit and (not modes or (AR.ReadWriteMountMode if rw else AR.ReadOnlyMountMode) in modes):
                if best is None or len(path) > best[0]:
                    best = (len(path), kind)
        return best[1] if best else None

    def host_path(self, path: str | None) -> str | None:
        """Host path relative to the NanoClaw checkout when inside it."""
        if not path:
            return None
        root = str(self.facts["nanoclaw_root"]).rstrip("/") + "/"
        return path[len(root):] if path.startswith(root) else path

    def node(self, local: str) -> URIRef:
        return self.inst[re.sub(r"[^A-Za-z0-9_.-]", "_", local)]

    def add(self, node: URIRef, kind: URIRef, evidence: URIRef, label: str, **props: object) -> URIRef:
        g = self.graph
        g.add((node, RDF.type, kind))
        g.add((node, RDFS.label, Literal(label)))
        g.add((node, OBS.evidenceKind, evidence))
        for key, value in props.items():
            values = value if isinstance(value, list) else [value]
            for item in values:
                if item is None:
                    continue
                obj = item if isinstance(item, (URIRef, BNode, Literal)) else Literal(item)
                g.add((node, OBS[key], obj))
        return node

    def build(self) -> None:
        f, g = self.facts, self.graph
        sess, group, config, inspect = f["session"], f["group"], f["config"], f["inspect"]
        host = inspect["HostConfig"]

        snap = self.node("snapshot")
        self.add(snap, OBS.Snapshot, OBSERVED, f"Snapshot of {sess['id']}", takenAt=Literal(self.taken_at, datatype=XSD.dateTime), nanoclawRevision=f["nanoclaw_head"])

        grp = self.add(self.node(f"group_{group['id']}"), AR.NanoClawAgentGroup, FROM_CONFIG, group["name"], identifier=group["id"], folder=group.get("folder"), cliScope=config.get("cli_scope") or "group")
        session = self.add(self.node(f"session_{sess['id']}"), AR.NanoClawSession, FROM_CONFIG, sess["id"], identifier=sess["id"], inAgentGroup=grp, containerStatus=sess["container_status"])
        g.add((snap, OBS.ofSession, session))
        for other in f["group_sessions"]:
            if other["id"] != sess["id"]:
                peer = self.add(self.node(f"session_{other['id']}"), AR.NanoClawSession, FROM_CONFIG, other["id"], identifier=other["id"], inAgentGroup=grp, containerStatus=other["container_status"])
                g.add((session, OBS.sharesGroupStateWith, peer))

        mgs = {m["id"]: m for m in f["messaging_groups"]}
        origin = mgs.get(sess.get("messaging_group_id"))
        if origin:
            mg = self.add(self.node(f"mg_{origin['id']}"), AR.MessagingGroup, FROM_CONFIG, origin["name"] or origin["id"], identifier=origin["id"], channelType=origin["channel_type"], unknownSenderPolicy=origin["unknown_sender_policy"])
            g.add((session, OBS.originChat, mg))
        for w in f["wirings"]:
            target = mgs.get(w["messaging_group_id"], {})
            self.add(self.node(f"wiring_{w['id']}"), AR.NanoClawWiring, FROM_CONFIG, f"{target.get('name')} → {group['name']}", identifier=w["id"], wiresAgentGroup=grp, wiresMessagingGroup=self.node(f"mg_{w['messaging_group_id']}"), engageMode=w["engage_mode"], senderScope=w["sender_scope"])

        for d in f["grants"]:
            grant = self.add(self.node(f"grant_{d['local_name']}"), AR.NanoClawDestinationGrant, FROM_CONFIG, d["local_name"], localName=d["local_name"], targetType=d["target_type"], targetId=d["target_id"], channelType=d.get("channel_type"), heldBy=grp)
            g.add((session, OBS.mayAddress, grant))
        for d in f["projected"]:
            self.add(self.node(f"projected_{d['name']}"), AR.NanoClawProjectedDestination, OBSERVED, d["name"], localName=d["name"], inSession=session, projectionOf=self.node(f"grant_{d['name']}"))
        granted = {d["local_name"] for d in f["grants"]}
        for d in f["projected"]:
            if d["name"] not in granted:
                self.findings.append(f"Projected destination '{d['name']}' has no central grant (stale projection; it authorizes nothing).")

        container = self.add(self.node(f"container_{f['container_name']}"), AR.NanoClawAgentContainer, OBSERVED, f["container_name"], servesSession=session, image=inspect["Config"]["Image"], runsAsUser=inspect["Config"].get("User") or "image default", readOnlyRootFs=bool(host.get("ReadonlyRootfs")))
        self.add(self.node("image"), AR.NanoClawAgentImage, OBSERVED, inspect["Config"]["Image"], usedBy=container, perGroupImage=bool(config.get("image_tag")))

        # Mounts: each is a container-side location bound from a separate host-side location.
        g.add((container, OBS.onSide, AR.NanoClawAgentContainer))
        for m in inspect["Mounts"]:
            dest, rw, source = m["Destination"], bool(m["RW"]), m.get("Source")
            kind = self.mount_kind(dest, rw)
            if kind is None:
                kind = AR.NanoClawMount
                self.findings.append(f"Mount {dest} matches no modeled mount kind.")
            mode = AR.ReadWriteMountMode if rw else AR.ReadOnlyMountMode
            mount = self.add(self.node(f"mount{dest}"), kind, OBSERVED, dest, containerPath=dest, hostPath=self.host_path(source), accessMode=mode, mountedIn=container)
            modeled = set(self.model.objects(kind, AR.mountAccessMode))
            if modeled and mode not in modeled:
                self.findings.append(f"Mount {dest} is {short(mode)} but {short(kind)} is modeled as {', '.join(short(x) for x in modeled)}.")
            exposed_kinds = list(self.model.objects(kind, AR.mountExposesKind))
            if kind == AR.OneCLIFileMount:
                exposed_kinds = [AR.OneCLICACertificate if "-ca" in dest or dest.endswith(".pem") else AR.OneCLICredentialStub]
            for exposed in exposed_kinds:
                location = self.add(self.node(f"location{dest}_{short(exposed)}"), exposed, OBSERVED, f"{dest} ({short(exposed)})", containerPath=dest, onSide=AR.NanoClawAgentContainer)
                g.add((mount, OBS.exposes, location))
            for host_kind in self.model.objects(kind, AR.bindsFromKind):
                backing = self.add(self.node(f"host{source}"), host_kind, OBSERVED, self.host_path(source), hostPath=self.host_path(source), onSide=AR.NanoClawHostProcess)
                g.add((mount, OBS.bindsFrom, backing))
                for location in self.graph.objects(mount, OBS.exposes):
                    g.add((location, OBS.backedBy, backing))

        # Session mailbox files (in the session workspace mount).
        if "/workspace" in {m["Destination"] for m in inspect["Mounts"]}:
            for kind, name in ((AR.NanoClawInboundMailbox, "inbound.db"), (AR.NanoClawOutboundMailbox, "outbound.db")):
                ws = next(m for m in inspect["Mounts"] if m["Destination"] == "/workspace")
                self.add(self.node(f"mailbox_{name}"), kind, FROM_CONFIG, f"/workspace/{name}", containerPath=f"/workspace/{name}", hostPath=f"{self.host_path(ws.get('Source'))}/{name}", inSession=session)

        # Network and controls.
        nets = f["networks"]
        lockdown_on = any(n["internal"] for n in nets.values())
        for name, net in nets.items():
            self.add(self.node(f"network_{name}"), AR.NanoClawInternalEgressNetwork if net["internal"] else AR.RemoteNetworkEndpoint, OBSERVED, name, attaches=container, internal=net["internal"], memberCount=len(net["members"]))
        self.add(self.node("control_lockdown"), AR.NanoClawEgressLockdownControl, OBSERVED, "egress lockdown", enabled=lockdown_on, appliesTo=container)
        self.add(self.node("control_isolation"), AR.NanoClawContainerIsolationControl, OBSERVED, "container isolation", capDrop=host.get("CapDrop") or [], securityOpt=host.get("SecurityOpt") or [], init=bool(host.get("Init")), appliesTo=container)
        self.add(self.node("control_limits"), AR.NanoClawResourceLimitControl, OBSERVED, "resource limits", pidsLimit=host.get("PidsLimit") or 0, memoryBytes=host.get("Memory") or 0, nanoCpus=host.get("NanoCpus") or 0, shmBytes=host.get("ShmSize") or 0, appliesTo=container)
        self.add(self.node("control_cli_scope"), AR.NanoClawCLIScopeControl, FROM_CONFIG, "cli scope", value=config.get("cli_scope") or "group", appliesTo=grp)
        self.add(self.node("control_destination_acl"), AR.NanoClawDestinationACL, FROM_CONFIG, "destination ACL", enforced=f["a2a_installed"], appliesTo=grp)
        self.add(self.node("control_tool_policy"), AR.NanoClawProviderToolPolicyControl, FROM_CONFIG, "provider tool policy", permissionMode="bypassPermissions", appliesTo=container)
        if origin:
            self.add(self.node("control_user_access"), AR.NanoClawUserAccessControl, FROM_CONFIG, "sender admission", unknownSenderPolicy=origin["unknown_sender_policy"], appliesTo=self.node(f"mg_{origin['id']}"))
        if f["roles"] or f["members"]:
            self.add(self.node("roles"), AR.NanoClawRoleMembershipState, FROM_CONFIG, "roles and members", ownerCount=sum(r["role"] == "owner" for r in f["roles"]), adminCount=sum(r["role"] == "admin" for r in f["roles"]), memberCount=len(f["members"]))

        # Gateway.
        agent = f["onecli_agent"]
        if agent:
            identity = self.add(self.node("onecli_identity"), AR.OneCLIAgentIdentity, OBSERVED, agent["name"] or agent["identifier"], identifier=agent["identifier"], secretMode=agent.get("secretMode"), identifies=grp)
            for s in f["secrets"]:
                self.add(self.node(f"secret_{s['name']}"), AR.Credential, OBSERVED, s["name"], hostPattern=s.get("hostPattern"), secretType=s.get("type"), injectableFor=identity if agent.get("secretMode") == "all" else None)
            scoped = [r for r in f["rules"] if not r.get("agentId") or r.get("agentId") == agent["id"]]
            self.add(self.node("control_gateway_policy"), AR.OneCLIGatewayPolicy, OBSERVED, "gateway policy", ruleCount=len(scoped), appliesTo=identity)

        # MCP servers configured for the group (names and transport only).
        for name, spec in (config.get("mcp_servers") or {}).items():
            remote = isinstance(spec, dict) and bool(spec.get("url"))
            self.add(self.node(f"mcp_{name}"), AR.RemoteMCPService if remote else AR.LocalMCPServerProcess, FROM_CONFIG, name, transport="http" if remote else "stdio", configuredFor=grp)

        self.resolve_conditions(lockdown_on)

    # ── condition resolution ──

    def resolve_conditions(self, lockdown_on: bool) -> None:
        f, config = self.facts, self.facts["config"]
        mounts = {m["Destination"]: bool(m["RW"]) for m in f["inspect"]["Mounts"]}
        provider = (config.get("provider") or f["session"].get("agent_provider") or "claude").lower()
        claude = provider == "claude"
        extras = [d for d in mounts if d.startswith("/workspace/extra/")]

        def set_(cond: str, status: URIRef, reason: str) -> None:
            self.conditions[AR[cond]] = (status, reason)

        set_("cond_default_claude_provider", SATISFIED if claude and "/home/node/.claude" in mounts else UNSATISFIED, f"provider={provider}; /home/node/.claude {'mounted' if '/home/node/.claude' in mounts else 'not mounted'}")
        set_("cond_provider_file_tool_available", SATISFIED if claude else UNKNOWN, "Claude allowlist includes Read/Write/Edit/Glob/Grep" if claude else f"provider {provider} not modeled")
        set_("cond_container_shell_available", SATISFIED if claude else UNKNOWN, "Claude allowlist includes Bash" if claude else f"provider {provider} not modeled")
        set_("cond_provider_web_tool_available", SATISFIED if claude else UNKNOWN, "Claude allowlist includes WebFetch/WebSearch" if claude else f"provider {provider} not modeled")
        set_("cond_provider_subagent_tool_available", SATISFIED if claude else UNKNOWN, "Claude allowlist includes Task" if claude else f"provider {provider} not modeled")
        set_("cond_builtin_messaging_tool_available", SATISFIED, "built-in nanoclaw MCP server is always registered")
        set_("cond_shared_skills_exist", SATISFIED if "/app/skills" in mounts else UNSATISFIED, "/app/skills mount " + ("present" if "/app/skills" in mounts else "absent"))
        set_("cond_container_config_exists", SATISFIED if "/workspace/agent/container.json" in mounts else UNSATISFIED, "container.json mount " + ("present" if "/workspace/agent/container.json" in mounts else "absent"))
        set_("cond_standing_instructions_composed", SATISFIED if "/workspace/agent/CLAUDE.md" in mounts else UNSATISFIED, "CLAUDE.md mount " + ("present" if "/workspace/agent/CLAUDE.md" in mounts else "absent"))
        set_("cond_additional_mount_admitted", SATISFIED if extras else UNSATISFIED, f"{len(extras)} /workspace/extra mounts observed")
        set_("cond_additional_mount_readwrite", SATISFIED if any(mounts[d] for d in extras) else UNSATISFIED, "no read-write extra mount" if not any(mounts[d] for d in extras) else "a read-write extra mount is present")
        set_("cond_onecli_files_contributed", SATISFIED if any("onecli" in d for d in mounts) else UNSATISFIED, "OneCLI CA mounts " + ("present" if any("onecli" in d for d in mounts) else "absent"))
        set_("cond_network_client_available", SATISFIED if f["curl"] else UNKNOWN, f"curl at {f['curl']}" if f["curl"] else "no curl found; other clients may exist")
        has_route = bool(f["grants"]) or bool(f["session"].get("messaging_group_id"))
        set_("cond_destination_projected_and_authorized", SATISFIED if has_route else UNSATISFIED, f"{len(f['grants'])} destination grant(s); origin chat {'present' if f['session'].get('messaging_group_id') else 'absent'}")
        set_("cond_network_route_permitted", UNKNOWN, ("lockdown on: only gateway-proxied requests can leave; " if lockdown_on else "lockdown off: direct and proxied routes exist; ") + "per-request gateway and remote decisions are not observable")
        set_("cond_container_file_readable", UNKNOWN, "depends on the concrete path")
        set_("cond_container_file_writable", UNKNOWN, "depends on the concrete path; see mount modes")

        for cond in sorted(set(self.model.subjects(RDF.type, AR.Requirement))):
            if cond not in self.conditions:
                self.conditions[cond] = (UNKNOWN, "no evaluator for this requirement")
        for cond, (status, reason) in self.conditions.items():
            ev = self.node(f"eval_{short(cond)}")
            self.add(ev, OBS.ConditionEvaluation, OBSERVED, short(cond), evaluates=cond, status=status, reason=reason)

    # ── assessment ──

    def capabilities(self) -> list[dict]:
        rows = []
        self.cap_status: dict[URIRef, URIRef] = {}
        for cap in sorted(set(self.model.subjects(RDF.type, AR.NativeCapability))):
            reqs = sorted(self.model.objects(cap, AR.nativeRequires))
            statuses = {r: self.conditions.get(r, (UNKNOWN, ""))[0] for r in reqs}
            blocked = [r for r, s in statuses.items() if s == UNSATISFIED]
            open_ = [r for r, s in statuses.items() if s == UNKNOWN]
            status = OBS.Unavailable if blocked else OBS.Conditional if open_ else OBS.Available
            self.cap_status[cap] = status
            scope = self.capability_scope(cap)
            node = self.node(f"capability_{short(cap)}")
            self.add(node, OBS.CapabilityAssessment, OBSERVED, short(cap), capability=cap, status=status, blockedBy=blocked, pendingOn=open_, scopedTo=[s for s, _ in scope])
            rows.append({
                "capability": short(cap),
                "status": short(status),
                "effect": ", ".join(short(e) for e in sorted(self.model.objects(cap, AR.nativeEffectType))),
                "resource": short(next(self.model.objects(cap, AR.nativeResourceKind))),
                "why": "; ".join([f"blocked: {short(r)}" for r in blocked] + [f"pending: {short(r)}" for r in open_]) or "all requirements satisfied",
                "scope": ", ".join(label for _, label in scope) or "-",
            })
        return rows

    def capability_scope(self, cap: URIRef) -> list[tuple[URIRef, str]]:
        """Concrete instances a capability can reach in this session."""
        scope_kind = next(self.model.objects(cap, AR.nativeScopeKind), None)
        if short(cap) == "NativeMessageDelivery":
            return [(self.node(f"grant_{d['local_name']}"), f"{d['local_name']} ({d['target_type']}:{d.get('channel_type') or d['target_id']})") for d in self.facts["grants"]]
        hits = [(s, str(self.graph.value(s, RDFS.label))) for s in self.graph.subjects(RDF.type, scope_kind)] if scope_kind else []
        if hits:
            return hits
        if scope_kind == AR.NanoClawContainerFileSystem:
            effects = set(self.model.objects(cap, AR.nativeEffectType))
            writes = bool(effects & {AR.Create, AR.Update, AR.Delete})
            mounts = [m for m in self.facts["inspect"]["Mounts"] if m["RW"] or not writes]
            reach = [(self.node(f"mount{m['Destination']}"), f"{m['Destination']} ({'rw' if m['RW'] else 'ro'})") for m in sorted(mounts, key=lambda m: m["Destination"])]
            if writes and not self.facts["inspect"]["HostConfig"].get("ReadonlyRootfs"):
                layer = self.add(self.node("container_layer"), AR.NanoClawContainerLayer, OBSERVED, "container layer (writable, discarded with the container)")
                reach.append((layer, "container layer (writable, ephemeral)"))
            return reach
        return []

    # Display subpaths for modeled resources inside a mounted location.
    SUBPATHS = {
        AR.NanoClawInboundMailbox: "inbound.db",
        AR.NanoClawOutboundMailbox: "outbound.db",
        AR.NanoClawInboxArtifact: "inbox/",
        AR.NanoClawOutboxArtifact: "outbox/",
        AR.NanoClawConversationArchive: "conversations/",
        AR.NanoClawPersistentMemory: "memory/",
        AR.NanoClawTaskRunLog: "tasks/",
        AR.NanoClawConversationContinuation: "projects/",
    }

    def side_of(self, kind: URIRef) -> URIRef | None:
        """executesOn / locatedOn, inherited along the specialization hierarchy."""
        seen, todo = set(), [kind]
        while todo:
            k = todo.pop()
            if k in seen:
                continue
            seen.add(k)
            side = self.model.value(k, AR.executesOn) or self.model.value(k, AR.locatedOn)
            if side is not None:
                return side
            todo.extend(self.model.objects(k, AR.specializesInvocationKind))
            todo.extend(self.model.objects(k, AR.specializesKind))
        return None

    def modifications(self, lockdown_on: bool) -> tuple[list[tuple], list[tuple], list[tuple]]:
        """What this session can change, split by where the change happens.

        Returns (inside, outside, remote):
          inside  rows (resource, container path, host backing, effects, via, status, scope)
          outside rows (resource, host location, effects, triggered by, status, gate)
          remote  rows (resource, remote location, effects, path off the machine, status, gate)
        Inside rows come from native capabilities and observed mounts; a write
        through a bind mount also changes the listed host backing. Outside rows are
        host-side steps reachable from a container entry point along routesToKind,
        plus host-mediated management actions. Call capabilities() first.
        """
        m, f = self.model, self.facts
        mutating = {AR.Create, AR.Update, AR.Delete, AR.Configure, AR.Transmit, AR.Execute, AR.Delegate, AR.Install}
        rank = {OBS.Available: 0, OBS.Conditional: 1, OBS.Unavailable: 2}
        persistence = {
            AR.NanoClawSessionWorkspace: "this session",
            AR.NanoClawAgentGroupWorkspace: "agent group (all its sessions)",
            AR.NanoClawProviderStateDirectory: "agent group (all its sessions)",
            AR.NanoClawContainerLayer: "ephemeral (discarded with the container)",
        }
        endpoint_names = {
            AR.NanoClawContainerShellExecution: "shell",
            AR.NanoClawProviderFileTool: "file tools",
            AR.NanoClawSendMessageTool: "send_message",
            AR.NanoClawSendFileTool: "send_file",
            AR.NanoClawProviderSubagentTool: "subagent tool",
            AR.NanoClawProviderWebFetchTool: "web fetch",
            AR.NanoClawProviderWebSearchTool: "web search",
        }
        container_only = "— (container only)"
        mounts = sorted(f["inspect"]["Mounts"], key=lambda x: x["Destination"])

        def caps_where(pred):
            out = []
            for cap, status in self.cap_status.items():
                effects = set(m.objects(cap, AR.nativeEffectType)) & mutating
                if effects and status != OBS.Unavailable and pred(cap):
                    out.append((cap, status, effects))
            return out

        def merge(items):
            effects = sorted({short(e) for _, _, es in items for e in es})
            via = sorted({endpoint_names.get(m.value(c, AR.nativeEndpointKind), short(m.value(c, AR.nativeEndpointKind))) for c, _, _ in items})
            status = min((st for _, st, _ in items), key=lambda st: rank[st])
            return ", ".join(effects), ", ".join(via), short(status)

        def backing(dest: str) -> str:
            mnt = next((x for x in mounts if x["Destination"] == dest), None)
            return self.host_path(mnt.get("Source")) if mnt else container_only

        inside: list[tuple] = []
        # 1. Writable container locations and the modeled resources inside them.
        fs_caps = caps_where(lambda c: m.value(c, AR.nativeScopeKind) == AR.NanoClawContainerFileSystem)
        ro_kinds, locations = set(), []
        for mnt in mounts:
            exposed = [self.graph.value(loc, RDF.type) for loc in self.graph.objects(self.node(f"mount{mnt['Destination']}"), OBS.exposes)]
            for kind in exposed:
                nested = any(other in m.objects(kind, AR.mayResideInKind) for other in exposed if other != kind)
                if mnt["RW"] and not nested:
                    locations.append((kind, mnt["Destination"]))
                elif not mnt["RW"]:
                    ro_kinds.add(kind)
        if not f["inspect"]["HostConfig"].get("ReadonlyRootfs"):
            locations.append((AR.NanoClawContainerLayer, None))
        if fs_caps:
            effects, via, status = merge(fs_caps)
            for kind, dest in locations:
                cpath = dest or "/ (writable layer: /tmp, /home/node, ...)"
                hpath = backing(dest) if dest else container_only
                inside.append((short(kind), cpath, hpath, effects, via, status, persistence.get(kind, "-")))
                for sub in sorted(m.subjects(AR.mayResideInKind, kind)):
                    if sub in ro_kinds or (sub, RDF.type, AR.WorldSurfaceKind) not in m:
                        continue
                    tail = self.SUBPATHS.get(sub, "")
                    sub_c = f"{dest}/{tail}" if dest and tail else cpath
                    sub_h = f"{hpath}/{tail}" if dest and tail else hpath
                    inside.append((f"└ {short(sub)}", sub_c, sub_h, effects, via, status, persistence.get(kind, "-")))

        # 2. Capabilities aimed at a specific resource, except delivery (a host-side step).
        specific = caps_where(lambda c: m.value(c, AR.nativeScopeKind) != AR.NanoClawContainerFileSystem
                              and m.value(c, AR.nativeResourceKind) != AR.NanoClawDestinationGrant
                              and self.side_of(m.value(c, AR.nativeResourceKind)) != AR.ExternalNetwork)
        grouped: dict[URIRef, list] = {}
        for item in specific:
            grouped.setdefault(m.value(item[0], AR.nativeResourceKind), []).append(item)
        known_paths = {
            AR.NanoClawInboundMailbox: "/workspace/inbound.db",
            AR.NanoClawOutboundMessage: "/workspace/outbound.db",
            AR.NanoClawProviderStateDirectory: "/home/node/.claude",
            AR.NanoClawTaskRunLog: "/workspace/agent/tasks/",
        }
        gates = {
            AR.NanoClawOutboundMessage: "host delivery and action guards decide",
            AR.NanoClawProviderStateDirectory: "affects later sessions of the group",
            AR.NanoClawInboundMailbox: "projected destinations grant nothing",
            AR.RemoteNetworkEndpoint: "leaves via the OneCLI gateway only (lockdown on)" if lockdown_on else "gateway or direct (lockdown off)",
        }
        for kind, items in sorted(grouped.items(), key=lambda kv: short(kv[0])):
            effects, via, status = merge(items)
            cpath = known_paths.get(kind)
            if cpath:
                parent = max((x["Destination"] for x in mounts if cpath.startswith(x["Destination"])), key=len, default=None)
                hpath = f"{backing(parent)}{cpath[len(parent):]}" if parent else container_only
            else:
                cpath = "in container" if self.side_of(kind) == AR.NanoClawAgentContainer else short(m.value(items[0][0], AR.nativeScopeKind))
                hpath = container_only if self.side_of(kind) == AR.NanoClawAgentContainer else "— (remote)"
            inside.append((short(kind), cpath, hpath, effects, via, status, gates.get(kind, "-")))

        # 3. Read-only mounts.
        for mnt in mounts:
            if not mnt["RW"]:
                kinds = [self.graph.value(loc, RDF.type) for loc in self.graph.objects(self.node(f"mount{mnt['Destination']}"), OBS.exposes)]
                inside.append((", ".join(short(k) for k in kinds) or "-", mnt["Destination"], backing(mnt["Destination"]), "none", "-", "Unavailable", "read-only mount"))

        outside, remote_via_host = self.host_side_rows(lockdown_on)
        remote = self.remote_rows(lockdown_on, remote_via_host)

        def dedupe(rows, width):
            seen, out = set(), []
            for row in rows:
                key = (row[0].strip(" └"),) + tuple(row[1:width])
                if key not in seen:
                    seen.add(key)
                    out.append(row)
            return out

        inside, outside, remote = dedupe(inside, 4), dedupe(outside, 4), dedupe(remote, 4)
        for i, (res, cpath, hpath, effects, via, status, scope) in enumerate(inside):
            self.add(self.node(f"modification_in_{i}"), OBS.ModificationAssessment, OBSERVED, f"{res.strip(' └')} @ {cpath}", resource=res.strip(" └"), onSide=AR.NanoClawAgentContainer, containerPath=cpath, hostPath=hpath, effects=effects, via=via, status=status, gate=scope)
        for i, (res, hloc, effects, via, status, gate) in enumerate(outside):
            self.add(self.node(f"modification_out_{i}"), OBS.ModificationAssessment, OBSERVED, f"{res} @ {hloc}", resource=res, onSide=AR.NanoClawHostProcess, hostPath=hloc, effects=effects, via=via, status=status, gate=gate)
        for i, (res, rloc, effects, path, status, gate) in enumerate(remote):
            self.add(self.node(f"modification_remote_{i}"), OBS.ModificationAssessment, OBSERVED, f"{res} @ {rloc}", resource=res, onSide=AR.ExternalNetwork, remoteLocation=rloc, effects=effects, via=path, status=status, gate=gate)
        return inside, outside, remote

    def host_side_rows(self, lockdown_on: bool) -> tuple[list[tuple], dict]:
        """Host-side steps an agent can trigger, found by walking routesToKind
        from container-side tool endpoints to the first host-side invocations."""
        m, f = self.model, self.facts
        scope = f["config"].get("cli_scope") or "group"
        folder = f["group"].get("folder") or "{folder}"
        grants = f["grants"]
        agent_grants = [d["local_name"] for d in grants if d["target_type"] == "agent"]
        ws = next((x for x in f["inspect"]["Mounts"] if x["Destination"] == "/workspace"), {})
        session_dir = self.host_path(ws.get("Source")) or "data/v2-sessions/<group>/<session>"
        channel_grants = [f"{d['local_name']} ({d.get('channel_type')})" for d in grants if d["target_type"] == "channel"]

        entries = [k for k in m.subjects(RDF.type, AR.ToolEndpointKind) if self.side_of(k) == AR.NanoClawAgentContainer]
        ncl_kinds = {k for k in entries if k == AR.NanoClawContainerNclCLI or AR.NanoClawContainerNclCLI in m.transitive_objects(k, AR.specializesInvocationKind)}
        if scope == "disabled":
            entries = [k for k in entries if k not in ncl_kinds]
        elif scope != "global":
            entries = [k for k in entries if k != AR.NanoClawContainerGlobalAdminCLI]
        reached: dict[URIRef, set[URIRef]] = {}
        for entry in entries:
            todo, seen = [entry], set()
            while todo:
                k = todo.pop()
                if k in seen:
                    continue
                seen.add(k)
                if k != entry and self.side_of(k) == AR.NanoClawHostProcess and (k, RDF.type, AR.InvocationSurfaceKind) in m:
                    reached.setdefault(k, set()).add(entry)
                if k == AR.NanoClawHostDeliveryInvocation:
                    continue  # hub: every outbound row passes through; specific steps have direct routes
                todo.extend(t for t in m.objects(k, AR.routesToKind) if (t, RDF.type, AR.InvocationSurfaceKind) in m)
                # inherit routes of broader invocation kinds
                todo.extend(m.objects(k, AR.specializesInvocationKind))

        # What each host-side step changes, where, and its status in this session.
        effects = {
            AR.NanoClawHostDeliveryInvocation: ("NanoClawDeliveryRecord", "Create", f"{session_dir}/inbound.db (delivered)", "Available"),
            AR.NanoClawAgentRouteInvocation: ("NanoClawInboundMessage (another agent's session)", "Create", ", ".join(agent_grants) or "no agent destination grants", "Available" if agent_grants else "Unavailable"),
            AR.NanoClawHostAttachmentStaging: ("NanoClawInboxArtifact (another agent's session)", "Create", "data/v2-sessions/<target group>/<session>/inbox/", "Available" if agent_grants else "Unavailable"),
            AR.NanoClawHostTaskLogAppend: ("NanoClawTaskRunLog", "Update", f"groups/{folder}/tasks/<series>.md", "Available" if scope != "disabled" else "Unavailable"),
            AR.NanoClawHostImageBuild: ("NanoClawAgentImage", "Install, Update", "per-group image (Docker image store)", "Available"),
            AR.NanoClawHostConfigMaterialization: ("NanoClawHostContainerConfigFile, NanoClawHostComposedInstructionsFile", "Update", f"groups/{folder}/container.json, groups/{folder}/CLAUDE.md", "Available" if scope != "disabled" else "Unavailable"),
            AR.NanoClawHostCommandDispatch: ("NanoClawCentralDatabase", "Create, Update, Delete", "data/v2.db", "Available" if scope != "disabled" else "Unavailable"),
            AR.NanoClawHostGuardInvocation: ("NanoClawCentralDatabase", "Create, Update, Delete", "data/v2.db", "Available" if scope != "disabled" else "Unavailable"),
        }
        names = {AR.NanoClawContainerShellExecution: "shell"}
        rows = []
        remote_via_host = {step: srcs for step, srcs in reached.items() if step == AR.NanoClawChannelAdapterDelivery}
        for step, sources in sorted(reached.items(), key=lambda kv: short(kv[0])):
            if step not in effects:
                continue
            resource, eff, where, status = effects[step]
            leaves = {e for e in sources if not any(e in m.objects(o, AR.specializesInvocationKind) for o in sources)}
            via = ", ".join(sorted(names.get(e, short(e).replace("NanoClaw", "").replace("Tool", "")) for e in leaves))
            if step == AR.NanoClawHostDeliveryInvocation:
                via = "every outbound row (all built-in tools, ncl, direct writes)"
            controls = sorted(short(c) for c in m.objects(step, AR.protectedByKind))
            rows.append((resource, where, eff, f"{short(step).replace('NanoClaw', '')} ← {via}", status, ", ".join(controls) or "-"))

        # Deliveries to local channels stay on this machine.
        for d in grants:
            if d["target_type"] == "channel" and d.get("channel_type") in LOCAL_CHANNELS and AR.NanoClawChannelAdapterDelivery in reached:
                rows.append(("MessagingMessage (local channel)", f"{d.get('channel_type')}: {d.get('display_name') or d['local_name']} (local client)", "Create, Transmit", "ChannelAdapterDelivery ← built-in messaging tools", "Available", "destination grant; origin chat always allowed"))

        # Host-mediated management actions (guard rules encoded here; see README).
        if scope != "disabled":
            rows.append(("NanoClawScheduledTask", "data/v2.db + task session inbound.db", "Create, Update, Delete", "ncl tasks", "Available", "no approval"))
            rows.append(("NanoClawContainerConfiguration", "data/v2.db (container_configs)", "Update", "ncl groups config", "Available", "held for approval"))
            rows.append(("NanoClawDestinationGrant", "data/v2.db (agent_destinations)", "Create, Delete", "ncl destinations", "Available", "held for approval"))
            rows.append(("NanoClawRoleMembershipState", "data/v2.db (members)", "Create, Delete", "ncl members", "Available", "held for approval"))
        if scope == "global":
            rows.append(("NanoClawMessagingRouteConfiguration", "data/v2.db (wirings, messaging groups, policies)", "Create, Update, Delete", "ncl (global scope)", "Available", "held for approval"))
            rows.append(("NanoClawRoleMembershipState", "data/v2.db (users, roles)", "Create, Update, Delete", "ncl (global scope)", "Available", "held for approval"))
        rows.append(("NanoClawAgentGroup", "data/v2.db + groups/<new folder>", "Create", "create_agent", "Available", "no approval (cli_scope=global)" if scope == "global" else "held for approval"))
        rows.append(("NanoClawAgentImage", "per-group image (Docker image store)", "Install, Update", "install_packages", "Available", "held for approval; rebuild + restart"))
        rows.append(("NanoClawContainerConfiguration", f"data/v2.db → groups/{folder}/container.json", "Configure", "add_mcp_server", "Available", "held for approval; restart"))
        return rows, remote_via_host

    def remote_rows(self, lockdown_on: bool, via_host: dict) -> list[tuple]:
        """What this session can reach or change beyond the local machine.

        Container-originated requests leave through the OneCLI gateway (and directly
        when lockdown is off); messages leave through the host's channel adapter;
        provider web search runs at the model provider. Reads are included here
        because the remote party sees the request. Model-provider traffic is out of scope.
        """
        m, f = self.model, self.facts
        rows: list[tuple] = []
        agent = f["onecli_agent"]
        rule_count = len([r for r in f["rules"] if not r.get("agentId") or (agent and r.get("agentId") == agent["id"])])
        leave = "container ▸ OneCLI gateway ▸ Internet" if lockdown_on else "container ▸ OneCLI gateway or direct ▸ Internet"
        net_gate = f"gateway policy ({rule_count} rule(s) in scope); credentials injected per host" + ("; direct route blocked" if lockdown_on else "; direct route open")
        endpoint_names = {
            AR.NanoClawContainerShellExecution: "shell (curl, scripts, ...)",
            AR.NanoClawProviderWebFetchTool: "web fetch",
            AR.NanoClawProviderWebSearchTool: "web search",
        }
        for cap, status in sorted(self.cap_status.items(), key=lambda kv: short(kv[0])):
            resource = m.value(cap, AR.nativeResourceKind)
            if status == OBS.Unavailable or self.side_of(resource) != AR.ExternalNetwork:
                continue
            endpoint = m.value(cap, AR.nativeEndpointKind)
            effects = ", ".join(sorted(short(e) for e in m.objects(cap, AR.nativeEffectType)))
            name = endpoint_names.get(endpoint, short(endpoint))
            if self.side_of(endpoint) == AR.ExternalNetwork:
                rows.append((short(resource), "search results (any site)", effects, f"{name}: query sent inside the model request ▸ OneCLI gateway ▸ model provider, which runs the search", short(status), "local controls see only the model request, not the searches or sites; disable via the tool allowlist"))
            else:
                rows.append((short(resource), "any public host", effects, f"{name}: {leave}", short(status), net_gate))
        for name, spec in (f["config"].get("mcp_servers") or {}).items():
            if isinstance(spec, dict) and spec.get("url"):
                rows.append(("RemoteMCPService", spec["url"].split("/")[2] if "//" in spec["url"] else spec["url"], "Transmit", f"MCP server '{name}': {leave}", "Available", net_gate + "; the service's own calls happen remotely"))
        if AR.NanoClawChannelAdapterDelivery in via_host:
            sources = via_host[AR.NanoClawChannelAdapterDelivery]
            tools = ", ".join(sorted(short(e).replace("NanoClaw", "").replace("Tool", "") for e in sources))
            for d in f["grants"]:
                if d["target_type"] == "channel" and d.get("channel_type") not in LOCAL_CHANNELS:
                    rows.append(("MessagingMessage", f"{d.get('channel_type')}: {d.get('display_name') or d['local_name']}", "Create, Transmit", f"{tools} ▸ outbound mailbox ▸ host delivery ▸ {d.get('channel_type')} adapter", "Available", "destination grant; origin chat always allowed; the host holds the channel credentials"))
        return rows

    def routes(self, lockdown_on: bool) -> list[tuple[str, str, str]]:
        scope = self.facts["config"].get("cli_scope") or "group"
        rows = [
            ("NanoClawProxyAwareHTTPRequest", "available", "gateway attached" if lockdown_on else "gateway reachable via proxy env"),
            ("NanoClawDirectNetworkRequest", "blocked" if lockdown_on else "available", "internal network, no route out" if lockdown_on else "default bridge network"),
            ("NanoClawHostReachableService", "unreachable" if lockdown_on else "reachable", "host.docker.internal resolves to the gateway" if lockdown_on else "host services reachable on the bridge"),
            ("NanoClawContainerTasksCLI", "unavailable" if scope == "disabled" else "available", f"cli_scope={scope}"),
            ("NanoClawContainerGroupAdminCLI", "unavailable" if scope == "disabled" else "available (writes held)", f"cli_scope={scope}"),
            ("NanoClawContainerGlobalAdminCLI", "available (writes held)" if scope == "global" else "unavailable", f"cli_scope={scope}"),
            ("NanoClawCreateAgentTool", "allowed without approval" if scope == "global" else "held for approval", f"cli_scope={scope}"),
            ("NanoClawAdditionalHostDirectory", "present" if any(m["Destination"].startswith("/workspace/extra/") for m in self.facts["inspect"]["Mounts"]) else "absent", "observed mounts"),
        ]
        for name, status, why in rows:
            self.add(self.node(f"route_{name}"), OBS.RouteAssessment, OBSERVED, name, assesses=AR[name], status=status, reason=why)
        return rows


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", help="session id (default: most recently active running session)")
    parser.add_argument("--nanoclaw", type=Path, help="NanoClaw checkout (default: nanoclaw-core sourceRepositoryPath)")
    parser.add_argument("--out", type=Path, default=ROOT / "observations")
    parser.add_argument("--no-write", action="store_true", help="print the report without writing a snapshot file")
    args = parser.parse_args()

    model = load_model()
    pinned_repo = next(model.objects(AR.NanoClawCoreModule, AR.sourceRepositoryPath), None)
    pinned_rev = str(next(model.objects(AR.NanoClawCoreModule, AR.sourceRevision), ""))
    nanoclaw = args.nanoclaw or Path(str(pinned_repo))
    facts = collect(nanoclaw, args.session)
    if facts["nanoclaw_head"] != pinned_rev:
        print(f"warning: NanoClaw HEAD {facts['nanoclaw_head'][:12]} differs from the modeled revision {pinned_rev[:12]}; results may be stale.", file=sys.stderr)

    taken_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    snap = Snapshot(facts, model, taken_at)
    snap.build()
    lockdown_on = any(n["internal"] for n in facts["networks"].values())
    caps = snap.capabilities()
    routes = snap.routes(lockdown_on)
    inside, outside, remote = snap.modifications(lockdown_on)

    # Every instance must be typed with a kind the model declares.
    known = set(model.subjects(RDF.type, None)) | {OBS.Snapshot, OBS.ConditionEvaluation, OBS.CapabilityAssessment, OBS.RouteAssessment, OBS.ModificationAssessment}
    unknown_kinds = sorted({o for o in snap.graph.objects(None, RDF.type) if o not in known})
    if unknown_kinds:
        raise SystemExit("Snapshot uses undeclared kinds: " + ", ".join(map(str, unknown_kinds)))

    sess, group, config = facts["session"], facts["group"], facts["config"]
    print_table("Session snapshot", ("Field", "Value"), [
        ("Session", sess["id"]),
        ("Agent group", f"{group['name']} ({group['id']})"),
        ("Other sessions in group", str(len(facts["group_sessions"]) - 1)),
        ("Container", facts["container_name"]),
        ("Provider", config.get("provider") or "claude (default)"),
        ("cli_scope", config.get("cli_scope") or "group"),
        ("Egress lockdown", "on" if lockdown_on else "off"),
        ("Destination grants", ", ".join(d["local_name"] for d in facts["grants"]) or "none"),
        ("MCP servers (third-party)", ", ".join(config.get("mcp_servers") or {}) or "none"),
        ("Gateway identity", f"{facts['onecli_agent']['identifier']} secretMode={facts['onecli_agent'].get('secretMode')}" if facts["onecli_agent"] else "none"),
        ("Gateway rules in scope", str(len([r for r in facts["rules"] if not r.get("agentId") or (facts["onecli_agent"] and r.get("agentId") == facts["onecli_agent"]["id"])]))),
        ("Instances / triples", f"{len(set(snap.graph.subjects(RDF.type, None)))} / {len(snap.graph)}"),
    ], (26, 90))

    def host_kind(dest: str) -> str:
        backing = snap.graph.value(snap.node(f"mount{dest}"), OBS.bindsFrom)
        return short(snap.graph.value(backing, RDF.type)) if backing is not None else "-"

    print_table("Observed mounts (container view ← host source)", ("Container path", "Mode", "Container-side kind", "Host path", "Host-side kind"), [
        (m["Destination"], "rw" if m["RW"] else "ro", short(snap.graph.value(snap.node(f"mount{m['Destination']}"), RDF.type)), snap.host_path(m.get("Source")) or "-", host_kind(m["Destination"]))
        for m in sorted(facts["inspect"]["Mounts"], key=lambda m: m["Destination"])
    ], (32, 4, 34, 46, 36))

    print_table("Requirements for this session", ("Requirement", "Status", "Reason"), [
        (short(c), short(s), r) for c, (s, r) in sorted(snap.conditions.items(), key=lambda kv: (short(kv[1][0]), short(kv[0])))
    ], (44, 11, 70))

    print_table("Native capabilities in this session (may-effects)", ("Capability", "Status", "Effect", "Resource", "Reaches", "Why"), [
        (r["capability"], r["status"], r["effect"], r["resource"], r["scope"], r["why"]) for r in sorted(caps, key=lambda r: (r["status"], r["capability"]))
    ], (34, 11, 18, 26, 34, 40))

    print_table("Routes and management paths", ("Kind", "Status", "Why"), routes, (34, 24, 50))

    print_table("Modifiable inside the container (may-effects; reads excluded)", ("Resource", "Container path", "Host backing", "Effects", "Via", "Status", "Scope / gate"), inside, (36, 30, 40, 22, 18, 11, 28))
    print_table("Changed outside the container, on the host (triggered by the agent)", ("Resource", "Host location", "Effects", "Triggered by", "Status", "Gate"), outside, (36, 38, 20, 40, 11, 30))
    print_table("Outside this machine (remote): reached or changed", ("Resource", "Remote location", "Effects", "Path off the machine", "Status", "Gate"), remote, (22, 30, 16, 52, 11, 40))

    installed = facts["container_skills"]
    modeled = skill_directories()
    print_table("Skills", ("Installed container skill", "Modeled skill graph"), [
        (name, modeled[name].name if name in modeled else "none") for name in installed
    ], (30, 40))
    if not any(name in modeled for name in installed):
        print("No installed skill has a skill graph, so no skill operations apply to this session; only native capabilities do.")

    if snap.findings:
        print("\nModel/runtime differences:")
        for item in snap.findings:
            print(f"  - {item}")

    if not args.no_write:
        args.out.mkdir(exist_ok=True)
        path = args.out / f"{sess['id']}-{taken_at.replace(':', '')}.trig"
        ds = Dataset()
        for prefix, ns in (("ar", AR), ("obs", OBS), ("inst", snap.inst)):
            ds.bind(prefix, ns)
        named = ds.graph(snap.graph.identifier)
        for triple in snap.graph:
            named.add(triple)
        ds.serialize(path, format="trig")
        print(f"\nSnapshot written: {path}")


if __name__ == "__main__":
    main()
