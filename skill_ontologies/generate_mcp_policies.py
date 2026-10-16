"""Generate a OneCLI Cedar policy group for an MCP server from its pinned snapshot.

    python3 generate_mcp_policies.py github > mcp-github.json
    onecli-policy sync mcp-github.json

Reads the same snapshot as generate_mcp_ontology.py (ontology/mcp/sources/<id>.json)
and writes the JSON spec `onecli-policy sync` takes: one group (source "mcp:<id>")
with the protocol policies the transport needs and one policy per tool, so every
tool can be switched on or off on its own.

- protocol: initialize, notifications, ping, and listing (tools, resources, prompts)
- read-content: resources/read, prompts/get, completion/complete, as far as the
  server declares those capabilities
- stream-and-session: GET and DELETE on the endpoint (streamable HTTP)
- tool-<name>: tools/call with params.name == <name>. Read-only tools (readOnlyHint)
  are on; other tools are off and carry @approval when destructive under the MCP
  ToolAnnotations defaults (destructiveHint unset counts as true), so switching one
  on still holds each call for a human.
"""

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "ontology" / "mcp" / "sources"


def cedar_str(text: str) -> str:
    return json.dumps(text)


def method_policy(host: str, path_pattern: str, methods: list[str]) -> str:
    listed = ",\n    ".join(cedar_str(m) for m in methods)
    return f'''permit(
  principal,
  action == OneCLI::Action::"POST",
  resource == OneCLI::Host::{cedar_str(host)}
) when {{
  context.path like {cedar_str(path_pattern)} &&
  context has json && context.json has method &&
  [
    {listed}
  ].contains(context.json.method)
}};'''


def tool_policy(host: str, path_pattern: str, tool: str, approval: bool) -> str:
    return ("@approval\n" if approval else "") + f'''permit(
  principal,
  action == OneCLI::Action::"POST",
  resource == OneCLI::Host::{cedar_str(host)}
) when {{
  context.path like {cedar_str(path_pattern)} &&
  context has json && context.json has method && context.json.method == "tools/call" &&
  context.json has params && context.json.params has name &&
  context.json.params.name == {cedar_str(tool)}
}};'''


def describe(tool: dict) -> str:
    a = tool["annotations"]
    kind = "read-only" if a.get("readOnlyHint") else ("destructive" if a.get("destructiveHint", True) else "additive write")
    sets = ", ".join(tool["toolsets"]) or "no documented toolset"
    title = tool.get("title") or tool["name"]
    return f"{title} ({kind}; toolset {sets})"[:500]


def generate(server_id: str) -> dict:
    snap = json.loads((SOURCES / f"{server_id}.json").read_text())
    url = urlparse(snap["callEndpoint"])
    host = url.hostname
    path_pattern = (url.path.rstrip("/") or "") + "*"
    caps = snap.get("capabilities") or {}
    title = snap["server"].get("title") or snap["server"]["name"]

    listing = ["initialize", "notifications/initialized", "notifications/cancelled", "ping", "tools/list"]
    content = []
    if "resources" in caps:
        listing += ["resources/list", "resources/templates/list"]
        content.append("resources/read")
    if "prompts" in caps:
        listing.append("prompts/list")
        content.append("prompts/get")
    if "completions" in caps:
        content.append("completion/complete")

    policies = [
        {"name": "protocol", "description": "MCP handshake, notifications, ping, and listing (JSON-RPC over POST)",
         "policyText": method_policy(host, path_pattern, listing)},
    ]
    if content:
        policies.append({"name": "read-content", "description": f"Server capabilities {', '.join(sorted(caps))}: " + ", ".join(content),
                         "policyText": method_policy(host, path_pattern, content)})
    policies.append({"name": "stream-and-session", "description": "Server stream (GET) and session close (DELETE) of the streamable HTTP transport",
                     "policyText": f'''permit(
  principal,
  action in [OneCLI::Action::"GET", OneCLI::Action::"DELETE"],
  resource == OneCLI::Host::{cedar_str(host)}
) when {{ context.path like {cedar_str(path_pattern)} }};'''})
    for tool in sorted(snap["tools"], key=lambda t: t["name"]):
        a = tool["annotations"]
        read_only = bool(a.get("readOnlyHint", False))
        destructive = not read_only and bool(a.get("destructiveHint", True))
        policies.append({
            "name": f"tool-{tool['name']}",
            "description": describe(tool),
            "enabled": read_only,
            "policyText": tool_policy(host, path_pattern, tool["name"], approval=destructive),
        })
    return {
        "name": f"mcp-{server_id}",
        "source": f"mcp:{server_id}",
        "description": f"{title} ({snap['callEndpoint']}): protocol plus one policy per tool, generated from ontology/mcp/sources/{server_id}.json. Read-only tools on; write tools off and held for approval when destructive.",
        "policies": policies,
    }


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python3 generate_mcp_policies.py <server-id>  > spec.json")
    json.dump(generate(sys.argv[1]), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
