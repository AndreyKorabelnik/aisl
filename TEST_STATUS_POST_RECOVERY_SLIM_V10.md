# Test Status — post-recovery Slim Source JOIN v10 merge

Date: 2026-08-14
Scope: focused affected contracts only; full framework regression intentionally not run.

Actual results in the recovered canonical source tree:
- `knowledge-integration` profile/contract tests: **9/9 PASS**.
- affected `knowledge-assistant` attribute-addition profile tests: **7/7 PASS**.
- `knowledge-api` integration-profile / consumer-runtime / CLI tests: **6/6 PASS**.
- focused total: **22/22 PASS**.
- rebuilt `knowledge-integration 0.1.2` wheel: runtime package files are byte-identical to the supplied slim wheel.
- rebuilt `knowledge-api 0.30.6` wheel: runtime package files are byte-identical to the supplied slim wheel.
- rebuilt wheel metadata confirms `knowledge-api==0.30.6` depends on `knowledge-integration==0.1.2`.
- `prepared-knowledge-runtime 0.1.0.post4`: no source delta between recovery and supplied slim wheel.

One recovery-only non-portable test path was found in `knowledge-assistant/tests/test_attribute_addition_profile.py`; it pointed at `/mnt/data/llm_integration_work/...`. It was changed to a source-tree-relative path. This is a test portability correction, not a runtime change.

Not run:
- full framework regression;
- real external LLM quality run against the industrial UCP prepared revision;
- real Bitbucket project acquisition.
