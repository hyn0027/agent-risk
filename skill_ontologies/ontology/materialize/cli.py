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
from .collect import collect
from .conditions import resolve_conditions
from .instantiate import instantiate
from .model import load_model, pinned_source
from .modifications import assess_modifications
from .output import check_instance_types, write_snapshot
from .report import print_report
from .routes import assess_routes
from .snapshot import Snapshot


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
    if facts["nanoclaw_head"] != pinned_rev:
        print(f"warning: NanoClaw HEAD {facts['nanoclaw_head'][:12]} differs from the modeled revision {pinned_rev[:12]}; results may be stale.", file=sys.stderr)

    taken_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    snap = Snapshot(facts, model, taken_at)
    instantiate(snap)
    resolve_conditions(snap)
    caps = assess_capabilities(snap)
    routes = assess_routes(snap)
    inside, outside, remote = assess_modifications(snap)
    check_instance_types(snap)

    print_report(snap, caps, routes, inside, outside, remote)
    if not args.no_write:
        print(f"\nSnapshot written: {write_snapshot(snap, args.out)}")
