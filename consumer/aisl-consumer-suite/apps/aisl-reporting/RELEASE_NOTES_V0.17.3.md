# aisl-reporting 0.17.3

Completes the first Gold-driven System Data Model report restoration block.

- Carries forward cross-artifact lineage consumption from the 0.17.2 checkpoint.
- Prioritizes logical objects that actually participate in published lineage; ambiguous simple-name matches are never used for prioritization.
- Prioritizes PDM target tables reached by lineage and their declared physical neighbours.
- Selects diverse journey examples from already materialized correspondences (direct name correspondence, rare source types, deterministic fill) rather than alphabetic first rows.
- Keeps the report dataset below the existing 500 KB budget; full lineage remains queryable through Knowledge API.
