# Change report — UCP 91 external blind stand

Date: 2026-08-15

## Runtime changes

None. Core, Runner, KLC, Prepared Runtime, Knowledge API, Knowledge Integration, KCP and AISL contract package code/versions are unchanged.

## Validation/productization changes

- Added a reproducible external blind-stand acceptance record.
- Added the Gold-free `freeze_result.py` validator to canonical validation assets.
- Added stand metadata containing pinned revision, artifact/result fingerprints and required consumer runtime versions.
- Added an optional OpenAI-compatible consumer validation runner with generated-tool execution, batching and per-turn timing/trace. It remains outside AISL runtime.
- Updated recovery pointers/status to distinguish **stand ready** from **external agent score complete**.

## Deliberately not implemented

- no LLM/agent loop inside AISL;
- no vector/embedding retrieval in AISL;
- no Gold-derived synonyms/targets in runtime;
- no new Core/KLC producer or materializer;
- no synthetic external-agent score.
