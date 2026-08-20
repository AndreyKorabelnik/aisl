# Knowledge Control Plane 1.2.0a27

## Block E — Core/Runner contract repin

- Repins the canonical Core evidence contract catalog for code-analyzer-core `0.44.23a7`.
- Repins the canonical Runner knowledge catalog for static-analysis-runner `0.10.27`.
- Repins the KLC materialization catalog generated from KLC `0.61.0a35` against the updated canonical Core target fingerprint.
- Regenerates the runtime contract bundle manifest from canonical catalog owners.
- Adds no independent applicability logic to Knowledge Control Plane.

Real acceptance corrected the Core declaration for `data-model-candidate-evidence`: applicability is now deliberately `not_formalized` because the existing scanner observes Java, declarative schema, SQL DDL/migrations, and model-oriented paths. Runner therefore preserves execution until Core can state a complete safe non-applicability predicate.
