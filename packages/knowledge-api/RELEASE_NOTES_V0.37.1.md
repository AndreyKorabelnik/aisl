# knowledge-api 0.37.1

Date: 2026-08-17

## Multi-repository observed product publication

Observed Core product replacement slots are now source-aware:

```text
core:<source_id>:<artifact_kind>
```

This allows one immutable AISL revision to contain the same observed artifact kind from multiple source repositories without weakening the one-product-per-replacement-slot invariant.

The slot intentionally excludes source revision/fingerprint so it remains stable when the same repository changes and copy-on-write replacement can replace only that repository's product.

For source IDs that cannot be represented directly by the public Identifier alphabet, publication uses a deterministic SHA-256 source token. The original source identity remains present in product provenance.

## Packaging

`prepared-knowledge-runtime` is now declared as `>=0.1.0,<0.2.0` instead of the stale exact `0.1.0.post8` pin. Canonical reproducibility remains owned by the release/recovery version manifest, while package metadata declares the supported runtime contract line.

## Compatibility

No adapter or dual slot identity is introduced. Existing revisions retain their immutable published metadata. New publications use the source-aware slot identity.
