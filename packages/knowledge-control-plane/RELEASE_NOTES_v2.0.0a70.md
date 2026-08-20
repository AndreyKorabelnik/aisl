# Analysis UI 2.0.0a70

## High-level terminal analysis command

Added a one-shot `analysis-ui run` command for launching an existing Knowledge Profile directly from a terminal without starting `analysis-ui serve`.

The command is intentionally a thin adapter over the existing Analysis UI control plane: repository discovery, `JobManager`, Runner execution, Knowledge API publication and Assistant preparation remain the same canonical path used by the HTTP/UI flow.

The first target use case is a repository containing a SQL datamart:

```bash
analysis-ui run \
  --profile sql-source-inventory-v1 \
  --repository /path/to/datamart \
  --system-id datamart-profile
```

Repository-scoped and workspace-scoped Knowledge Profiles are accepted according to the existing profile contract. The CLI does not add scenario-specific Runner commands or a parallel orchestration path.
