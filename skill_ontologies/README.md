# Top-skills endpoint ontologies — prototype

Each `.trig` file contains one named graph for one `top_skills/*/SKILL.md`. `vocabulary.ttl` defines the common classes and relations; `shapes.ttl` defines validation rules. `manifest.json` maps exact source directories and SHA-256 hashes to their ontology modules and graph names. The manifest is loader metadata; every per-skill ontology uses TriG. These graphs catalog **potential surfaces and effects**, not agent identities, actual permissions, or execution traces. The source directory was read-only during preparation; the files do not invoke any skill.

All files use the same RDF prefix, `ar: <urn:agent-risk:>`. The IRIs are identifiers within this dataset, not dereferenceable Web URLs. For a public ontology, replace this private namespace with an owned, persistent HTTPS namespace.

## Loading

Keep one named graph per skill and version. The active dataset is the union of `vocabulary.ttl`, a separately verified harness-inventory graph, and the `.trig` graphs of loaded skills. A loader can use `manifest.json` to find the matching source directory and reject a stale ontology if its source hash differs. Loading a skill adds its graph; unloading removes it from the active view without erasing the archived graph. Validate each graph against `shapes.ttl` before activation. A later version should replace, not blindly accumulate with, the previous active version. No harness hook/loader has been installed in this prototype.

The graph names do not themselves imply provenance or trust. `ar:sourceStatus` describes the basis for individual operation claims. All runtime availability, authentication, action gates, destinations, and provider behavior remain unverified. Example IDs such as `channel:<id>` and `slack:thread-1` are *templates/examples*, not concrete endpoints.

## Interpretation

- `ar:InvocationSurfaceKind` is a channel the harness or a tool may call (CLI, API, message tool, subagent launcher).
- `ar:WorldSurfaceKind` is a kind of resource that may be read, created, changed, deleted, or receive information.
- `ar:Operation` connects a call channel with potential effects. `ar:PotentialEffect` is deliberately conditional and does not assert an observed mutation.
- `ar:Requirement` describes a stated prerequisite, not a verified permission grant.
- Effects on humans after messages, PRs, or media publication are **not** asserted. A delivered message does not imply it was read; a PR does not imply merge or deployment.

The graph gives endpoint reachability at a coarse level. Joint effects such as "read credential, then transmit it through Discord" need separate content-flow/state-transition rules; merging graphs alone will not infer them. Generic shell or delegated coding workers have open-ended effects. They are represented conservatively, not exhaustively.

## Example query

Load the active graphs into the default graph or query each named graph with `GRAPH`. This query lists skill-stated operations and the kinds of surfaces they may touch:

```sparql
PREFIX ar: <urn:agent-risk:>
SELECT ?graph ?operation ?toolKind ?effectType ?affectedKind WHERE {
  GRAPH ?graph {
    ?operation a ar:Operation ;
      ar:invokedThroughKind ?toolKind ;
      ar:hasPotentialEffect ?effect .
    ?effect ar:effectType ?effectType ; ar:affectsKind ?affectedKind .
  }
}
```

## Coverage and limits

This initial extraction covers all ten current `top_skills/*/SKILL.md` files and selected bundled references/scripts relevant to side effects. It is a manually reviewed *first pass*, not an exhaustive code audit or runtime inventory. A harness graph is intentionally absent because the source skills do not disclose the complete harness tool list or its live configuration. Add that inventory from harness schemas/configuration rather than guessing it from skill prose.
