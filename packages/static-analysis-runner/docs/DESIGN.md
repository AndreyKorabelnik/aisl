# Design

## Scopes

The runner exposes only two domain scopes:

```text
repository
workspace
```

A profile or suite is an execution strategy within a scope, not a third scope.

## Repository

```text
one repository + one profile
  -> code-analyzer-core
  -> repository-analysis-manifest.json
```

or:

```text
one repository + suite
  -> shared foundation
  -> task profiles
  -> repository suite manifest
```

## Workspace

```text
repository selection
  -> repository execution x N
  -> one workspace Knowledge Layer
```

Profile mode uses the established data-model workspace builder. Suite mode aggregates suite manifests directly with `knowledge-layer-core`.

## Evidence policy

The runner controls processes and artifacts only. It does not infer source-code semantics, assign confidence or invoke an LLM.
