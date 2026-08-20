# code-analyzer-core 0.43.1

## Iteration 71 — auxiliary PowerDesigner physical-model facts

- Added `analyze-physical-model` for deterministic, facts-only extraction from PowerDesigner PDM XML.
- Added the independent `physical-model/v1` artifact with typed JSONL fact streams for tables, columns, keys, relationships and extraction gaps.
- Preserved source metadata, source SHA-256, stable IDs, package paths and object-level evidence.
- Physical-model facts are auxiliary schema evidence. They do not infer SQL usage, rewrite SQL lineage or replace repository evidence.

- Fact IDs use immutable PDM object IDs; duplicate fact IDs are rejected before artifact publication.
