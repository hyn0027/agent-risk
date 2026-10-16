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
from .model import add_mcp_graphs, add_skill_graphs, load_model, pinned_source
from .modifications import assess_modifications
from .operations import assess_operations
from .downstream import assess_downstream
from .output import check_instance_types, write_snapshot
from .report import print_report
from .routes import assess_routes
from .snapshot import Snapshot
from .tools import assess_tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", help="session id (default: most recently active running session)")
    parser.add_argument("--nanoclaw", type=Path, help="NanoClaw checkout (default: nanoclaw-core sourceRepositoryPath)")
    parser.add_argument("--out", type=Path, default=OBSERVATIONS_DIR)
    parser.add_argument("--no-write", action="store_true", help="print the report without writing a snapshot file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = load_model()
    pinned_repo, pinned_rev = pinned_source(model)
    nanoclaw = args.nanoclaw or pinned_repo
    facts = collect(nanoclaw, args.session)
    facts["modeled_skills"] = add_skill_graphs(model, facts["container_skills"])
    facts["modeled_mcp"] = add_mcp_graphs(model, facts["config"].get("mcp_servers") or {})
    if facts["nanoclaw_head"] != pinned_rev:
        print(f"warning: nanoclaw_head={facts['nanoclaw_head'][:12]}; modeled_revision={pinned_rev[:12]}", file=sys.stderr)

    taken_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    snap = Snapshot(facts, model, taken_at)
    problem = deny_by_default_problem(facts["gateway_policy"], snap.lockdown_on)
    if problem:
        sys.exit(f"error: precondition failed: {problem} (required: cedar_policy_rules=present, GATEWAY_STRICT_DENY=on, lockdown=on)")
    instantiate(snap)
    resolve_conditions(snap)
    assess_capabilities(snap)  # fills snap.cap_status, used by every table
    assess_tools(snap)  # recorded in the snapshot graph only
    assess_routes(snap)  # recorded in the snapshot graph only
    inside, outside, remote = assess_modifications(snap, assess_operations(snap))
    downstream = assess_downstream(snap, snap.raw_remote)
    check_instance_types(snap)

    print_report(snap, inside, outside, remote, downstream)
    if not args.no_write:
        print(f"\nSnapshot written: {write_snapshot(snap, args.out)}")
