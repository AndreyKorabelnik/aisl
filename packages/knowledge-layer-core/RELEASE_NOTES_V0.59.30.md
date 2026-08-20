# knowledge-layer-core 0.59.30

Case-sensitive HTTP path matching for system interactions.

- Preserves observed HTTP path case during KLC path normalization.
- Still normalizes redundant separators and trailing slash without changing case.
- Prevents case-only variants such as `/UpdateOrCreate` and `/updateOrCreate` from becoming a false `exact_path` match.
- Allows evidence-backed suffix matching to remain available: in the real workspace `/ucp/updateOrCreate` -> `/updateOrCreate` is now reported as `normalized_path` while the original source variants remain visible.
- Does not change confidence policy in the same iteration: matches without target addressing/service identity remain `probable` rather than being silently promoted.

Real four-repository workspace result remains structurally stable:
- system interactions: 3;
- boundary interactions: 3;
- execution contexts: 8;
- diagnostics: 17.

Real match bases after the fix:
- `/sberProfileId/search` -> `/sberProfileId/search`: `exact_path`, probable;
- `/updatePhoneFlags` -> `/updatePhoneFlags`: `exact_path`, probable;
- `/ucp/updateOrCreate` -> `/updateOrCreate`: `normalized_path`, probable.

No application names, endpoint names or Manual Gold values are hardcoded. Core remains unchanged.
