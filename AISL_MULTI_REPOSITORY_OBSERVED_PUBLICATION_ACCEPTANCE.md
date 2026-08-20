# AISL multi-repository observed publication — acceptance

Date: 2026-08-17
Status: PASS

## Structural acceptance

Two observed Core artifacts of the same kind from different repositories can coexist in one immutable revision.

```text
ucp-api      -> core:ucp-api:java-type-structure-evidence
ucp-tsa-v4   -> core:ucp-tsa-v4:java-type-structure-evidence
```

A true duplicate for the same source repository and artifact kind remains a publication conflict.

Incremental COW acceptance proves that replacing repository A's observed product retains repository B's product unchanged.

## Real acceptance

The real UCP `build-data-model-v1` scenario with `ucp-api + ucp-tsa-v4` completed and published revision:

`rev-cf1820d42ff0cf021ccb358a`

Published products:

- observed `core:ucp-api:java-type-structure-evidence`
- observed `core:ucp-tsa-v4:java-type-structure-evidence`
- derived `klc:code-declared-data-model`

The prior failure `execution contains multiple observed artifacts for one Core product slot` is not reproduced.
