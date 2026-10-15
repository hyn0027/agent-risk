"""Network routes and management paths for this session.

The ncl / create_agent rows encode NanoClaw's guard rules here because the
ontology states them only in comments; update them if those guards change.
"""

from ..common.namespaces import AR, OBS
from .constants import OBSERVED
from .snapshot import Snapshot


def assess_routes(snap: Snapshot) -> list[tuple[str, str, str]]:
    lockdown, scope = snap.lockdown_on, snap.cli_scope
    extra = any(m["Destination"].startswith("/workspace/extra/") for m in snap.facts["inspect"]["Mounts"])
    rows = [
        ("NanoClawProxyAwareHTTPRequest", "available", "gateway attached" if lockdown else "gateway reachable via proxy env"),
        ("NanoClawDirectNetworkRequest", "blocked" if lockdown else "available", "internal network, no route out" if lockdown else "default bridge network"),
        ("NanoClawHostReachableService", "unreachable" if lockdown else "reachable", "host.docker.internal resolves to the gateway" if lockdown else "host services reachable on the bridge"),
        ("NanoClawContainerTasksCLI", "unavailable" if scope == "disabled" else "available", f"cli_scope={scope}"),
        ("NanoClawContainerGroupAdminCLI", "unavailable" if scope == "disabled" else "available (writes held)", f"cli_scope={scope}"),
        ("NanoClawContainerGlobalAdminCLI", "available (writes held)" if scope == "global" else "unavailable", f"cli_scope={scope}"),
        ("NanoClawCreateAgentTool", "allowed without approval" if scope == "global" else "held for approval", f"cli_scope={scope}"),
        ("NanoClawAdditionalHostDirectory", "present" if extra else "absent", "observed mounts"),
    ]
    for name, status, why in rows:
        snap.add(snap.node(f"route_{name}"), OBS.RouteAssessment, OBSERVED, name, assesses=AR[name], status=status, reason=why)
    return rows
