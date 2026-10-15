"""OneCLI gateway policy: mode and rules, and what is actually enforced.

The OneCLI CLI lists project rules but not the organization's policy mode, so
both are read (read-only) from OneCLI's own Postgres database. Semantics follow
the OneCLI gateway source (1.41 `forward.rs`, 2.x `policy-engine`): explicit
block rules apply to every request, but deny-by-default only applies to
*credentialed* requests (the gateway would inject a stored secret for the host)
to non-LLM hosts. Uncredentialed traffic is never default-denied, and LLM hosts
(anthropic.com, openai.com, ...) always bypass the default.
"""

import fnmatch
import json
import subprocess

from .runtime import tool

POSTGRES_CONTAINER = "onecli-postgres-1"

# Hosts the gateway treats as LLM providers (policy crate `is_llm_host`): they bypass deny-by-default.
LLM_HOST_MARKERS = ("anthropic.com", "openai.com", "chatgpt.com", "deepseek.com", "groq.com", "openrouter.ai", "moonshot.cn", "generativelanguage.googleapis.com")

POLICY_QUERY = """
select json_build_object(
  'mode', o.policy_mode,
  'subscription', o.subscription_status,
  'rules', coalesce((
    select json_agg(json_build_object(
      'name', r.name, 'action', r.action, 'host', r.host_pattern, 'path', r.path_pattern,
      'method', r.method, 'agentId', r.agent_id, 'enabled', r.enabled, 'scope', r.scope,
      'conditions', r.conditions, 'rateLimit', r.rate_limit, 'window', r.rate_limit_window))
    from policy_rules r
    where r.organization_id = o.id or r.project_id in (select p.id from projects p where p.organization_id = o.id)
  ), '[]'::json))
from organizations o limit 1;
"""


def read_gateway_policy() -> dict | None:
    """{"mode", "subscription", "rules": [...]}, or None when the database is unreachable."""
    argv = [
        tool("docker"), "exec", "-i", POSTGRES_CONTAINER, "sh", "-c",
        'psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-onecli}" -At -v ON_ERROR_STOP=1',
    ]
    try:
        out = subprocess.run(argv, input=POLICY_QUERY, check=True, capture_output=True, text=True, timeout=30).stdout
        return json.loads(out.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def applicable_rules(policy: dict | None, agent_id: str | None) -> list[dict]:
    """Enabled rules that apply to this OneCLI agent (agent-scoped or for all agents)."""
    if not policy:
        return []
    return [r for r in policy["rules"] if r.get("enabled") and (not r.get("agentId") or r.get("agentId") == agent_id)]


def is_llm_host(host: str) -> bool:
    return any(marker in host for marker in LLM_HOST_MARKERS)


def effective_mode(policy: dict | None) -> tuple[str, str]:
    """(mode: "allow" | "deny" | "unknown", explanation)."""
    if not policy:
        return "unknown", "OneCLI database not readable"
    if (policy.get("mode") or "allow") == "deny":
        return "deny", "deny-by-default: credentialed, non-LLM requests need an allow rule; other requests pass unless blocked"
    return "allow", "allow-by-default: every request passes unless a rule blocks it"


def credentialed_hosts(secrets: list[dict]) -> list[str]:
    """Host patterns the gateway injects a stored secret for."""
    return sorted({s["hostPattern"] for s in secrets if s.get("hostPattern")})


def rule_label(rule: dict) -> str:
    target = rule["host"] + (rule.get("path") or "")
    if rule.get("method"):
        target = f"{rule['method']} {target}"
    if rule.get("conditions"):
        target += " (conditional)"
    return target


def reachability(policy: dict | None, agent_id: str | None, secrets: list[dict]) -> tuple[str, str, bool]:
    """(where requests can go, gate text, anything reachable at all) for this agent."""
    mode, why = effective_mode(policy)
    rules = applicable_rules(policy, agent_id)
    by_action: dict[str, list[str]] = {}
    for r in rules:
        by_action.setdefault(r["action"], []).append(rule_label(r))
    extras = []
    if by_action.get("manual_approval"):
        extras.append("needs approval: " + ", ".join(by_action["manual_approval"]))
    if by_action.get("rate_limit"):
        extras.append("rate-limited: " + ", ".join(by_action["rate_limit"]))
    blocked = list(by_action.get("block", []))
    if mode == "deny":
        allowed = [r["host"] for r in rules if r["action"] == "allow"]
        for host in credentialed_hosts(secrets):
            if not is_llm_host(host) and not any(fnmatch.fnmatch(host, a) for a in allowed):
                blocked.append(f"{host} (credentialed, no allow rule)")
    where = "any public host" + (" except " + ", ".join(blocked) if blocked else "")
    return where, "; ".join([why, *extras]), True


def host_allowed(policy: dict | None, agent_id: str | None, host: str, credentialed: bool) -> bool | None:
    """Whether one request to ``host`` passes the policy (None when the policy is unknown).

    Conditional and path-specific rules are treated as applying to the host.
    """
    mode, _ = effective_mode(policy)
    if mode == "unknown":
        return None
    rules = applicable_rules(policy, agent_id)
    hit = lambda action: any(r["action"] == action and fnmatch.fnmatch(host, r["host"]) for r in rules)  # noqa: E731
    if hit("block"):
        return False
    if mode == "deny" and credentialed and not is_llm_host(host):
        return hit("allow")
    return True
