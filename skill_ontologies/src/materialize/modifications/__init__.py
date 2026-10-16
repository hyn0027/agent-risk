"""What this session can read or change, split by where it happens.

``inside``  in the container, reads and changes (with the host path a bind mount
            reads or writes through to)
``host``    on the host, through host steps the agent can trigger
``remote``  beyond the local machine
"""

from ...common.namespaces import AR, OBS
from ..constants import OBSERVED
from ..snapshot import Snapshot
from .common import merge_rows
from .host import host_rows
from .inside import inside_rows
from .remote import remote_rows


def record(snap: Snapshot, inside: list[tuple], outside: list[tuple], remote: list[tuple]) -> None:
    """Store every row as an obs:ModificationAssessment on its side."""
    for i, (res, cpath, hpath, effects, via, status, scope) in enumerate(inside):
        snap.add(snap.node(f"modification_in_{i}"), OBS.ModificationAssessment, OBSERVED, f"{res.strip(' └')} @ {cpath}", resource=res.strip(" └"), onSide=AR.NanoClawAgentContainer, containerPath=cpath, hostPath=hpath, effects=effects, via=via, status=status, gate=scope)
    for i, (res, hloc, effects, via, status, gate) in enumerate(outside):
        snap.add(snap.node(f"modification_out_{i}"), OBS.ModificationAssessment, OBSERVED, f"{res} @ {hloc}", resource=res, onSide=AR.NanoClawHostProcess, hostPath=hloc, effects=effects, via=via, status=status, gate=gate)
    for i, (res, rloc, effects, path, status, gate) in enumerate(remote):
        snap.add(snap.node(f"modification_remote_{i}"), OBS.ModificationAssessment, OBSERVED, f"{res} @ {rloc}", resource=res, onSide=AR.ExternalNetwork, remoteLocation=rloc, effects=effects, via=path, status=status, gate=gate)


def assess_modifications(snap: Snapshot) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """(inside, outside, remote) rows; call after ``assess_capabilities``."""
    inside = inside_rows(snap)
    outside, remote_via_host = host_rows(snap)
    remote = remote_rows(snap, remote_via_host)
    # Same resource at the same location with the same status → one row.
    inside = merge_rows(inside, 3, effects=3, via=4, gate=6)
    outside = merge_rows(outside, 2, effects=2, via=3, gate=5)
    remote = merge_rows(remote, 2, effects=2, via=3, gate=5)
    record(snap, inside, outside, remote)
    return inside, outside, remote
