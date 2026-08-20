# Test results — iteration 14

Test level: **targeted**

## Analysis UI

- module/contract/frontend/boundary tests: 23 passed;
- publication-specific integration tests: 3 passed;
- selected pipeline/capability/diagnostic/reuse tests: 6 passed;
- total targeted analysis-ui tests: 32 passed;
- Python compilation: passed.

## Knowledge API

- complete small module suite: 35 passed.

## Real integration smoke

`analysis-ui 2.0.0a11` published a real 17,838,080-byte Knowledge Layer through `knowledge-api 0.3.0a2`. The resulting system, table catalog and Markdown report were retrieved over the canonical API. Tables observed: `address`, `customer`.

The long combined interpreter again stalled during teardown after successful test output; all targeted tests were rerun in isolated processes and passed.

## Not run

- complete `analysis-ui` regression suite;
- full UCP E2E;
- Vue/Vite production build.

The next full regression is scheduled after duplicate knowledge-domain code is removed from `analysis-ui` (iteration 17), with final real UCP E2E in iteration 18.
