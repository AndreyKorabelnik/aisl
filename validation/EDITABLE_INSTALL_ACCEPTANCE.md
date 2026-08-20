# Editable install acceptance

Source: extracted final full-code ZIP.

Command shape validated for all nine `packages/<module>` projects with editable installation.
Validation used `--no-deps --no-build-isolation` because external package-index access is unavailable. The isolated test venv was explicitly given the locally installed setuptools build backend.

Result: PASS.

Post-install imports/versions:
- knowledge-control-plane 1.2.0a7
- knowledge-assistant 0.25.1.post4
- knowledge-layer-core 0.61.0a20
- code-analyzer-core 0.44.23a3

`knowledge-control-plane --help`: PASS.
