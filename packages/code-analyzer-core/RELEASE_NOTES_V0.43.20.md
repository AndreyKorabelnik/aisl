# code-analyzer-core 0.43.20

Adds the independent `repository-data-model-discovery` profile for large Bitbucket portfolio scans.

The profile publishes `compact/data_model_candidate_profile.json` with transparent repository-level signals, a bounded evidence list, a sortable score and one of `strong`, `possible`, `weak` or `not_candidate`. It does not build a data model, persistence lineage, interaction topology or a workspace.

The detector is framework-neutral: standard persistence/document annotations, custom annotation suffixes, model-oriented paths, model parser/generator classes, schema-bound classes and declarative/physical schema files are observed without UCP-specific class, package or annotation names.
