# Changed files — Static Analysis Runner 0.10.22

- `static_analysis_runner/knowledge_planning.py`, `knowledge_execution_planning.py` — generic optional-evidence `production_policy` and bounded `existing_only` planning.
- `static_analysis_runner/input_preparation.py`, `cli.py` — repository source metadata input without changing observed source fingerprints.
- `static_analysis_runner/knowledge_execution.py`, `knowledge_materialization_executor.py` — carry repository-structure metadata to Repository Inventory and include it only in the relevant materialization reuse identity.
- affected tests — production-policy, metadata propagation, reuse identity and CLI wiring.
- version metadata — 0.10.22.
