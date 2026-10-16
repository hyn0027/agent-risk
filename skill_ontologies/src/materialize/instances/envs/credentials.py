"""The account behind each credential the gateway grants the agent."""

from ..model import Instance
from ..registry import Context, environment


@environment("credentials", kinds=["ConnectedServiceData"])
def credentials(ctx: Context) -> None:
    """OneCLI credential grants: the account behind each granted credential"""
    for s in ctx.snap.facts["secrets"]:
        ctx.add(Instance("ConnectedServiceData", f"credential:{s['name']}", f"the account behind credential '{s['name']}' at {s['hostPattern']}",
                         None, {"host": s["hostPattern"], "match": s["hostPattern"]}))
