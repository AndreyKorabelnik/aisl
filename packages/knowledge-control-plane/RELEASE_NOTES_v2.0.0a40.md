# Analysis UI 2.0.0a40

Breaking revision-first UI redesign. No backward compatibility is retained.

- User navigation is now `Masters -> Revisions -> Report or Chat`.
- Removed legacy `/systems` and `/assistant-contexts` user routes and views.
- Removed user-facing DuckDB registration from the attribute-addition flow.
- Added exact revision catalogue and exact revision detail route.
- Added dedicated attribute-addition master using existing revisions or new repository analysis.
- Added deterministic chat welcome with capabilities and examples.
- Assistant contexts are now explicitly typed as `revision` or `attribute_addition` and contain role-based revision bindings.
- Removed assistant-context update API; contexts are immutable revision pins.
- Advanced mode remains a non-functional placeholder.
