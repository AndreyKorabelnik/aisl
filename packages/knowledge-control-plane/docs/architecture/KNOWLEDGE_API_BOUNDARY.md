# Knowledge API boundary

Knowledge Control Plane is a Producer orchestrator, not a semantic store and not a revision publisher.

## AISL Producer owns

- source registration/checkout;
- Knowledge Profile selection and execution;
- job lifecycle, logs and artifacts;
- self-contained `aisl_publication_bundle/v2` creation;
- optional reads of pinned published revisions for composition scenarios.

## AISL Server / Knowledge API owns

- publication bundle import and validation;
- immutable Artifact Store bytes;
- systems and immutable revisions;
- revision activation/lifecycle;
- typed product membership, capabilities and domain read projections.

## Enforced rules

- Producer never creates a revision and never sends Producer-local `file://` paths as a cross-project publication contract.
- Server publication has one canonical engine; local `publish` and bundle `import` are input transports to that engine.
- Producer and Server do not require a shared filesystem.
- Consumers use pinned published revisions through Knowledge API / knowledge-integration.
