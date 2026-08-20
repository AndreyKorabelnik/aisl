# Test status — static-analysis-runner 0.10.16

- Full Runner test suite: 87 passed.
- compileall: PASS.
- Real planning smoke: UCPDataModel + UCPucp-tsa-v4 + datamart_profile_fl + PDM -> inventory with 3 source snapshots + 1 typed PDM artifact -> data-model-attribute-extension plan READY.
- Real plan: 12 execution nodes = 5 Core analyzers + 7 KLC materializations; blocking diagnostics: 0.
- No KLC/Core semantic contracts changed.
