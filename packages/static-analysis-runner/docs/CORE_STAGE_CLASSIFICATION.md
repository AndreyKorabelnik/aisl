# Core stage architecture classification

Stage classification is owned and published by `code-analyzer-core` in `core_analysis_catalog/v1`. Runner consumes owner-published Core contracts when compiling typed execution plans; it does not rediscover or reclassify Core stages.

The former Runner-owned system-wide mechanism catalog has been removed. Architecture/audit tooling must use official owner catalogs and manifests directly rather than scanning source trees of other modules.

## Boundary

```text
Core typed evidence contracts
→ Runner execution planning
→ KLC materialization contracts
```

Dependencies between internal algorithm phases may remain inside one Core analyzer. They are not a second Runner stage taxonomy.
