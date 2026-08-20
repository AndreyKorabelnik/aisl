# Test results — iteration 16

Test level: targeted.

Completed:

- analysis-ui targeted suite: 34 passed, including proxy transport tests: JSON, Markdown, POST body, authorization, query strings, upstream 404, timeout, unavailable upstream, disabled proxy and OpenAPI boundary;
- publication and frontend contract regression;
- knowledge-api targeted suite: 16 passed;
- real same-origin proxy smoke with `knowledge-api 0.3.0a2`, DuckDB 1.5.5 and a 17,838,080-byte Knowledge Layer;
- Python compilation, source manifests and fresh archive extraction.

Not run:

- full analysis-ui runtime regression;
- UCP production E2E;
- full Vue/Vite production build.

The next full regression remains scheduled after iteration 17, when duplicated local knowledge-domain code is removed from `analysis-ui`.
