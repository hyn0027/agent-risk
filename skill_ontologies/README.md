# Top-skills endpoint ontologies — prototype

Each per-skill `.trig` file contains one named graph for one `top_skills/*/SKILL.md`. Two additional `.trig` files, `local-filesystem.trig` and `freeform-internet.trig`, are always-loaded **resource-only** catalogues: they define resource kinds and containment, but no operations, invocation channels, or effects. `vocabulary.ttl` defines the common classes and relations; `shapes.ttl` defines validation rules. `manifest.json` maps exact source directories and SHA-256 hashes to skill modules, and lists the baseline graphs. The manifest is loader metadata. Skill graphs catalog **potential surfaces and effects**, not agent identities, actual permissions, or execution traces. The source directory was read-only during preparation; the files do not invoke any skill.

All files use the same RDF prefix, `ar: <urn:agent-risk:>`. The IRIs are identifiers within this dataset, not dereferenceable Web URLs. For a public ontology, replace this private namespace with an owned, persistent HTTPS namespace.

## Loading

Keep one named graph per skill and version. The active dataset is the union of `vocabulary.ttl`, both baseline resource graphs, any separately verified harness-inventory graph, and the `.trig` graphs of loaded skills. `loader.py` loads the baselines on every run, uses `manifest.json` to find selected skills, rejects stale skill ontologies when source hashes differ, checks that shared-kind citations resolve to baseline-declared kinds, and validates the combined graph against `shapes.ttl`. It does not implement a harness hook, runtime availability check, or graph unloading. A later skill version should replace, not blindly accumulate with, the previous active version.

Run `python loader.py discord gh-issues` from this folder with `rdflib` and `pyshacl` installed. Omitting arguments selects those two skills by default; `python loader.py --baseline-only` lists shared resources with no skill-operation rows. The filesystem and internet baselines load in either case. `ar:HarnessBaseline` declares resource kinds with `ar:declaresKind`; only `ar:Skill` modules declare operations. "Always loaded" describes ontology inclusion only. It does **not** mean the agent actually has filesystem permissions, internet egress, an authenticated browser, or access to every remote endpoint.

The graph names do not themselves imply provenance or trust. `ar:sourceStatus` describes the basis for individual operation claims. All runtime availability, authentication, action gates, destinations, and provider behavior remain unverified. Example IDs such as `channel:<id>` and `slack:thread-1` are *templates/examples*, not concrete endpoints.

## Interpretation

- `ar:InvocationSurfaceKind` is a channel the harness or a tool may call (CLI, API, message tool, subagent launcher).
- `ar:WorldSurfaceKind` is a kind of resource that may be read, created, changed, deleted, or receive information.
- `ar:Operation` connects a call channel with potential effects, and occurs only in skill graphs. `ar:PotentialEffect` does not assert an observed mutation.
- `ar:usesSharedKind` is an explicit skill-to-baseline citation. `ar:specializesKind` maps a specific kind (for example `ar:LocalAudioFile`) to a broader baseline kind (`ar:LocalFile`). Both are RDF individuals representing kinds; this is not `rdfs:subClassOf`. `ar:mayBeStoredAsKind` is a weaker, conditional storage link when the physical representation is uncertain.
- `ar:Requirement` describes a stated prerequisite, not a verified permission grant.
- Effects on humans after messages, PRs, or media publication are **not** asserted. A delivered message does not imply it was read; a PR does not imply merge or deployment.

The graph gives endpoint reachability at a coarse level. Joint effects such as "read credential, then transmit it through Discord" need separate content-flow/state-transition rules; merging graphs alone will not infer them. Generic shell or delegated coding workers have open-ended effects. They are represented conservatively, not exhaustively.

Named connector/API endpoints such as Discord, GitHub REST, Imgflip `caption_image`, and Slack remain separate kinds even when their transport uses the internet. The freeform-internet catalogue is cited for unspecified websites and ordinary URL downloads, not used as a replacement for provider-specific endpoint semantics. No baseline operation is inferred merely because a skill cites a resource kind.

## Example query

Load the active graphs into the default graph or query each named graph with `GRAPH`. This query lists explicit skill citations to shared kinds:

```sparql
PREFIX ar: <urn:agent-risk:>
SELECT ?graph ?skill ?sharedKind WHERE {
  GRAPH ?graph {
    ?skill a ar:Skill ; ar:usesSharedKind ?sharedKind .
  }
}
```

The loader also prints skill-stated potential effects and, when possible, the shared parent kind reached through `ar:specializesKind`. To inspect effects directly:

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

This initial extraction covers all ten current `top_skills/*/SKILL.md` files and selected bundled references/scripts relevant to side effects. Nine skill modules explicitly cite shared resource kinds. The TaskFlow example has no identified local-file or freeform-internet resource and was left unchanged. The baselines are generic resource taxonomies, not an observed inventory of this harness. The extraction is a manually reviewed *first pass*, not an exhaustive code audit or runtime inventory. A verified harness graph is still absent because the source skills do not disclose the complete harness tool list or its live configuration. Add that inventory from harness schemas/configuration rather than guessing it from skill prose.
