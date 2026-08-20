# Knowledge Layer Core 0.59.38

## Reference Data / own NSI read consolidation

- Added grounded reference-data candidate context over existing prepared `reference-data/v1`.
- Candidate context aggregates observed representations, local definition evidence, definition modes, usage observations and gaps.
- Added generic observed definition modes for seed SQL, code declarations and source files including CSV/TSV/JSON/YAML/XML-like declared value sets.
- Fixed reference-data search so caller pagination is applied after candidate aggregation/filtering; small limits no longer hide matching candidates.
- Production view excludes only explicitly test/example/documentation evidence; `unknown` source-set remains visible as unknown rather than being silently discarded.
- KLC does **not** assign own-NSI/global-authority verdicts. Interpretation remains with LLM/human.

Producer analyzers/materializations are unchanged.
