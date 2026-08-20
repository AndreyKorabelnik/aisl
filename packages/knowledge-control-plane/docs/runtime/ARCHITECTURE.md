# Knowledge Control Plane runtime architecture — 1.2.0a33

## Responsibility

Knowledge Control Plane is the headless AISL Producer orchestration backend. It owns source preparation, Knowledge Profile execution, job lifecycle and creation of a self-contained publication bundle. It does **not** create or activate AISL revisions.

## Module boundaries

```text
Knowledge Control Plane / AISL Producer
  orchestration, job lifecycle, source checkout, Runner execution, bundle creation

Core
  analyzer registry and typed observed evidence

Runner
  input inventory, execution DAG, generic producer execution

KLC
  materializer registry and typed knowledge products

AISL Server / Knowledge API
  bundle import, validation, immutable Artifact Store ingestion, revisions, capabilities, read API

AISL Client / UI
  independent consumers of published revisions
```

## Canonical execution

```text
Sources
→ Knowledge Profile
→ Runner knowledge-input-inventory
→ Runner knowledge-execution-plan
→ Runner knowledge-execute
→ knowledge_execution_result/v2
→ aisl_publication_bundle/v2
→ DONE (Producer)

AISL Server:
publication bundle
→ validate bundle identities
→ validate prepared knowledge
→ import immutable bytes into server-owned SHA CAS
→ create/activate immutable revision
```

Producer and Server do not require a shared filesystem. Absolute Producer paths remain provenance inside prepared artifacts; Server import relocates them only during validation and stores published bytes under `aisl+sha256://...`.

## Consumer boundary

Consumers start from a Server-owned `system_id` + pinned `revision_id`. They do not require Core, Runner, KLC, source repositories or Producer runtime state.
