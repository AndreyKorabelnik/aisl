# static-analysis-runner 0.10.8 — internal materialization dependency closure

- Adds the user-facing knowledge product `data-model-attribute-extension`, mapped to the existing KLC `cross-artifact-data-model-mapping` materialization.
- Completes the existing `internal_materializations` concept: required KLC technical materializations are now recursively added to the resolved technical plan while remaining unavailable for direct user selection.
- Internal materializations carry their typed evidence and knowledge-model requirements into the plan, so Core analyzers are selected through the normal `artifact_kind + schema_version` contract path.
- The default catalog classifies `model-storage-semantics`, `logical-storage-mapping` and `sql-target-source-mapping` as internal technical materializations; no KLC materialization remains uncatalogued.
- No materialization-specific dispatch, UCP/datamart naming heuristic, legacy fallback or second executor was introduced.
