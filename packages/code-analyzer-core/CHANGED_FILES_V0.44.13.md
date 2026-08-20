# Changed files — 0.44.13

- `code_analyzer_core/scanners/system_description_enrichment.py`
  - conservative inbound scenario call-graph composition;
  - selected JSONL sections streamed from the uncapped source-observation store;
  - reachable storage/outbound observations attached to scenarios;
  - test-source and ambiguous implementations excluded from traversal.
- `code_analyzer_core/navigation.py`
  - compact scenario record retains bounded call chain, reachable count and composition status/policy.
- `tests/test_system_description_evidence.py`
  - scenario-composition regression coverage.
- version metadata: `0.44.13`.
