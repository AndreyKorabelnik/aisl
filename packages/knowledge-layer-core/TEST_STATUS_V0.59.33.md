# Test status — knowledge-layer-core 0.59.33

## Targeted regression

Confirmed PASS:
- new attribute-extension context tests: **6 passed**;
- existing reference-value/key correspondence runtime: **2 passed**;
- existing relationship key-lineage runtime: **4 passed**;
- existing relationship storage diagnostics: **3 passed**;
- selected workspace data-model relationship/correspondence contracts: **3 passed**;
- materialization contract/runtime tests: **13 passed**.

Total confirmed targeted tests: **31 passed**.

## Real validation

Built `data-model-attribute-extension-context/v1` from the real UCP + TSA + `datamart_profile_fl` + PDM knowledge artifacts without changing Core.

Result counts:
- builds: 1;
- sources: 5;
- object anchors: 1326;
- join semantics: 1573;
- context gaps: 1027.

Safety checks:
- join semantics exist: PASS;
- unsafe direct physical JOIN inference used: false;
- fuzzy identity matching used: false;
- generated SQL emitted: false;
- unknown join method count: 0.

Representative Manual Gold C1–C6 semantics are documented in `SYSTEM_DATA_MODEL_AGENT_JOIN_REAL_VALIDATION_V0.59.33.md`.

## Packaging

Compile/import, source manifest, clean ZIP and unpacked import are verified during final packaging.

## Known limitations

- Many broader logical relationships remain `not_established`/gap when storage or physical representation is not observed; the materialization intentionally does not guess them.
- PDM physical candidates for UCP raw source objects may be absent because the supplied EPKAP PDM does not map those source FQCNs; observed SQL relation anchors remain available separately.
- This version materializes knowledge only; user-facing product orchestration and a thin API surface are separate downstream steps.
