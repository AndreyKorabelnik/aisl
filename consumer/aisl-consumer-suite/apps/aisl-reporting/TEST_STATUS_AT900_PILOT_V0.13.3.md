# Test status — aisl-reporting 0.13.3 / AT900 pilot

## Automated tests

- Full suite: `54 passed, 16 skipped`.
- Focused system-description contract: `5 passed`.
- Fresh AT900 report profiles: `2 passed`.
- Python compileall: passed.
- Source manifest verification: passed.
- ZIP integrity: passed.

The 16 skipped tests require optional real artifacts that were not supplied to the generic full-suite invocation. AT900 tests were then run explicitly with the fresh AT900 Knowledge Layer and passed.

## Fresh AT900 input

- Repository: `client-profile`.
- Files analyzed: `1,038`.
- Core: `0.43.18`.
- Runner: `0.9.29`.
- Knowledge Layer Core: `0.53.4`.
- Suite: `default-system-analysis`.
- Suite status: completed.
- Timeouts: none.
- Stack-dump requests: none.

## Prepared report datasets

### System description

- Validation: passed.
- Canonical dataset size: `218,518` bytes.
- Evidence entries: `152`.
- Dangling evidence IDs: `0`.

### Data model

- Validation: passed.
- Canonical dataset size: `61,283` bytes.
- Evidence entries: `75`.
- Dangling evidence IDs: `0`.
- Report mode: `physical_only`.

## Not claimed

A live LLM endpoint was not called in this iteration. Therefore prose style of a generated AT900 report and unconstrained chat-answer quality are not claimed as validated. The deterministic evidence, selection, prompt contract and budgets are validated.
