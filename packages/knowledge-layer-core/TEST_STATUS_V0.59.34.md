# Test status — knowledge-layer-core 0.59.34

Targeted regression:
- cross-artifact data-model mapping runtime;
- agent-ready attribute-extension context;
- materialization contracts;
- materialization runtime.

Result: **21 passed**.

Root-cause regression verifies that the cross-artifact runtime result and Knowledge Layer manifest both publish:
- mart `cross-artifact-target-source-mapping`;
- capability `common.sql-target-source-mapping`.

Compile/import, manifest, clean unzip/import and ZIP integrity are verified during packaging.
