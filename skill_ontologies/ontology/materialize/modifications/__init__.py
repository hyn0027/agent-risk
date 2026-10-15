"""What this session can change, split by where the change happens.

``inside``  in the container (with the host path a bind mount writes through to)
``host``    on the host, through host steps the agent can trigger
``remote``  beyond the local machine
"""

from ...common.namespaces import AR, OBS
from ..constants import OBSERVED
from ..snapshot import Snapshot
from .common import dedupe
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
    inside, outside, remote = dedupe(inside, 4), dedupe(outside, 4), dedupe(remote, 4)
    record(snap, inside, outside, remote)
    return inside, outside, remote
