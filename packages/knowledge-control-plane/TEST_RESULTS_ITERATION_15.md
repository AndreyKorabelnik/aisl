# Test results — iteration 15

Test level: **targeted**.

## Automated checks

- Analysis UI frontend/boundary/publication tests: **15 passed**.
- Canonical Knowledge API contract/runtime tests: **16 passed**.
- Strict TypeScript check for orchestration and Knowledge API clients: **passed**.
- Vue script syntax: **13 files passed**.
- Python compilation: **passed**.
- visual contracts: **12 legacy sections unchanged; 14 workspace/system sections pinned**.
- source manifests: **passed**.

## Real Knowledge API smoke

A real 17,838,080-byte Knowledge Layer was published and queried through `/api/knowledge/v1`.
The response shapes consumed by Vue were verified:

- active revision state and `source.execution_id`;
- table catalog in `items`;
- 2 tables;
- first table: 3 fields, 1 key and 1 relationship;
- Markdown report returned successfully.

Evidence: `validation/FRONTEND_KNOWLEDGE_API_SMOKE_ITERATION_15.json`.

## Intentionally not run

- full Analysis UI runtime regression;
- complete runner/reporting pipeline suite;
- real UCP E2E;
- full Vue/Vite build requiring the internal npm registry.

The next full regression remains scheduled after removal of the duplicated local knowledge implementation in iteration 17.
