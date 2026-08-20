# Test results — Analysis UI 2.0.0a73

## Automated tests

- Full Analysis UI pytest suite: **67 passed**.
- Targeted CLI + knowledge execution + module baseline subset: **24 passed**.

## Static/runtime checks

- `python -m compileall -q src`: **OK**.
- `scripts/verify_knowledge_execution_architecture.py`: **OK**.
- `analysis-ui run --help`: **OK**.

## Packaging check

Wheel built with local setuptools using `--no-build-isolation` because the execution environment has no network access to fetch build dependencies.

Verified wheel contents include:

- `analysis_ui/resources/runtime_contracts/bundle-manifest.json`
- `analysis_ui/resources/runtime_contracts/core-evidence-contract-catalog.json`
- `analysis_ui/resources/runtime_contracts/knowledge-catalog.json`
- `analysis_ui/resources/runtime_contracts/knowledge-materialization-catalog.json`

A clean `--target` installation resolved all three operational catalogs from the installed Analysis UI package. No resolved path contained `validation`.

## Not rerun

A fresh real SQL-datamart end-to-end execution against Knowledge API was not rerun in this container. The execution path itself was not changed by 2.0.0a73; this release changes only runtime-contract discovery/packaging on top of the existing one-shot CLI.
