"""Collect facts about one live session.

Names and settings only: secret values, tokens, and environment values are
never read.
"""

import subprocess
from pathlib import Path

from .gateway_policy import read_gateway_policy
from .provider_tools import read_tool_lists
from .runtime import docker_json, ncl, onecli, run, sqlite_rows, tool


def pick_session(sessions: list[dict], session_id: str | None) -> dict:
    """The requested session, or the most recently active one with a running container."""
    if session_id is not None:
        session = next((s for s in sessions if s["id"] == session_id), None)
        if session is None:
            raise SystemExit(f"Unknown session {session_id}")
        return session
    running = sorted(
        (s for s in sessions if s["container_status"] == "running"),
        key=lambda s: s["last_active"] or "",
        reverse=True,
    )
    if not running:
        raise SystemExit("No running session. Start one (send the agent a message) or pass --session.")
    return running[0]


def collect_container(session_id: str) -> dict:
    """docker inspect of the session's container, its networks, and whether curl exists."""
    containers = run([tool("docker"), "ps", "--format", "{{.Names}}"]).split()
    container_name = next((n for n in containers if n.endswith(session_id)), None)
    if container_name is None:
        raise SystemExit(f"Session {session_id} has no running container; this collector only reads live sessions.")
    inspect = docker_json("inspect", container_name)[0]
    networks = {}
    for name in inspect["NetworkSettings"]["Networks"]:
        net = docker_json("network", "inspect", name)[0]
        networks[name] = {
            "internal": bool(net.get("Internal")),
            "members": sorted(c["Name"] for c in net.get("Containers", {}).values()),
        }
    try:
        curl = run([tool("docker"), "exec", container_name, "sh", "-c", "command -v curl || true"]).strip()
    except subprocess.CalledProcessError:
        curl = ""
    return {"container_name": container_name, "inspect": inspect, "networks": networks, "curl": curl}


def collect_gateway(group_id: str) -> dict:
    """OneCLI identity, secret names, and rules. Never the agent's access token."""
    agents = [{k: a.get(k) for k in ("id", "name", "identifier", "secretMode")} for a in onecli("agents", "list")]
    return {
        "onecli_agent": next((a for a in agents if a["identifier"] == group_id), None),
        "secrets": [{k: s.get(k) for k in ("name", "type", "hostPattern")} for s in onecli("secrets", "list")],
        "rules": [{k: r.get(k) for k in ("name", "action", "hostPattern", "agentId", "enabled")} for r in onecli("rules", "list")],
        "gateway_policy": read_gateway_policy(),
    }


def collect_central(nanoclaw: Path, group_id: str, sessions: list[dict]) -> dict:
    """Group, config, wirings, destination grants, roles, and members via host ncl."""
    return {
        "group": next(g for g in ncl(nanoclaw, "groups", "list") if g["id"] == group_id),
        "config": ncl(nanoclaw, "groups", "config", "get", "--id", group_id),
        "group_sessions": [s for s in sessions if s["agent_group_id"] == group_id],
        "messaging_groups": ncl(nanoclaw, "messaging-groups", "list"),
        "wirings": [w for w in ncl(nanoclaw, "wirings", "list") if w["agent_group_id"] == group_id],
        "grants": [d for d in ncl(nanoclaw, "destinations", "list") if d["agent_group_id"] == group_id],
        "roles": ncl(nanoclaw, "roles", "list"),
        "members": [m for m in ncl(nanoclaw, "members", "list") if m.get("agent_group_id") == group_id],
    }


def collect_checkout(nanoclaw: Path) -> dict:
    return {
        "container_skills": sorted(p.name for p in (nanoclaw / "container" / "skills").iterdir() if p.is_dir()),
        "a2a_installed": (nanoclaw / "src" / "modules" / "agent-to-agent").is_dir(),
        "claude_tools": read_tool_lists(nanoclaw),
        "nanoclaw_head": run([tool("git"), "-C", str(nanoclaw), "rev-parse", "HEAD"]).strip(),
        "nanoclaw_root": nanoclaw.resolve(),
    }


def collect(nanoclaw: Path, session_id: str | None) -> dict:
    sessions = ncl(nanoclaw, "sessions", "list")
    session = pick_session(sessions, session_id)
    group_id = session["agent_group_id"]
    container = collect_container(session["id"])
    session_dir = nanoclaw / "data" / "v2-sessions" / group_id / session["id"]
    central = collect_central(nanoclaw, group_id, sessions)
    gateway = collect_gateway(group_id)
    return {
        "session": session,
        **central,
        "projected": sqlite_rows(
            session_dir / "inbound.db",
            "SELECT name, type, channel_type, platform_id, agent_group_id FROM destinations",
        ),
        **container,
        **gateway,
        **collect_checkout(nanoclaw),
    }
