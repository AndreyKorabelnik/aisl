# aisl-reporting 0.13.4

## Mermaid reliability

- Added deterministic normalization of Mermaid fenced blocks before `report.md` is written.
- Flowchart node labels are quoted and spaced edge labels are converted to canonical `-->|label|` syntax.
- ER entity names containing schema separators such as `mbk_cache.card` are quoted.
- The normalization result is recorded in `report-validation.json`.
- Strengthened the system-description renderer prompt with Mermaid 11-safe examples.

The transformation changes formatting only; diagram nodes, edges, labels and report narrative are not inferred or replaced.
