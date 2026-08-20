# AISL Platform / aisl-workbench 0.4.1

Standalone browser shell over separated AISL boundaries.

## Surfaces

- **Build** → Knowledge Control Plane (`AISL_KCP_URL`)
- **Explore / Products / Provenance / Diagnostics** → Knowledge API (`AISL_API_URL`) via public TypeScript SDK
- **Reports** → `aisl-reporting` (`AISL_REPORTING_URL`)
- **Chat** → `aisl-agent-runtime` (`AISL_AGENT_URL`)

Build does not reproduce Core/Runner/KLC planning. It discovers KCP scenarios and parameters, submits the public `JobCreateRequest`, observes the job, and opens the exact published immutable revision when available.

## Run

```bash
AISL_API_URL=http://127.0.0.1:8080 \
AISL_KCP_URL=http://127.0.0.1:8000 \
AISL_REPORTING_URL=http://127.0.0.1:8090 \
AISL_AGENT_URL=http://127.0.0.1:8091 \
node server/server.mjs
```

Only `AISL_API_URL` is mandatory. Missing KCP/Reporting/Agent services are shown explicitly as unavailable.
