# Analysis UI 2.0.0a47

- The home page now shows only the priority masters by default: data model, system description, foreign-data persistence and system interaction. The list can be overridden at frontend build time with `VITE_PRIORITY_MASTER_IDS`.
- The attribute-addition preparation master now uses the fixed canonical profiles `repository-data-model-static` for the source model and `sql-mart-lineage` for the SQL datamart.
- PDM preparation no longer requires a separately discovered static-analysis profile. It uses the built-in `physical-model/v1` flow directly.
- Added explicit Bitbucket username/token fields to the attribute-addition preparation master. Credentials are kept only in backend memory until checkout and are not written to jobs, SQLite, localStorage, CLI previews or analysis artifacts.
- Git checkout now disables inherited terminal, VS Code and credential-manager prompts. Missing or invalid credentials fail quickly with a visible checkout error instead of leaving a job indefinitely on the checkout stage.
