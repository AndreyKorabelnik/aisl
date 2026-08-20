# Current state

Date: 2026-08-19
Status: `GITHUB_BOOTSTRAP_PREPARED`

## Source canonical

Before first Git push, provenance is the verified pre-Git archive:

`auto-code-analysis-current-reporting-http-parity-2026-08-19.zip`

SHA-256:

`f6b39783676cea949e76d47d7982436deafded3ab644266d92c6b53b2603465f`

After bootstrap commit is pushed, **Source canonical is the exact Git commit returned by**:

```bash
git rev-parse HEAD
```

Do not attempt to store the current HEAD SHA inside the same commit as a self-referential canonical value. Handover/release notes can record the resolved SHA externally, while Git itself remains authoritative.

## Framework/runtime versions

- evidence-common 0.23.2
- code-analyzer-core 0.44.23a7
- static-analysis-runner 0.10.28
- knowledge-layer-core 0.61.0a39
- prepared-knowledge-runtime 0.1.0.post14
- knowledge-integration 0.1.17
- knowledge-control-plane 1.2.0a35
- knowledge-api 0.40.3

## Consumer versions

- aisl-consumer-suite 0.7.2
- aisl-sdk 0.3.0
- aisl-sdk-typescript 0.3.0
- aisl-cli 0.2.0
- aisl-reporting 0.4.3
- aisl-agent-runtime 0.2.1
- aisl-workbench 0.4.1

## Clean delivery versions

- aisl-producer 0.3.2
- aisl-server 0.3.3
- aisl-client 0.3.2
- aisl-ui 0.2.2

`SOURCE_TO_DELIVERY_MAP.json` is the current source-to-delivery map.
