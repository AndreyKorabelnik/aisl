# knowledge-api 0.3.0a2

The canonical `/api/knowledge/v1` contract is now backed by production runtime code.

## Highlights

- persistent systems and immutable historical revisions;
- producer-neutral publication API;
- local artifact validation by allowed root, byte size and SHA-256;
- Knowledge Layer semantic validation through `knowledge-layer-core`;
- revision-aware tables, fields, keys and relationships;
- published Markdown reports;
- deterministic idempotent revision identifiers;
- temporary coexistence with legacy read-only `/api/v1` routes.

Only local `file://` artifacts are accepted in this iteration. Remote/object-storage resolvers are intentionally deferred.
