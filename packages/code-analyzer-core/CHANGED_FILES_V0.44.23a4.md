# code-analyzer-core 0.44.23a4 — repository structure evidence

- Added universal repository enumeration separate from the historical analyzer-eligible file view.
- Added official observed-only `repository-structure-evidence/v1` and registered `repository-structure-analyzer`.
- Evidence records all non-skipped files, content identity, extension composition, and the precise Core analyzer frontier (`eligible` / `outside_frontier`).
- Existing `scan_files()` semantics remain unchanged for all existing analyzers.
- No concept classification, novelty inference, or business meaning is produced by Core.
