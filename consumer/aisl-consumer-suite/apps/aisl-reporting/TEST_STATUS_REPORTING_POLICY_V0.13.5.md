# Test status — aisl-reporting 0.13.5

## Environment

- Python: 3.13
- Evidence Common source: 0.23.2
- Knowledge Layer Core source: 0.53.7
- Network access for build dependencies: unavailable; wheel built with `--no-build-isolation` using installed setuptools/wheel.

## Results

### Syntax

```text
python -m compileall -q aisl_reporting tests
passed
```

### Targeted regression

Profiles/pipeline/contracts/system/workspace/SQL tests:

```text
34 passed in 2.83s
```

### Full module regression

```text
68 passed, 16 skipped in 1.26s
```

Skipped tests require real external artifacts that were not present in the execution environment:

- UCP conceptual model Knowledge Layer;
- UCP data model Knowledge Layer;
- UCP full Knowledge Layer for FDP/reference data;
- UCP interaction Knowledge Layer;
- @900 Knowledge Layer;
- git change analysis fixture from environment.

No changed-path test was skipped.

### Package build

```text
aisl_reporting-0.13.5-py3-none-any.whl
SHA-256: 99dc6a126cc92f36d58445e4a117bc5da65874fc3cf2e60f9b530bebcd00b218
```

Verified inside wheel:

- common editorial policy resource: present;
- report contracts: 7;
- renderer prompts: 7.

## Known limitations

- Real LLM rendering comparison on saved @900/UCP datasets has not yet been run.
- Physical ER completeness is still bounded by the existing data-model dataset selection (up to 25 physical tables and 25 physical relationships in standard/detailed mode).
- Conceptual Data Model artifact and SDD package prompts were intentionally not changed.

## Next step

Extend `data-model-report/v1` dataset with deterministic logical and physical ER sections, full declared relationships up to 30, domain grouping for larger models and explicit separation of declared FK from observed usage joins.
