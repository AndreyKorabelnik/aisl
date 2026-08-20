# static-analysis-runner 0.9.38 — Core stage architecture classification

## Added

- read-only classification of every stage label declared by all installed Core profiles;
- four architecture categories: base evidence, derived evidence, Knowledge Layer materialization candidate and technical packaging;
- runtime-binding diagnostics distinguishing Java executable stages from SQL/spec descriptive stage labels;
- source-file hashes and line references for observed execution bindings;
- stage classification embedded into resolved task/profile stage entries;
- architecture findings for hidden mutable-result dependencies and mixed stage responsibility;
- optional `--core-root` for `mechanism-catalog`.

## Runtime behavior

No analysis, suite, task, profile, Foundation, Knowledge Layer or output contract behavior changed.

## Current diagnostic result on Core 0.43.20

- 14 profiles;
- 48 distinct declared stage IDs;
- 48 classified, 0 unclassified;
- 15 base-evidence stages;
- 24 derived-evidence stages;
- 4 Knowledge Layer materialization candidates;
- 5 technical-packaging stages.
