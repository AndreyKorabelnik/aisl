# Preflight applicability → Runner selection — Block E Test Status

Date: 2026-08-16
Verdict: PASS

Authoritative completed test summaries:

- code-analyzer-core 0.44.23a7: **610/610 PASS**
- static-analysis-runner 0.10.27: **113/113 PASS**
- knowledge-layer-core 0.61.0a35: **256 PASS / 8 SKIPPED**
- prepared-knowledge-runtime 0.1.0.post10: **10/10 PASS**
- knowledge-api 0.35.0: **118/118 PASS**
- knowledge-control-plane 1.2.0a27: **95/95 PASS**
- fresh real gateway publication: **PASS**
- fresh real SQL-heavy datamart publication: **PASS**

Timeout/incomplete pytest invocations were not counted as PASS. Suites that exceeded the execution-tool window were rerun in smaller independent groups until every test file had a completed pytest summary.

One earlier Core group was invoked from the wrong working directory and failed a test that intentionally reads `code_analyzer_core/pipeline.py` relative to the package root. That invocation is not counted; the same group was rerun from the correct package root and completed 141/141 PASS.
