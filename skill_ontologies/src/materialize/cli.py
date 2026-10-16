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
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..common.paths import OBSERVATIONS_DIR
from .capabilities import assess_capabilities
from .gateway_policy import deny_by_default_problem
from .collect import collect
from .conditions import resolve_conditions
from .instantiate import instantiate
from .model import add_mcp_graphs, add_skill_graphs, load_model, pinned_source, stale_skill_graphs
from .modifications import assess_modifications
from .operations import assess_operations
from .downstream import assess_downstream
from .instances import discover, with_instances, write_instances
from .pair_risks import annotate
from .probe import ContainerProbe
from .run_log import RunLog
from .output import check_instance_types, write_snapshot
from .report import print_report
from .routes import assess_routes
from .snapshot import Snapshot
from .tools import assess_tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", help="session id (default: most recently active running session)")
    parser.add_argument("--nanoclaw", type=Path, help="NanoClaw checkout (default: nanoclaw-core sourceRepositoryPath)")
    parser.add_argument("--out", type=Path, default=OBSERVATIONS_DIR, help="snapshot directory; run logs go to <out>/runs/")
    parser.add_argument("--no-write", action="store_true", help="print the report without writing a snapshot file")
    parser.add_argument("--no-discovery", action="store_true",
                        help="skip live instance discovery (read-only GitHub/Vercel calls made from the container as the agent); NanoClaw records and credential grants are still used")
    parser.add_argument("--max-pairs", type=int, help="maximum host/downstream resource pairs to annotate with the LLM (default: all; 0: skip)")
    parser.add_argument("--cross-only", action="store_true", help="annotate only host–remote instance pairs")
    parser.add_argument("--workers", type=int, default=20, help="parallel LLM calls for the pair annotation (default: 20)")
    parser.add_argument("--seed", type=int, help="random seed for the pair sample (default: a fresh one, printed)")
    parser.add_argument("--model", default="gpt-6-luna", help="OpenAI model for the pair annotation (default: gpt-6-luna)")
    args = parser.parse_args()
    if args.max_pairs is not None and args.max_pairs < 0:
        parser.error("--max-pairs must be non-negative")
    return args


def main() -> None:
    args = parse_args()
    model = load_model()
    pinned_repo, pinned_rev = pinned_source(model)
    nanoclaw = args.nanoclaw or pinned_repo
    facts = collect(nanoclaw, args.session)
    facts["modeled_skills"] = add_skill_graphs(model, facts["container_skills"])
    facts["modeled_mcp"] = add_mcp_graphs(model, facts["config"].get("mcp_servers") or {})
    taken_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    log = RunLog(args.out, facts["session"]["id"], taken_at)
    try:
        run(args, facts, model, pinned_rev, taken_at, log)
    finally:
        log.close()
    print(f"\nRun log: {log.dir}")


def run(args: argparse.Namespace, facts: dict, model, pinned_rev: str, taken_at: str, log: RunLog) -> None:
    for name in facts["container_skills"]:
        if name not in facts["modeled_skills"]:
            log.warn(f"skill {name} has no ontology (ontology/skills/*.trig with ar:skillDirectory \"{name}\"); its operations are not in the tables")
    for name, problem in stale_skill_graphs(facts["modeled_skills"]).items():
        log.warn(f"skill {name} ontology is stale: {problem}")
    for name in facts["config"].get("mcp_servers") or {}:
        if name not in facts["modeled_mcp"]:
            log.warn(f"MCP server {name} has no ontology (no ontology/mcp/*.trig ar:mcpEndpointPattern matches it); its tools are not in the tables")
    if facts["nanoclaw_head"] != pinned_rev:
        log.warn(f"nanoclaw_head={facts['nanoclaw_head'][:12]}; modeled_revision={pinned_rev[:12]}")

    snap = Snapshot(facts, model, taken_at)
    problem = deny_by_default_problem(facts["gateway_policy"], snap.lockdown_on)
    if problem:
        log.warn(f"precondition failed: {problem}")
        sys.exit(f"error: precondition failed: {problem} (required: cedar_policy_rules=present, GATEWAY_STRICT_DENY=on, lockdown=on)")
    instantiate(snap)
    resolve_conditions(snap)
    assess_capabilities(snap)  # fills snap.cap_status, used by every table
    assess_tools(snap)  # recorded in the snapshot graph only
    assess_routes(snap)  # recorded in the snapshot graph only
    requests: list[dict] = []
    probe = None if args.no_discovery else ContainerProbe(facts["container_name"], requests)
    discover(snap, probe)
    for warning in snap.instances.warnings:
        log.warn(warning)
    log.write_json("requests.jsonl", requests)
    write_instances(snap.instances, log.dir / "instances.json")
    inside, outside, remote = assess_modifications(snap, assess_operations(snap))
    outside_rows = outside  # without the instance lines, for the joint-risk items
    outside = with_instances(snap, outside)
    downstream, ruled_out = assess_downstream(snap, snap.raw_remote)
    check_instance_types(snap)

    log.start_tables()
    # not shown: what instances or a declared scope rule out; kept in the run log only
    log.write_json("ruled-out.jsonl", [{"step": a, "started_by": b.splitlines(), "why": c} for a, b, c in ruled_out])
    print_report(snap, inside, outside, remote, downstream)
    snapshot = None if args.no_write else write_snapshot(snap, args.out)
    if snapshot:
        print(f"\nSnapshot written: {snapshot}")
    report = log.write_report(f"materialize: session {facts['session']['id']} at {taken_at}", snap.findings, snapshot)
    print(f"Full report (unwrapped): {report}")
    annotate(snap, outside_rows, remote, downstream, model=args.model, max_pairs=args.max_pairs, log_dir=log.dir, cross_only=args.cross_only, seed=args.seed, workers=args.workers)
