# knowledge-api 0.15.0

Iteration 107: expose canonical PDM physical-model reads.

## Changes

- Added revision-aware `/physical-model` summary, table, column, key, relationship and gap endpoints.
- Added typed public request/response models and canonical OpenAPI definitions.
- Added generic KLC adapter support for physical-model queries.
- Updated publication validation so PDM-only Knowledge Layers are accepted without routing through the logical data-model adapter.
- Raised the minimum KLC dependency to 0.53.1.

## Unchanged

- The API remains read-only for knowledge queries.
- No SQL, PDM or repository content is modified.
- PDM does not assign source/target roles.
