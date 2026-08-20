# knowledge-control-plane configuration

The backend initializes persistent configuration from environment variables and stores revisions in the runtime SQLite database.

Supported initial environment variables:

```text
KNOWLEDGE_CONTROL_PLANE_RUNTIME_ROOT
KNOWLEDGE_CONTROL_PLANE_ANALYSIS_OUTPUT_ROOT
KNOWLEDGE_CONTROL_PLANE_PROFILES_ROOT
KNOWLEDGE_CONTROL_PLANE_MAX_CONCURRENT_JOBS
STATIC_ANALYSIS_RUNNER_COMMAND
KNOWLEDGE_API_BASE_URL
KNOWLEDGE_API_TIMEOUT_SECONDS
KNOWLEDGE_API_PROXY_ENABLED
```

Use:

```text
GET  /api/v1/configuration
PUT  /api/v1/configuration
POST /api/v1/configuration/validate
```

Published systems and revisions are owned by the external canonical `knowledge-api`. The knowledge-control-plane database stores orchestration jobs and raw artifact metadata only. The same-origin proxy is transport-only.

Do not commit certificates, private keys, tokens, generated outputs or the runtime SQLite database.


Frontend build-time setting:

```text
VITE_PRIORITY_MASTER_IDS
```

Comma-separated allowlist of pipeline master IDs shown on the home page. If unset, Knowledge Control Plane shows the four priority masters: data model, system description, foreign-data persistence and system interaction.
