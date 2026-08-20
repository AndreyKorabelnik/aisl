# Changed files — aisl-reporting 0.1.0

Primary extraction changes:

- package namespace renamed to `aisl_reporting`;
- CLI renamed to `aisl-reporting`;
- `contracts.py`: API-revision-only request/run contracts;
- `pipeline.py`: removed direct-artifact branch;
- `profile.py`: all active profiles require published Knowledge API knowledge;
- `renderer.py`: removed evidence-common LLM client dependency;
- removed direct `git_change_impact` profile;
- added extraction boundary tests and standalone documentation.
