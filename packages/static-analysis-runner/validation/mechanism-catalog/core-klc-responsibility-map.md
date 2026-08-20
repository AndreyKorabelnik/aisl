# Core → KLC responsibility map

Schema: `core_klc_responsibility_map/v1`  
Execution effect: `none`

## Target architecture

- **Core Analyzer:** technical Foundation and independent source-grounded evidence analyzers.
- **Knowledge Layer:** composition of persisted evidence into knowledge models and views.
- **Runner:** process orchestration, retries and lifecycle only.

## Summary

- Core stages reviewed: **29**
- Produced result families: **47**
- Current Foundation stages: **10**
- Target Foundation/source-index stages: **9**
- Independent evidence analyzer stages: **14**
- Knowledge materializations to move to KLC: **1**
- Technical packaging stages: **5**

## Migration sequence

1. `code_conceptual_model_build` → knowledge-layer common/workspace data-model materialization (`partial_existing_klc_consumer`)

## Knowledge materialization candidates

### `code_conceptual_model_build`

- Current owner: `code-analyzer-core`
- Target owner: `knowledge-layer-core`
- Affected profiles: `repository-data-model-static`, `repository-system-data-model`
- Affected tasks: none
- Affected suites: none
- What stays in Core:
  - java structural evidence
  - persistence mapping evidence
  - mapping and relationship observations
  - physical schema evidence
  - source provenance and gaps
- What moves to KLC:
  - conceptual entities and fields projection
  - effective associations and inheritance composition
  - logical-to-physical model composition
- Evidence gaps / blockers:
  - KLC currently requires compact/code_conceptual_model artifacts from Core for repository data-model materialization.
  - The raw evidence families used by the current Core materializer must be enumerated and proven sufficient before removing that artifact.
  - Result parity must be checked on real repositories before the Core materializer is deleted.

## Deferred work

- Redesigning Task and Suite boundaries.
- Eliminating repeated heavy analyzers.
- Caching and persisted evidence bundles.
- Runtime enforcement of analyzer independence.
